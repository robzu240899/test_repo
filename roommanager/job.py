from django.db.models.expressions import F
from main.threads import EmailThread
import boto3
import copy
import json
import logging
import re
import traceback
from datetime import datetime
from dateutil.relativedelta import relativedelta
from django.db import transaction
from django.db.models import Q
from django.core.mail import EmailMessage
from django.conf import settings
from django.contrib.auth.models import User
from django.forms.models import model_to_dict
from django.template.loader import render_to_string
from django.template.loader import get_template
from sentry_sdk import capture_exception
from sentry_sdk import configure_scope
from fascard.api import FascardApi, PricingHistoryAPI
from main.decorators import ProductionCheck
from outoforder.ingest import SlotDataStructure
from reporting.models import LaundryRoomExtension
from revenue.models import FascardUser, LaundryTransaction
from revenue.enums import TransactionType
from maintainx.enums import MaintainxDefaultCategories, MaintainxWorkOrderPriority
from maintainx.managers.managers import MaintainxWorkOrderManager, MaintainxLocationManager
from upkeep.api import UpkeepAPI
from upkeep.manager import UpkeepManager
from .enums import TimeZoneType, HardwareType, ORPHANE_MESSAGES, BundleType, ChangeType, \
MachineType, LanguageChoices, AssetMapOutChoices, AssetPicturesChoice, MissingAssetFieldNotifications
from .exceptions import WrongEquipmentTypeForMachine, WrongEquipmentTypeForBundle
from .helpers import Helpers, get_equipment_type, MessagesTranslationHelper, MissingBundleFinder, UploadAssetAttachments
from .models import LaundryRoom, LaundryGroup, Slot, Machine, TechnicianEmployeeProfile, \
HardwareBundlePairing, HardwareBundle, CardReaderAsset, MachineSlotMap, HardwareBundleRequirement, ValidTag, AssetMapOut, \
HardwareBundleChangesLog, BundleChangeApproval, SwapTagLog, AssetUpdateApproval, MachineAttachmentTracker
from .slot_finder import ConfigurationRecorder

logger = logging.getLogger(__name__)


class TechnicianUtil:

    @classmethod
    def get_technician(cls, codereadr_username):
        try:
            technician = TechnicianEmployeeProfile.objects.get(codereadr_username=codereadr_username)
        except TechnicianEmployeeProfile.DoesNotExist as e:
            with configure_scope() as scope:
                scope.set_extra("custom_message", f"There is not valid record for user: {codereadr_username}")
                scope.set_tag("custom_error_type", "invalid_codereader_username")
            capture_exception(e)
            technician = None
            subject = f'Invalid record/email for user {codereadr_username}'
            body_msg = f"A proper record for Codereader user {codereadr_username} has not been created \
            in the admin dashboard yet"
            msg = EmailMessage(
                    subject = subject,
                    body = body_msg,
                    to = settings.IT_EMAIL_LIST,
            )
            msg.send(fail_silently=True)
        except TechnicianEmployeeProfile.MultipleObjectsReturned as e:
            technician = TechnicianEmployeeProfile.objects.filter(codereadr_username=codereadr_username).first()        
        return technician

    @classmethod
    def check_email(cls, email):
        if not re.match(r'[^@]+@[^@]+\.[^@]+', email):
            notification = EmailMessage(
                subject = f'Invalid email addres for codereader user {email}',
                body = f'Invalid email addres for codereader user {email}',
                to = settings.IT_EMAIL_LIST,
            )
            notification.send(fail_silently=True)
            return False
        else:
            return True


class LaundryRoomConfigManager:
    DEFAULT_PROCEDURE_TEMPLATE_ID = 1003500

    @classmethod
    def _get_fascard_locations(cls, laundry_group_id):
        return PricingHistoryAPI(laundry_group_id).get_available_locations()

    @classmethod
    def create_room(cls, *args, **kwargs):
        try:
            room = LaundryRoom.objects.create(**kwargs)
            ext = LaundryRoomExtension.objects.create(laundry_room=room)
        except Exception as e:
            logger.info('Failed creating laundry room: {}'.format(e), exc_info=True)
            room = LaundryRoom.objects.get(**kwargs)
        if not room.upkeep_code:
            UpkeepManager().create_location(room)
        if not room.maintainx_id:
            logger.info("Creating maintainx location")
            MaintainxLocationManager().create_location(room)
            #automatic work order after room creation
            room.refresh_from_db()
            assert getattr(room, 'maintainx_id')
            logger.info(f"Created room with maintainx id: {room}")
            categories = [MaintainxDefaultCategories.STANDARD_OPERATING_PROCEDURE]
            maintainx_payload = {
                'title' : f'New Location: {room.display_name} Tasks',
                'locationId' : int(getattr(room, 'maintainx_id')),
                'categories' : categories,
                'priority' : MaintainxWorkOrderPriority.MEDIUM,
                'procedureTemplateId' : cls.DEFAULT_PROCEDURE_TEMPLATE_ID,
                'description' : """
                -Complete LaundryRoom Extension\n-Schedule recurring cleaner Work Order task\n-Schedule signage check\n-Schedule Scan all Machines Work order / task
                """
            }
            logger.info(f"Creating WO with payload: {maintainx_payload}")
            wo_manager = MaintainxWorkOrderManager()
            response = wo_manager.create_work_order(maintainx_payload)
            logger.info("Created work order")
            if not response: logger.info("WO creation Unsuccessful response")


    @classmethod
    def update_room(cls, laundry_room, **kwargs):
        if laundry_room.upkeep_code is None:
            logger.error("Room {} has no upkeep code".format(laundry_room))
            payload = {
                'laundry_group': laundry_room.laundry_group,
                'display_name': laundry_room.display_name,
                'fascard_code': laundry_room.fascard_code,
                'time_zone': laundry_room.time_zone
            }
            cls.create_room(**payload)
            return True

            #TODO: Fetch all locations and try to find one that matches the name, then assign upkeep code
        
        for k,v in kwargs.items():
            if hasattr(laundry_room, k):
                setattr(laundry_room, k, v)
        laundry_room.save()

        if kwargs.get('display_name') is not None:
            UpkeepManager().update_location(
                laundry_room,
                **{'name': laundry_room.display_name}
            )
            MaintainxLocationManager().update_location(
                laundry_room,
                **{'name': laundry_room.display_name}
            )
    
    @staticmethod
    def deactivate_room(laundry_room):
        if laundry_room.is_active:
            laundry_room.is_active = False
            laundry_room.save()
            logger.info('Deactivated Room: {}'.format(laundry_room))
            UpkeepManager().deactivate_location(laundry_room)
            MaintainxLocationManager().deactivate_location(laundry_room)
            

    @staticmethod
    def activate_room(laundry_room):
        if not laundry_room.is_active:
            laundry_room.is_active = True
            laundry_room.save()
            logger.info('Reactivated Room: {}'.format(laundry_room))
            UpkeepManager().activate_location(laundry_room)
            MaintainxLocationManager().activate_location(laundry_room)


class LaundryRoomSync(LaundryRoomConfigManager):

    def __init__(self, laundry_group_id):
        self.laundry_group_id = laundry_group_id
        self.laundry_group = LaundryGroup.objects.get(pk=self.laundry_group_id)
        self.available_fascard_locations = self._get_fascard_locations(self.laundry_group_id)
        self.fascard_locations_ids = [location['ID'] for location in self.available_fascard_locations]

    def deactivated_checker(self):
        for laundry_room in LaundryRoom.objects.filter(is_active=True, laundry_group=self.laundry_group):
            if laundry_room.fascard_code not in self.fascard_locations_ids:
                self.deactivate_room(laundry_room)

    def sync_name_or_create(self):
        for location in self.available_fascard_locations:
            fascard_location_name = location['Name'].encode("ascii", "ignore")
            try:
                obj = LaundryRoom.objects.get(
                    laundry_group=self.laundry_group,
                    fascard_code=location['ID']
                )
            except LaundryRoom.DoesNotExist:
                data = {
                    'laundry_group': self.laundry_group,
                    'display_name': fascard_location_name.decode(),
                    'fascard_code': location['ID'],
                    'time_zone': TimeZoneType.EASTERN
                }
                self.create_room(**data)
                continue
            
            if obj.display_name != fascard_location_name.decode():
                self.update_room(obj, **{'display_name':fascard_location_name.decode()})

    def get_available_locations(self):

        available_fascard_locations_ids = [location['ID']
                                          for location in self.available_fascard_locations]
        return LaundryRoom.objects.filter(
            laundry_group__id=self.laundry_group_id,
            is_active=True,
            fascard_code__in=available_fascard_locations_ids
        )

    @classmethod
    def run(cls, laundry_group_id, return_locations=False):
        try:
            ins = LaundryRoomSync(laundry_group_id)
            ins.sync_name_or_create()
            ins.deactivated_checker()
            if return_locations:
                return ins.get_available_locations()
        except Exception as e:
            logger.error(e, exc_info=True)
            raise Exception(e)


class LaundryRoomStatusFinderJob(LaundryRoomConfigManager):

    @classmethod
    def run_analysis(cls, laundry_room_id):
        try:
            laundry_room = LaundryRoom.objects.get(pk=laundry_room_id)
        except Exception as e:
            raise Exception(e)
        fascard_api_handler = FascardApi(laundry_room.laundry_group.id)
        room_data = fascard_api_handler.get_room(laundry_room.fascard_code, silent_fail=True)
        if 'ErrorCode' in room_data and room_data['ErrorCode'] == 903:
            cls.deactivate_room(laundry_room)
            logger.info(f"Deactivating room: {laundry_room}. ErrorCode 903")
            return
        try: satellite_data = fascard_api_handler.get_satellite(laundry_room.fascard_code)
        except: satellite_data = False
        if room_data['Enabled'] and not satellite_data:
            msg = EmailMessage(
                subject = f'Possible issue at room {laundry_room}',
                body = "The Room is Enabled according to the API but we couldn't get any Satellite Data",
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=settings.IT_EMAIL_LIST
            )
            msg.send(fail_silently=False)
        elif not room_data['Enabled'] and not satellite_data:
            cls.deactivate_room(laundry_room)
            logger.info(f"Deactivating room: {laundry_room}. No satellite data ")
        elif room_data['Enabled'] and satellite_data and not laundry_room.is_active:
            cls.activate_room(laundry_room)
            logger.info(f"Activating Room {laundry_room}")
        # try:
        #     machines_in_room = fascard_api_handler.get_slots_by_room(laundry_room.fascard_code)
        #     err = False
        # except Exception as e:
        #     cls.deactivate_room(laundry_room)
        #     err = True
        # if not err:
        #     processed_slots = [SlotDataStructure(machine_dict) for machine_dict in machines_in_room]
        #     if laundry_room.is_active:
        #         deactivated_machines = [True if slot.VendAllowed is False else False for slot in processed_slots]
        #         if all(deactivated_machines) or len(machines_in_room) < 1:
        #             cls.deactivate_room(laundry_room)
        #     else:
        #         reactivated_machines = [True if slot.VendAllowed is True else False for slot in processed_slots]
        #         if any(reactivated_machines):
        #             cls.activate_room(laundry_room)

#NOTE: Assets Scanning App Below
class BundlingProcessAbstract:
    pieces_map = {
        'slot' : HardwareType.SLOT,
        'machine' : HardwareType.MACHINE,
        'card_reader' : HardwareType.CARD_READER
    }
    optional_asset_fields = (
        'asset_picture',
        'asset_serial_picture',
    )
    default_language = LanguageChoices.ENGLISH

    def __init__(self, obj, extra_data):
        required_fields = getattr(self, 'required_fields', ())
        optional_asset_fields = getattr(self, 'optional_asset_fields', ())
        self.bundle_pairing_obj = obj
        for field in (required_fields + optional_asset_fields):
            if hasattr(self.bundle_pairing_obj, field):
                v = getattr(self.bundle_pairing_obj, field)
            else:
                v = extra_data.get(field)
            if field in self.required_fields:
                print (f"field: {field}. val: {v}")
                assert v is not None
            setattr(self, field, v)
        self._load_sucessful_msg()

    def _load_sucessful_msg(self):
        technician = getattr(self.bundle_pairing_obj, 'tech_employee')
        language = self.default_language
        if technician:
            language = technician.language
        self.success_msg = MessagesTranslationHelper.get(self.success_msg_key, language)

    def add_optional_fields(self, obj):
        fields = self.optional_asset_fields
        for field in fields:
            field_value = getattr(self, field)
            if field_value is not None:
                setattr(obj, field, field_value)
        obj.save()

    #@classmethod
    def create_hardware_bundle(self, slot, card_reader, machine, location, **kwargs):
        hardware_bundle = HardwareBundle.objects.create(
            slot = slot,
            card_reader = card_reader,
            machine = machine,
            location = location,
            **kwargs
        )
        self.add_optional_fields(machine)
        return hardware_bundle

    @classmethod
    def deactivate_hardware_bundle(cls, old_bundle):
        if old_bundle.is_active:
            now = datetime.utcnow()
            old_bundle.is_active = False
            old_bundle.end_time = now
            old_bundle.save()

    @classmethod
    def get_card_reader_asset(cls, card_reader_tag):
        card_reader, created = CardReaderAsset.objects.get_or_create(
                card_reader_tag = card_reader_tag
        )
        return card_reader

    def get_or_create_machine(self, asset_code, equipment_type, override_machine_type=None):
        #TODO: What if there is an existing machine with the asset_code being scanned
        #but with a different equipment type? The code will create a new machine anyway and that's wrong.
        try:
            machine = Machine.objects.get(
                asset_code = asset_code
            )
            current_equipment_types = machine.get_equipment_types()
            if current_equipment_types:
                for current_equipment_type in current_equipment_types:
                    current_type_string = current_equipment_type.machine_text.replace(' ', '').split('--')
                    equipment_type_string = equipment_type.machine_text.replace(' ', '').split('--')
                    if current_type_string[:2] != equipment_type_string[:2]:
                        if not override_machine_type or override_machine_type != MachineType.COMBO_STACK:
                            raise WrongEquipmentTypeForBundle(machine.asset_code, equipment_type)
            created = False
            if override_machine_type:
                machine.machine_type = override_machine_type
                machine.save()
        except Machine.DoesNotExist:
            machine_type = equipment_type.machine_type
            if override_machine_type: machine_type = override_machine_type
            machine = Machine.objects.create(
                equipment_type = equipment_type,
                machine_type = machine_type,
                asset_code = asset_code,
                placeholder = False
            )
            created = True
        except Exception as e:
            raise e
        return (machine, created)

    def get_current_equipment_type(self, slot, location=None):
        if location is None:
            assert hasattr(self, 'location')
            location = self.location
        fascard_api = FascardApi(1)
        slot_response = fascard_api.get_machine(
            slot.slot_fascard_id
            )
        assert 'EquipID' in slot_response
        equipment_id = slot_response['EquipID']
        equipment = get_equipment_type(
                equipment_id,
                location
        )
        return equipment

    @classmethod
    def deactivate_machineslotmap(cls, machineslotmap, time):
        if machineslotmap is not None:
            machineslotmap.end_time = time
            machineslotmap.save()

    @classmethod
    def orphane_hardware_piece(cls, hardware_piece_obj, hardware_piece_type, location=None, technician=None):
        raw_message = ORPHANE_MESSAGES[hardware_piece_type]

        if hardware_piece_type is HardwareType.MACHINE:
            assert isinstance(hardware_piece_obj, Machine)
            assert (location)
            if not hardware_piece_obj.asset_code:
                return
            orphane_message = raw_message.format(
                hardware_piece_obj.asset_code,
                location
            )
        elif hardware_piece_type is HardwareType.CARD_READER:
            assert isinstance(hardware_piece_obj, CardReaderAsset)
            assert (location)
            orphane_message = raw_message.format(
                hardware_piece_obj.card_reader_tag,
                location
            )
        elif hardware_piece_type is HardwareType.SLOT:
            assert isinstance(hardware_piece_obj, Slot)
            orphane_message = raw_message.format(
                hardware_piece_obj,
            )

        hb_req = HardwareBundleRequirement.objects.get_or_create(
            message = orphane_message,
            hardware_type = hardware_piece_type,
            hardware_id = hardware_piece_obj.id,
            done = False,
            assigned_technician = technician
        )

    @classmethod
    def orphane_pieces(cls, previous_bundle, leading_piece=None, location=None, technician=None):
        #assert leading_piece in cls.pieces_map.keys()
        assert location is not None
        for piece in set(cls.pieces_map.keys()) - set([leading_piece]):
            piece_obj = getattr(previous_bundle, piece)
            if not piece_obj:
                continue
            piece_type = cls.pieces_map.get(piece)
            params = (piece_obj,piece_type)
            if piece_type is not HardwareType.SLOT: params = params + (location,)
            if technician: params = params + (technician,)
            try:
                #If there is an outstanding hardware scanning requirement for the given piece
                #there is no need orphane it again
                try:
                    existing_requirement = HardwareBundleRequirement.objects.filter(
                        hardware_id = piece_obj.id,
                        hardware_type = piece_type,
                        done = False
                    ).first()
                except HardwareBundleRequirement.DoesNotExist:
                    existing_requirement=False
                if not existing_requirement:
                    cls.orphane_hardware_piece(*params)
            except Exception as e:
                logger.error(e)
                raise e

    def create_machineslotmap(self, time):
        new_msmap = MachineSlotMap.objects.create(
            slot = self.slot,
            machine = self.new_machine, 
            start_time=time)

    def update_machineslotmap(self, old_machineslotmap):
        now = datetime.utcnow()
        self.deactivate_machineslotmap(old_machineslotmap, now)
        self.create_machineslotmap(now)

    def check_previous_bundles(self, pieces=None, exclude_bundle_ids=[]):
        """
        Check if each individual piece is member of a previous bundle and deactivate the previous bundle
        while making the pieces on the previous bundle orphane and creating triple-scan requirements for Techs
        """
        if pieces is not None:
            pieces_list = pieces
        else:
            pieces_list = self.pieces_map.keys()
        for leading_piece in pieces_list:
            leading_piece_value = getattr(self, leading_piece, None)
            if not leading_piece_value:
                continue
            query_dict = {
                leading_piece: leading_piece_value,
                'is_active': True
            }
            previous_bundles = HardwareBundle.objects.filter(
                **query_dict
            ).exclude(id__in=exclude_bundle_ids).order_by('-start_time')
            if previous_bundles:
                for previous_bundle in previous_bundles:
                    self.orphane_pieces(
                        previous_bundle,
                        leading_piece,
                        self.location,
                        technician = self.bundle_pairing_obj.tech_employee,
                    )
                    self.deactivate_hardware_bundle(previous_bundle)
                    #self.orphane_pieces(previous_bundle, leading_piece)

    def add_machine_placeholder(self, obj):
        """
        Handles the special case when a slot has lost its machine to a new bundle and therefore
        a new slot. The previous slot gets a new placeholder machine object.
        """
        if isinstance(obj, Machine):
            piece = 'machine'
            query_dict = {
                piece: obj,
                'is_active': True
            }
            previous_msm = MachineSlotMap.objects.filter(**query_dict).order_by('-start_time').first()
            if not previous_msm:
                return
            previous_slot = previous_msm.slot

        if isinstance(obj, Slot):
            piece = 'slot'
            previous_slot = obj

        if previous_slot.laundry_room is not None and previous_slot.is_active: #Meaning the Slot still Exists/ Is active
            now = datetime.utcnow()
            previous_slot_equipment_type = self.get_current_equipment_type(
                previous_slot, 
                previous_slot.laundry_room
            )
            new_machine_placeholder = Machine.objects.create(
                equipment_type = previous_slot_equipment_type, 
                machine_type = previous_slot_equipment_type.machine_type
            )
            MachineSlotMap.objects.create(
                slot = previous_slot,
                machine = new_machine_placeholder,
                start_time=now
             )

    def _check_override_machine_type(self):
        override_machine_type = None
        if self.bundle_pairing_obj.combostack:
            override_machine_type = MachineType.COMBO_STACK
        return override_machine_type
        
    def render_template(self, response_payload):
        rendered_template = render_to_string(self.template, response_payload)
        return rendered_template

    def render_response(self):
        assert hasattr(self, 'new_bundle')
        assert hasattr(self, 'location')
        self.response_data = {
            'timestamp' : self.new_bundle.start_time,
            'location' : self.location,
        }

    def process(self):
        raise NotImplementedError

    def check_previous_machineslotmap(self):
        raise NotImplementedError

    def build_response_payload(self):
        raise NotImplementedError

    def post_process_log(self, old_piece_hardware_id: int = None, new_piece_hardware_id: int=None) -> None:
        change_log = HardwareBundleChangesLog.objects.create(
            hardware_type = self.hardware_type,
            old_piece_hardware_id = old_piece_hardware_id,
            new_piece_hardware_id = new_piece_hardware_id,
            old_bundle = self.previous_bundle,
            new_bundle = self.new_bundle,
            technician = self.bundle_pairing_obj.tech_employee,
            location = self.location,
            change_type = self.change_type
        )


class CardReaderChange(BundlingProcessAbstract):
    template = 'card_reader_changed.html'
    required_fields = (
        'previous_bundle',
        'card_reader_code',
        'location',
        'scan_type',
        'user_language'
    )
    optional_asset_fields = (
        'asset_serial_number',
    )
    #success_msg = _('Successfully changed the *Card Reader* of the hardware bundle')
    success_msg_key = 'successful_cardreader_change'
    change_type = ChangeType.CARD_READER_CHANGE
    hardware_type = HardwareType.CARD_READER


    @transaction.atomic
    def process(self) -> None:
        self.new_card_reader = self.get_card_reader_asset(self.card_reader_code)
        self.old_card_reader = self.previous_bundle.card_reader
        self.new_bundle = self.create_hardware_bundle(
            card_reader = self.new_card_reader,
            slot = self.previous_bundle.slot,
            machine = self.previous_bundle.machine,
            location = self.location,
            bundle_type = self.scan_type
        )
        self.deactivate_hardware_bundle(self.previous_bundle)
        
        self.orphane_hardware_piece(
            self.old_card_reader, 
            HardwareType.CARD_READER,
            self.previous_bundle.location,
            self.bundle_pairing_obj.tech_employee
        )
        self.post_process_log(
            old_piece_hardware_id = getattr(self.old_card_reader, 'id', None),
            new_piece_hardware_id = getattr(self.new_card_reader, 'id', None)
        )

    def render_response(self) -> str:
        super().render_response()
        extra_data = {
            'machine' : self.new_bundle.machine,
            'slot' : self.new_bundle.slot,
            'new_card_reader' : self.new_bundle.card_reader,
            'old_card_reader' : self.old_card_reader,
        }
        self.response_data.update(extra_data)
        rendered_string = render_to_string(self.template, self.response_data)
        return rendered_string


class MachineChange(BundlingProcessAbstract):
    """
    Control the models creation and notification when the machine
    was the only part that changed in a Hardware bundle
    """
    template = 'machine_changed.html'
    required_fields = (
        'previous_bundle',
        'asset_code',
        'location',
        'scan_type',
        'user_language'
    )
    optional_asset_fields = (
        'asset_picture',
        'asset_serial_picture',
        'asset_serial_number'
    )
    #success_msg = _('Successfully changed the *Machine* of the hardware bundle')
    success_msg_key = 'successful_machine_change'
    change_type = ChangeType.MACHINE_CHANGE
    hardware_type = HardwareType.MACHINE

    @transaction.atomic
    def process(self):
        self.slot = self.previous_bundle.slot
        equipment = self.get_current_equipment_type(self.slot)
        self.new_machine, machine_created = self.get_or_create_machine(
            self.asset_code,
            equipment,
            override_machine_type = self._check_override_machine_type())
        old_machine = self.previous_bundle.machine
        old_machineslotmap = MachineSlotMap.objects.filter(
                machine=old_machine,
                slot=self.slot).order_by(
                '-start_time').first()
        self.update_machineslotmap(old_machineslotmap)
        #self.add_optional_fields(self.optional_asset_fields, self.new_machine)
        self.new_bundle = self.create_hardware_bundle(
            slot = self.slot,
            card_reader = self.previous_bundle.card_reader,
            machine = self.new_machine,
            location = self.location,
            bundle_type = self.scan_type
        )
        self.deactivate_hardware_bundle(self.previous_bundle)
        self.orphane_hardware_piece(
            old_machine, 
            HardwareType.MACHINE,
            self.location,
            self.bundle_pairing_obj.tech_employee
        )
        self.post_process_log(
            old_piece_hardware_id = getattr(self.previous_bundle.machine, 'id', None),
            new_piece_hardware_id = getattr(self.new_machine, 'id', None)
        )

    def render_response(self):
        super().render_response()
        extra_data= {
            'old_machine' : self.previous_bundle.machine,
            'new_machine' : self.new_bundle.machine,
            'slot' : self.new_bundle.slot,
            'card_reader' : self.new_bundle.card_reader,
        }
        self.response_data.update(extra_data)
        rendered_string = render_to_string(self.template, self.response_data)
        return rendered_string


class SlotChange(BundlingProcessAbstract):
    template = 'slot_changed.html'
    required_fields = (
        'new_slot',
        'previous_bundle',
        'location',
        'scan_type',
        'user_language'
    )
    optional_asset_fields = (
        'asset_serial_number',
        'slot_being_replaced'
    )
    #success_msg = _('Successfully changed the *Slot* of the hardware bundle')
    success_msg_key = 'successful_slot_change'
    change_type = ChangeType.SLOT_CHANGE
    hardware_type = HardwareType.SLOT

    @transaction.atomic
    def process(self):
        self.card_reader = self.previous_bundle.card_reader
        self.machine = self.previous_bundle.machine
        self.old_slot = self.previous_bundle.slot
        now = datetime.utcnow()

        #For old_slot
        old_machineslotmap = MachineSlotMap.objects.filter(
            is_active = True,
            slot = self.old_slot,
            machine = self.machine
        ).order_by('-start_time').first()
        if old_machineslotmap:
            self.deactivate_machineslotmap(old_machineslotmap, now)
            if self.old_slot.laundry_room is not None and self.old_slot.is_active:
                self.add_machine_placeholder(self.old_slot)
                self.orphane_hardware_piece(
                    self.old_slot,
                    HardwareType.SLOT,
                    technician = self.bundle_pairing_obj.tech_employee
                )
        self.is_valid = True

        if self.scan_type in [BundleType.SINGLE, BundleType.STACK_DRYER, BundleType.STACK_DRYER_DUAL_POCKET]:
            #For new slot
            newslot_oldmachineslotmap = MachineSlotMap.objects.filter(
                is_active = True,
                slot = self.new_slot,
            ).order_by('-start_time').first()
            if newslot_oldmachineslotmap:
                self.deactivate_machineslotmap(newslot_oldmachineslotmap, now)
            
            existing_valid_machineslotmap = MachineSlotMap.objects.filter(
                machine = self.machine,
                slot = self.new_slot,
                is_active=True
            ).order_by('-start_time').first()

            self.slot = self.new_slot
            if not existing_valid_machineslotmap:
                self.new_machine = self.machine
                self.create_machineslotmap(now)

        if self.scan_type == BundleType.SINGLE:
            params = None
        else:
            params = ('slot',)
        self.check_previous_bundles(params)
        
        self.deactivate_hardware_bundle(self.previous_bundle)

        self.new_bundle = self.create_hardware_bundle(
            slot = self.new_slot,
            card_reader = self.card_reader,
            machine = self.machine,
            location = self.location,
            bundle_type = self.scan_type
        )
        self.post_process_log(
            old_piece_hardware_id = getattr(self.old_slot, 'id', None),
            new_piece_hardware_id = getattr(self.new_slot, 'id', None)
        )

    def render_response(self):
        super().render_response()
        extra_data = {
            'machine' : self.new_bundle.machine,
            'card_reader' : self.new_bundle.card_reader,
            'old_slot' : self.old_slot,
            'new_slot' : self.new_slot
        }
        self.response_data.update(extra_data)
        rendered_string = render_to_string(self.template, self.response_data)
        return rendered_string


class NewBundle(BundlingProcessAbstract):
    template = 'new_bundle.html'
    required_fields = (
        'old_machineslotmap',
        'slot',
        'card_reader_code',
        'asset_code',
        'location',
        'scan_type',
        'user_language'
    )
    optional_asset_fields = (
        'asset_serial_number',
    )
    #success_msg = _('Successfully created new hardware bundle')
    success_msg_key = 'successful_newbundle'
    change_type = ChangeType.NEW_BUNDLE

    def _fetch_dual_pocket_sibling(self):
        return HardwareBundle.objects.filter(
            is_active = True,
            machine__asset_code = self.machine.asset_code,
            card_reader__card_reader_tag = self.card_reader.card_reader_tag,
            bundle_type = BundleType.STACK_DRYER_DUAL_POCKET).last()

    @transaction.atomic
    def process(self):
        #There will always be an existing machineslotmap since slots are ingested
        #via Fascard API and a placeholder machine object is created. That data is stored
        #in 'oldmachineslotmap' field.
        oldmachine = self.old_machineslotmap.machine
        self.card_reader = self.get_card_reader_asset(self.card_reader_code)
        if oldmachine.asset_code != self.asset_code:
            equipment = self.get_current_equipment_type(self.slot)
            self.machine, created = self.get_or_create_machine(
                self.asset_code,
                equipment,
                override_machine_type = self._check_override_machine_type()
            )
            if not created:
                existing_hardware_bundle = False
                if self.scan_type == BundleType.STACK_DRYER:
                    #Checks if there is a HardwareBundle in the same location with the same machine
                    #If so, it means that HardwareBundle is the bundle peer of the stack dryer being scanned.
                    existing_hardware_bundle = HardwareBundle.objects.filter(
                        is_active=True,
                        location=self.location,
                        machine=self.machine,
                    )
                    #If the machine belongs to a hardware bundle different to the stack dryer's
                    #bundle peer, then that hardware bundle's slot should be deactivated.
                    if not existing_hardware_bundle: self.add_machine_placeholder(self.machine)
                elif self.scan_type == BundleType.STACK_DRYER_DUAL_POCKET:
                    existing_hardware_bundle = self._fetch_dual_pocket_sibling()
                if not existing_hardware_bundle: self.add_machine_placeholder(self.machine)
            old_machineslotmap = self.old_machineslotmap
            self.new_machine = self.machine
            self.update_machineslotmap(old_machineslotmap) #Updates MSM for Slot
        else:
            self.machine = oldmachine
            override_machine_type = self._check_override_machine_type()
            if override_machine_type:
                self.machine.machine_type = override_machine_type
                self.machine.save()
        exclude_bundle_ids = [] #Ids to be excluded from previous bundle checks
        #i.e Ids of bundles that shouldn't be orphaned by the check
        if self.scan_type == BundleType.STACK_DRYER:
            params = ('slot', 'card_reader')
            bundle_type = BundleType.STACK_DRYER
        elif self.scan_type == BundleType.STACK_DRYER_DUAL_POCKET:
            existing_dual_pocket_sibling = self._fetch_dual_pocket_sibling()
            params = ('slot', 'card_reader')
            if existing_dual_pocket_sibling:
                exclude_bundle_ids = [existing_dual_pocket_sibling.id]
            bundle_type = BundleType.STACK_DRYER_DUAL_POCKET
        else:
            params = None
            bundle_type = BundleType.SINGLE
        self.check_previous_bundles(params, exclude_bundle_ids)
        self.new_bundle = self.create_hardware_bundle(
            slot = self.slot,
            card_reader = self.card_reader,
            machine = self.machine,
            location = self.location,
            bundle_type = bundle_type
        )
        self.post_process_log()

    def render_response(self):
        super().render_response()
        extra_data = {
            'new_machine' : self.new_bundle.machine,
            'slot' : self.new_bundle.slot,
            'card_reader' : self.new_bundle.card_reader,
        }
        self.response_data.update(extra_data)
        rendered_string = render_to_string(self.template, self.response_data)
        return rendered_string

    def post_process_log(self):
        pass


class WarehouseBundle(BundlingProcessAbstract):
    template = 'warehouse_existingbundle.html'
    required_fields = (
        'previous_bundle',
        'location',
        'scan_type',
        'user_language'
    )
    optional_asset_fields = (
        'asset_picture',
        'asset_serial_picture',
    )
    change_type = ChangeType.WAREHOUSE
    hardware_type = None
    #success_msg = _('Successfully warehoused machine and card reader bundle')
    success_msg_key = 'successful_warehousing'

    @transaction.atomic
    def process(self):
        now = datetime.utcnow()
        self.old_slot = self.previous_bundle.slot
        self.machine = self.previous_bundle.machine
        self.card_reader = self.previous_bundle.card_reader

        #can add stacked dryers here.
        #For loop all the previous bundles from the stack dryer being scanned

        #For old_slot
        old_machineslotmap = MachineSlotMap.objects.filter(
            is_active = True,
            slot = self.old_slot,
            machine = self.machine
        ).order_by('-start_time').first()
        if old_machineslotmap:
            self.deactivate_machineslotmap(old_machineslotmap, now)
            if self.old_slot.laundry_room is not None and self.old_slot.is_active:
                self.add_machine_placeholder(self.old_slot)
                self.orphane_hardware_piece(
                    self.old_slot,
                    HardwareType.SLOT,
                    technician = self.bundle_pairing_obj.tech_employee,
                )
        self.is_valid = True


        if self.scan_type == BundleType.STACKED_WAREHOUSE:
            params = ('slot',)
            bundle_type = BundleType.STACKED_WAREHOUSE
            self.check_previous_bundles(params)
            self.deactivate_hardware_bundle(self.previous_bundle) #"Manually" deactivate prev HB
        else:
            params = None
            bundle_type = BundleType.WAREHOUSE
            self.check_previous_bundles(params)

        if self.bundle_pairing_obj.card_reader_code:
            card_reader = self.card_reader
            self.success_msg = 'Successfully warehoused machine and card reader bundle'
        else:
            card_reader = None
            self.success_msg = 'Successfully warehoused machine'

        self.new_bundle = self.create_hardware_bundle(
            slot = None,
            card_reader = card_reader,
            machine = self.machine,
            location = self.location,
            warehouse = self.location,
            bundle_type = BundleType.WAREHOUSE
        )
        asset_types = [(card_reader, HardwareType.CARD_READER), (self.machine, HardwareType.MACHINE)]
        for asset_type in asset_types:
            if asset_type[0]:
                latest_status_mapout = AssetMapOut.objects.filter(
                    active=True,
                    asset_type = asset_type[1],
                    asset_id = asset_type[0].id,
                    needs_rescanning=True
                ).order_by('-timestamp')
                for status in latest_status_mapout:
                    status.active = False
                    status.save()
        self.post_process_log()

    def render_response(self):
        super().render_response()
        extra_data = {
            'machine' : self.new_bundle.machine,
            'card_reader' : self.new_bundle.card_reader,
            'old_slot' : self.old_slot,
            'new_slot' : None
        }
        self.response_data.update(extra_data)
        rendered_string = render_to_string(self.template, self.response_data)
        return rendered_string

    #Get machine
    #Orphane previously associated slot
    #create a new warehouse_bundle flagged HardwareBundle that stores 
    #the warehouse location
    #Change machine's location in Upkeep.


class HardwareBundleManager():
    datamatrix_response_fields = (
        'LocationID',
        'MachineID',
    )

    input_fields = (
        'fascardReader',
        'assetTag',
        'dataMatrix'
    )

    #NOTE: This piece of code may be redundant. It was useful when
    #we were using jotform
    modelfieldsmap = {
        'card-reader-tag':'card_reader_code',
        'asset-tag': 'asset_code',
        'card-reader-data-matrix': 'data_matrix_string',
        'asset-picture': 'asset_picture',
        'asset-serial-picture': 'asset_serial_picture',
        'asset-serial-number' : 'asset_serial_number',
        'machine-description' : 'machine_description'
    }

    stackdryer_modelfieldsmap = {
            'card-reader-tag-A':'card_reader_code',
            'card-reader-tag-B':'card_reader_code',
            'data-matrix-A': 'data_matrix_string',
            'data-matrix-B': 'data_matrix_string',
            'asset-tag': 'asset_code',
            'asset-picture' : 'asset_picture',
            'asset-serial-picture' : 'asset_serial_picture',
            'asset-serial-number' : 'asset_serial_number',
            'warehouse' : 'warehouse',
            'ComboStack' : 'combostack',
            'machine-description' : 'machine_description'
    }

    warehouse_modelfieldsmap = {
        'card-reader-tag' : 'card_reader_code',
        'asset-tag' : 'asset_code',
        'asset-picture' : 'asset_picture',
        'asset-serial-picture' : 'asset_serial_picture',
        'warehouse' : 'warehouse'
    }

    ASSET_PICTURES_DECISION_MAP = {
        'asset_picture' : 'asset_picture_decision',
        'asset_serial_picture' : 'asset_serial_picture_decision',
    }

    extra_msg = ''
    bundle_change_email_template = "bundle_change_approval_email.html"
    asset_update_email_template = "asset_update_email.html"
    bundle_change_tech_email_template = "bundle_change_approval_tech_email.html"
    asset_update_tech_email_template = "asset_update_email.html"
    scans_pictures_s3_bucket = 'scans-pictures'

    def __init__(self, **kwargs):
        self.submission_id = kwargs.get('submissionid')
        self.codereadr_username = kwargs.get('codereadrusername')
        self.card_reader_code = kwargs.get('fascardreader')
        self.asset_code = kwargs.get('assettag')
        self.asset_picture = kwargs.get('assetpicture')
        self.asset_serial_picture = kwargs.get('assetserialpicture')
        self.data_matrix_string = kwargs.get('datamatrixstring')
        self.asset_serial_number = kwargs.get('assetserialnumber')
        self.asset_factory_model = kwargs.get('assetfactorymodel')
        self.machine_description = kwargs.get('machinedescription')
        self.scan_type = kwargs.get('scantype')
        self.warehouse = kwargs.get('warehouse')
        self.combostack = kwargs.get('combostack')
        self.file_transfer_type = kwargs.get('filetransfertype')
        self.file_transfer_upload_path = kwargs.get('fileuploadpath')
        self.dual_pocket_new_bundle = kwargs.get('dual_pocket_new_bundle', False)
        self.slot_being_replaced = kwargs.get('slot_being_replaced')
        self.asset_picture_decision = kwargs.get('asset_picture_decision')
        self.asset_serial_picture_decision = kwargs.get('asset_serial_picture_decision')
        if not self.combostack: self.combostack = False

    @staticmethod
    def string_to_hex(string):
        #utf_encoded = string.encode('utf-8')
        #hex_encoded = utf_encoded.hex()
        binary = str.encode(string)
        hex_encoded = binary.hex()
        return hex_encoded

    @staticmethod
    def parse_data_matrix(data_matrix):
        occurrences = re.findall('\<0x.*?\>',data_matrix)
        new_string = data_matrix
        for occurrence in occurrences:
            new_string= new_string.replace(
                occurrence, 
                chr(int(occurrence.strip('<>'), 0))
            )
        return new_string

    @classmethod
    def clean_singlebundle(cls, parsed_request, warehouse=False):
        if warehouse:
            fieldsmap = cls.warehouse_modelfieldsmap
        else:
            fieldsmap = cls.modelfieldsmap
        cleaned_codes = {}
        for parsed_key,v in parsed_request.items():
            for field_name in fieldsmap.keys():
                if field_name in parsed_key:
                    new_field_name = fieldsmap.get(field_name)
                    if new_field_name in ['asset_picture', 'asset_serial_picture']:
                        if len(v) > 0:
                            v = json.loads(v)
                            if not 'file_transfer_type' in cleaned_codes:
                                cleaned_codes['file_transfer_type'] = v.get('__crc_file_transfer_type__')
                                cleaned_codes['file_upload_path'] = v.get('upload_path')
                            v = v.get('link')
                        else:
                            v = None
                    cleaned_codes[new_field_name] = v
        return cleaned_codes

    @classmethod
    def clean_stackdryer(cls, parsed_request):

        pairs = {
            'A': {
                'card-reader-tag-A': None,
                'data-matrix-A': None,
                'asset-tag': None,
                'asset-picture': None,
                'asset-serial-picture': None,
                'warehouse': None,
                #'ComboStack' : False,
                'machine-description' : None
            },
            'B': {
                'card-reader-tag-B': None,
                'data-matrix-B': None,
                'asset-tag': None,
                'asset-picture': None,
                'asset-serial-picture': None,
                'warehouse': None,
                #'ComboStack' : False,
                'machine-description' : None
            }
        }
        new_pairs = {'A' : {}, 'B': {}}
        for pair_key in pairs.keys():
            for field_name in pairs[pair_key].keys():
                for parsed_field in parsed_request.keys():
                    if field_name in parsed_field:
                        new_field_name = cls.stackdryer_modelfieldsmap.get(field_name)
                        parsed_value = parsed_request.get(parsed_field)
                        if new_field_name in ['asset_picture', 'asset_serial_picture']:
                            if len(parsed_value) > 0:
                                parsed_value = json.loads(parsed_value)
                                if not 'file_transfer_type' in new_pairs[pair_key]:
                                    new_pairs[pair_key]['file_transfer_type'] = parsed_value.get('__crc_file_transfer_type__')
                                    new_pairs[pair_key]['file_upload_path'] = parsed_value.get('upload_path')
                                parsed_value = parsed_value.get('link')
                            else:
                                parsed_value = None
                            #parsed_value = json.loads(parsed_value).get('link')
                        #if new_field_name == 'combostack':
                        #    if parsed_value: parsed_value = True
                        new_pairs[pair_key][new_field_name] = parsed_value
                        #if new_field_name != field_name:
                        #    pairs[pair_key].pop(field_name)
        return new_pairs

    @classmethod
    def create_machineslotmap(cls, slot, new_machine):
        now = datetime.utcnow()
        new_machineslotmap = MachineSlotMap.objects.create(
            slot = slot, 
            machine = new_machine, 
            start_time=now
        )
        return new_machineslotmap

    @classmethod
    def deactivate_machineslotmap(cls, old_machineslotmap):
        now = datetime.utcnow()
        old_machineslotmap.end_time = now
        old_machineslotmap.save()
        return True

    def set_location(self, room_fascard_code):
        try:
            self.location = LaundryRoom.objects.get(fascard_code=room_fascard_code)
            if self.scan_type in [BundleType.WAREHOUSE, BundleType.STACKED_WAREHOUSE]:
                self.warehouse = self.location
            self.valid = True
        except LaundryRoom.DoesNotExist:
            self.err_msg = 'Invalid warehouse. Location does not exist in database'
            self.valid = False
            logger.error(self.err_msg)
        
    def check_missing_fields(self, obj_instance, fields=None):
        """
        -obj_instance can be HardwareBundlePairing or Machine
        """
        obj_pairing = None
        obj_instance.refresh_from_db()
        fields_messages_map = MissingAssetFieldNotifications
        if not fields:
            fields = list(fields_messages_map.keys())
        if isinstance(obj_instance, HardwareBundlePairing):
            try:
                if obj_instance.asset_code:
                    obj_pairing = obj_instance
                    obj_instance = Machine.objects.get(asset_code=obj_instance.asset_code)
            except Machine.DoesNotExist:
                pass
          
        if not obj_pairing: obj_pairing = self.object
        missing_fields = []
        for field in fields:
            if not getattr(obj_instance, field):
                if obj_pairing and not getattr(obj_pairing, field):
                    #if the field is not populated in the machine, check if its populated in the current scan submission
                    #if it's not populated in either model, then the field is missing for sure,
                    notification = fields_messages_map.get(field)
                    missing_fields.append(field)
                    self.extra_msg = self.extra_msg + "-{}. \n".format(
                        MessagesTranslationHelper.get(notification, self.user_language)
                    )
        return self.extra_msg, missing_fields

    def _handle_picture(self, machine, field, val):
        sync_to_maintainx = False
        decision_field = self.ASSET_PICTURES_DECISION_MAP.get(field)
        if hasattr(self, decision_field):
            decision_val = getattr(self, self.ASSET_PICTURES_DECISION_MAP.get(field))
            if not decision_val: return
            if decision_val == AssetPicturesChoice.ACCEPT_AND_REPLACE:
                #create asset attachment tracker
                #Syncing to maintainx is not required here, it's taken care later in the process
                #as like any other bundle-change or asset-update approval process.
                #Same logic as above for MachineAttachmentTracker
                setattr(machine, field, val)
                sync_to_maintainx = True #happening by default already?
            elif decision_val == AssetPicturesChoice.SAVE_DONT_REPLACE:
                #Syncing to maintainx is neccesary here since this is not like any other bundle change or asset update
                #Since the field in the machine object is not being updated/changed, it won't make sure the new pic is actually synced to maintainx
                #Same logic as above for MachineAttachmentTracker
                try:
                    #sync to maintainx
                    if not machine.maintainx_id:
                        setattr(machine, field, val)
                        return
                    binary_content = UploadAssetAttachments._read_picture(val)
                    filename = f'asset-attachment-{round(datetime.now().timestamp())}.jpg'
                    attachment_tracker = UploadAssetAttachments.upload_binary_data(machine.maintainx_id, binary_content, filename)
                    attachment_tracker.url = val
                    attachment_tracker.save()
                    #TODO change to URL ?
                except Exception as e:
                    logger.error(f"Failed to sync attachment to machine {machine} in Maintainx. Exception: {e}")
                sync_to_maintainx = True
                pass

    def update_missing_fields(self, fake_run=False):
        """
            asset_picture and asset_serial_picture usually get updated via CodeReadr scans
            asset_serial_number and asset_factory_model get updated via manual submission in bundle change approval screen
        """
        updated_fields = list()
        machine = Machine.objects.get(asset_code=self.object.asset_code)
        picture_fields = ['asset_picture', 'asset_serial_picture']
        other_fields = ['asset_serial_number', 'asset_factory_model', 'machine_description']
        #NEED TO USE DECISION MADE RE PICS TO HANDLE BELOW
        for field in picture_fields + other_fields:
            val = getattr(self.object, field)
            if getattr(machine, field) is None or getattr(machine, field) != val:
                if val:
                    if not fake_run:
                        if field in picture_fields: self._handle_picture(machine, field, val)
                        else: setattr(machine, field, val)
                    updated_fields.append(field)
        if len(updated_fields) == 0:
            updated_fields = None
        else:
            if not fake_run: machine.save()
        return True, updated_fields


    def get_technician(self):
        tech = TechnicianUtil.get_technician(self.codereadr_username)
        return tech

    def get_datamatrix_response(self, data_matrix_code):
        fascard_api_client = FascardApi(1)#TODO: Build logic so laundry_group_id does not need to be hardcoded
        return fascard_api_client.get_datamatrix_info(data_matrix_code)

    def slot_exists(self, slot_fascard_id):
        slot = Slot.objects.filter(slot_fascard_id=slot_fascard_id).first()
        if slot:
            return slot
        else:
            return False

    @ProductionCheck
    def send_email(self, rendered_response):
        if self.object.tech_employee:
            tech_email = self.object.tech_employee.notifications_email
            if tech_email is not None:
                to_email = tech_email
        else:
            to_email = self.object.codereadr_username
            TechnicianUtil.check_email(to_email)
        assert to_email is not None
        #TODO: Change this for tech's email
        #to_email = 'suricatadev@gmail.com'
        message = EmailMessage(
            subject = 'Hardware Bundling Scan Response',
            body = rendered_response,
            to = [to_email],
        )
        message.content_subtype = "html"
        message.send(fail_silently=False)

    def create_work_order(self, payload):
        """
        Bundle Change or Asset Update Approval work order.
        """
        wo_payload = {'title' : payload.get('title'), 'description' : payload.get('description')}
        wo_payload['categories'] = [MaintainxDefaultCategories.BUNDLE_CHANGE_OR_ASSET_UPDATE]
        wo_payload['priority'] = MaintainxWorkOrderPriority.MEDIUM
        wo_payload['assignees'] = [{"type": "TEAM", "id": settings.MAINTAINX_ADMIN_TEAM_ID}]
        obj = payload.get('approval_object')
        wo_location = obj.scan_pairing.location
        if wo_location.maintainx_id: wo_payload['locationId'] = int(wo_location.maintainx_id)
        wo_manager = MaintainxWorkOrderManager()
        rid = wo_manager.create_work_order(wo_payload)
        obj.associated_work_order_maintainx_id = rid
        obj.save()

    def send_bundle_action_notification(self, notification_payload):
        assert notification_payload.get('email_template')
        assert notification_payload.get('technician_notification_email_template')
        assert notification_payload.get('approval_object')
        assert notification_payload.get('main_email_subject')
        main_email_data = {'obj': notification_payload.get('approval_object')}
        if 'extra' in notification_payload: main_email_data['extra'] = notification_payload.get('extra')
        rendered_response = render_to_string(notification_payload.get('email_template'), main_email_data)
        to = settings.DEFAULT_TO_EMAILS.copy()
        if settings.IS_PRODUCTION: to = settings.DEFAULT_BUNDLE_CHANGE_REQ_EMAILS
        payloads = [
            {'subject' : notification_payload.get('main_email_subject'), 'body' : rendered_response, 'to' : to},
        ]
        if self.object and self.object.tech_employee and self.object.tech_employee.notifications_email:
            tech_rendered_response = render_to_string(
                notification_payload.get('technician_notification_email_template'),
                {'obj': notification_payload.get('approval_object')}
            )
            payloads.append({
                'subject' : notification_payload.get('technician_email_subject'),
                'body' : tech_rendered_response,
                'to' : [self.object.tech_employee.notifications_email]
            })
        for payload in payloads:
            logger.info(f"Sending Email Notification: {payload['subject']}. To: {payload['to']}")
            email_thread = EmailThread(**payload)
            email_thread.content_type = "html"
            email_thread.start()
        return True


    def send_bundle_change_notification(self, bundle_change_approval):
        payload = {
            'approval_object' : bundle_change_approval,
            'email_template': self.bundle_change_email_template,
            'main_email_subject': '[URGENT] Action needed on a new Bundle Change request',
            'technician_notification_email_template': self.bundle_change_tech_email_template,
            'technician_email_subject' : MessagesTranslationHelper.get('bundle_requires_approval', self.user_language)
        }
        self.send_bundle_action_notification(payload)

    def asset_update_approval(self, bundle, updated_fields):
        outstanding_update_change = AssetUpdateApproval.objects.filter(approved=False, rejected=False, bundle=bundle)
        outstanding_update_change = outstanding_update_change.order_by('-timestamp').first()
        asset_update_approval = AssetUpdateApproval.objects.create(bundle=bundle, scan_pairing=self.object)
        if outstanding_update_change:
            outstanding_update_change.superseded_by = asset_update_approval
            outstanding_update_change.save()
        email_payload = {
            'approval_object' : asset_update_approval,
            'email_template': self.asset_update_email_template,
            'main_email_subject': '[URGENT] Action needed on a new Bundle Update request',
            'technician_notification_email_template': self.asset_update_tech_email_template,
            'technician_email_subject' : MessagesTranslationHelper.get('asset_update_requires_approval', self.user_language),
            'extra' : {'updated_attributes': updated_fields}
        }
        self.send_bundle_action_notification(email_payload)
        work_order_payload = {
            'approval_object' : asset_update_approval,
            'description' : f'https://system.aceslaundry.com/roommanager/asset-update-approval/{asset_update_approval.id}/',
            'title' : '[URGENT] Action needed on a new Bundle Update request',
        }
        self.create_work_order(work_order_payload)

    def process_asset_update_approval(self, hardware_bundle, requires_approval):
        """Specifically handles the cases related to the AssetUpdateApproval model"""
        self.msg = MessagesTranslationHelper.get('pieces_bundled', self.user_language)
        self.valid = False
        self.notify = False
        updated_fields = []
        if requires_approval:
            #TODO: Check that there are actual changes happening.
                #cant't raise this just by having a simple scan with the same data as the current bundle
            logger.info(f"Current scan requires_approval?: {requires_approval}")
            response, updated_fields = self.update_missing_fields(fake_run=True)
            if updated_fields:
                logger.info(f"Fields being updated: {updated_fields}. Successful?: {response}")
                self.asset_update_approval(hardware_bundle, updated_fields)
                self.msg += ". {}".format(MessagesTranslationHelper.get('asset_update_approval_sent', self.user_language))
        else:
            success, updated_fields = self.update_missing_fields()
            if success and updated_fields:
                self.msg = self.msg + ".\n UPDATED FIELDS: \n"
                for field in updated_fields:
                    self.msg = self.msg + "-{} \n".format(field)
                #sync to maintainx
                from .signals import process_machine_thread
                machine = Machine.objects.get(asset_code=self.object.asset_code)
                machine.refresh_from_db()
                process_machine_thread([machine])
        fields_to_check = ['asset_picture', 'asset_serial_picture']
        if updated_fields:
            fields_to_check = set(['asset_picture', 'asset_serial_picture']) - set(updated_fields)
            fields_to_check = list(fields_to_check)
        extra, missing_fields = self.check_missing_fields(hardware_bundle.machine, fields=fields_to_check)
        if extra != '':
            self.msg = self.msg + f".\n {MessagesTranslationHelper.get('missing_fields', self.user_language)} \n" + extra
        return

    def _check_cardreader_change(self):
        if self.object.slot:
            #CardReaderChange
            case1 = HardwareBundle.objects.filter(
                is_active = True,
                machine__asset_code = self.object.asset_code,
                slot = self.object.slot
            ).last()
        else:
            case1 = False
        return case1

    def _check_slot_change(self):
        return HardwareBundle.objects.filter(
            is_active = True,
            machine__asset_code = self.object.asset_code,
            card_reader__card_reader_tag = self.object.card_reader_code
        )  

    def _check_machine_change(self):
        return HardwareBundle.objects.filter(
            is_active = True,
            slot = self.object.slot,
            card_reader__card_reader_tag = self.object.card_reader_code
        ).last()

    def _check_warehouse_scan(self):
        if self.scan_type == BundleType.WAREHOUSE:
            case4 = HardwareBundle.objects.filter(
                is_active = True,
                machine__asset_code = self.object.asset_code,
            ).exclude(bundle_type=BundleType.WAREHOUSE).last()
        else:
            case4 = False
        return case4
    

    def pair(self, requires_approval=True):
        logger.info("Pairing")
        print ("Pairing")
        self.notify = True
        #machineslotmap = MachineSlotMap.objects.filter(slot=self.slot).last() #Assuming that all active slots have machineslotmap
        if self.scan_type in [BundleType.SINGLE, BundleType.STACK_DRYER, BundleType.STACK_DRYER_DUAL_POCKET]:
            machineslotmap = MachineSlotMap.objects.filter(
                slot=self.object.slot
            ).order_by('-start_time').first()            
            if not machineslotmap:
                self.msg = MessagesTranslationHelper.get('msm_doesnt_exist', self.user_language)
                self.valid = False
                return

            hardware_bundle = HardwareBundle.objects.filter(
                slot = self.object.slot,
                card_reader__card_reader_tag = self.object.card_reader_code,
                machine__asset_code = self.object.asset_code,
                is_active = True
            ).last()
            if hardware_bundle:
                self.process_asset_update_approval(hardware_bundle, requires_approval)
                return

        #TODO: Case zero warehouse case
        case1 = self._check_cardreader_change()
        #SlotChange
        case2 = self._check_slot_change()
        #This case is triggered by scanning a dual pocket, since there are two different slots
        #and the scan is broken into two pieces. When the first part gets approved, there is no issue
        #but when the second part is approved, the piece of code above assumes that second part
        #is actually an slot change, since the card_reader and machine stay the same and only the slot changes
        #Solution: Decide here whether this is an actual slot change or the
        #only existing bundle is simply the sibling dual pocket scan.
        if case2:
            if case2.last().bundle_type == BundleType.STACK_DRYER_DUAL_POCKET and self.scan_type == BundleType.STACK_DRYER_DUAL_POCKET:
                if self.dual_pocket_new_bundle:
                    case2 = False
                else:
                    if self.slot_being_replaced:
                        case2 = case2.filter(slot__slot_fascard_id=self.slot_being_replaced).last()
            else:
                case2 = case2.last()
        #MachineChange
        case3 = self._check_machine_change()
        case4 = self._check_warehouse_scan()
        extra_data = {'user_language' : getattr(self, 'user_language', LanguageChoices.ENGLISH)}
        if case1:
            #Machine and Slot stay the same and only card reader changes
            extra_data.update({'previous_bundle' : case1})
            bundle_process = CardReaderChange(self.object, extra_data)
        elif case2:
            #Machine and CardReader stay the same. Only slot changed.
            extra_data.update({'previous_bundle' : case2})
            if self.scan_type in [BundleType.WAREHOUSE, BundleType.STACKED_WAREHOUSE]:
                extra_data.update({'new_slot' : None})
                bundle_process = WarehouseBundle(self.object, extra_data)
            else:
                extra_data.update({'new_slot' : self.object.slot})
                bundle_process = SlotChange(self.object, extra_data)
            #TODO: Check if changing the equipment type of the slot changes its data matrix
            #most likely it does
        elif case3:
            #Slot and Card Reader stay the same and only machine changes
            extra_data.update({'previous_bundle' : case3})
            bundle_process = MachineChange(self.object, extra_data)
        elif case4:
            #A machine (with no card reader) is being scanned into the warehouse and 
            #was previously bundled in a laundry room.
            extra_data.update({'previous_bundle' : case4})
            if self.scan_type == BundleType.WAREHOUSE:
                bundle_process = WarehouseBundle(self.object, extra_data)
        else:
            #TODO: Still need to manage warehouse borne machines.
            if self.scan_type in [BundleType.WAREHOUSE, BundleType.STACKED_WAREHOUSE]:
                self.msg = MessagesTranslationHelper.get('warehouse_born_prohibited', self.user_language)
                self.valid = False
                return
            #requires_approval = False #New scans now require approval.
            old_machineslotmap = machineslotmap
            extra_data.update({
                'old_machineslotmap' : old_machineslotmap
            })
            bundle_process = NewBundle(self.object, extra_data)
        logger.info("decided case")
        try:
            if requires_approval:
                logger.info("entered requires approval if statement")
                if isinstance(bundle_process, NewBundle):
                    outstanding_bundle_change = BundleChangeApproval.objects.filter(
                        approved=False,
                        rejected=False,
                        change_type = bundle_process.change_type,
                        scan_pairing__card_reader_code = self.object.card_reader_code,
                        scan_pairing__asset_code = self.object.asset_code,
                        scan_pairing__slot = self.object.slot,
                    )
                else:
                    outstanding_bundle_change = BundleChangeApproval.objects.filter(
                        approved=False,
                        rejected=False,
                        previous_bundle = bundle_process.previous_bundle
                    )
                outstanding_bundle_change = outstanding_bundle_change.order_by('-timestamp').first()
                bundle_change_approval = BundleChangeApproval.objects.create(
                    previous_bundle = getattr(bundle_process, 'previous_bundle', None),
                    scan_pairing = self.object,
                    change_type = bundle_process.change_type
                )
                self.msg = f'Pieces Bundled:\nSlot: {self.object.slot}.\nMachine: {self.object.asset_code}.\nCard Reader: {self.object.card_reader_code}. \n'
                if outstanding_bundle_change:
                    #If there is an outstanding bundle change approval request we always supersede it
                    #with the newest scan, assuming the newest one is better than the previous.
                    outstanding_bundle_change.superseded_by = bundle_change_approval
                    outstanding_bundle_change.save()
                    self.msg += MessagesTranslationHelper.get('bundle_approval_overwritten', self.user_language)
                self.msg += MessagesTranslationHelper.get('enqueued_bundled', self.user_language).format(
                    bundle_process.change_type)
                logger.info("fetching missing fields")
                extra, missing_fields = self.check_missing_fields(bundle_change_approval.scan_pairing, fields=['asset_picture', 'asset_serial_picture'])
                self.missing_asset_fields = missing_fields
                # if extra != '':
                #     self.msg = self.msg + f"\n. {MessagesTranslationHelper.get('missing_fields', self.user_language)} \n" + extra
                self.valid = True
                self.send_bundle_change_notification(bundle_change_approval)
                logger.info("sent bundle change notification")
                work_order_payload = {
                    'approval_object' : bundle_change_approval,
                    'description' : f'https://system.aceslaundry.com/roommanager/bundle-change-approval/{bundle_change_approval.id}/',
                    'title' : '[URGENT] Action needed on a new Bundle Change request',
                }
                self.create_work_order(work_order_payload)
                return
            bundle_process.process()
            self.valid = True
        except WrongEquipmentTypeForMachine as e:
            self.valid = False
            self.err_msg = MessagesTranslationHelper.get('scanning_failed', self.user_language).format(e)
        except Exception as e:
            self.valid = False
            logger.error('Exception in Bundling/Scanning: {}'.format(e), exc_info=True)
            #raise Exception(e) #TODO: Change back
            self.err_msg = MessagesTranslationHelper.get('unknown_exception', self.user_language).format(e)
            return

        if self.notify:
            if self.valid:
                assert bundle_process
                try:
                    rendered_response = bundle_process.render_response()
                    self.send_email(rendered_response)
                    self.object.notification_sent = True
                    self.object.save()
                    self.msg = bundle_process.success_msg
                    self.update_missing_fields()
                    extra, missing_fields = self.check_missing_fields(bundle_process.new_bundle.machine)
                    if extra != '':
                        self.msg = self.msg + f".\n {MessagesTranslationHelper.get('missing_fields', self.user_language)} \n" + extra
                except Exception as e:
                    failure = traceback.format_exc()
                    logger.error(failure)
                    logger.error("Failed scanning process. Exception: {}".format(e), exc_info=True)
                    self.err_msg = 'Unknown exception: {}'.format(e)

    def _set_user_language(self):
        technician = getattr(self.object, 'tech_employee')
        self.user_language = LanguageChoices.ENGLISH
        if technician: self.user_language = technician.language

    def _s3_picture_handler(self, asset_code, pic_link):
        s3_client = boto3.client('s3')
        if not asset_code: return pic_link
        upload_path = self.file_transfer_upload_path.replace('/','').replace('\\', '')
        file_name = pic_link.split('/')[-1]
        existing_file_full_name = '/'.join([upload_path, file_name])
        new_file_name = '/'.join([asset_code, file_name])
        response = s3_client.copy_object(
            ACL='public-read',
            Bucket=self.scans_pictures_s3_bucket,
            CopySource='/'.join([self.scans_pictures_s3_bucket, existing_file_full_name]),
            Key=new_file_name,
        )['ResponseMetadata']
        if response['HTTPStatusCode'] == 200:
            return f'https://{self.scans_pictures_s3_bucket}.s3.amazonaws.com/{new_file_name}'
        else:
            return pic_link

    def save_model(self):
        if self.file_transfer_type == 's3':
            for field in ['asset_picture', 'asset_serial_picture']:
                val = getattr(self, field)
                if val:
                    val = self._s3_picture_handler(self.asset_code, val)
                    setattr(self, field, val)
        object_payload = self.__dict__.copy()
        object_payload.pop('user_language')
        self.object = HardwareBundlePairing.objects.create(**object_payload)

    def valid_slot(self, slot_fascard_id, room_fascard_code, last_attempt=False):
        self.valid = True
        slot = self.slot_exists(slot_fascard_id) #TODO: Ask Daniel what to do if the slot does not exists
        if slot and slot.is_active:
            self.slot = slot
        elif slot and slot.is_active == False:
            self.err_msg = MessagesTranslationHelper.get('slot_inactive', LanguageChoices.ENGLISH)
            self.valid = False
        else:
            if not last_attempt:
                try:
                    location = LaundryRoom.objects.get(fascard_code=room_fascard_code)
                    ConfigurationRecorder.record_slot_configuration(location.id) #TODO: Needs to make sure the LaundryRoom exists
                    self.valid_slot(slot_fascard_id, room_fascard_code, last_attempt=True) #TODO: Needs to be tested
                except Exception as e:
                    self.err_msg = e
                    self.valid=False
            else:
                self.err_msg = MessagesTranslationHelper.get('slot_doesnt_exist', LanguageChoices.ENGLISH)
                self.valid = False
        return self.valid


    def validate_data(self):
        self.tech_employee = self.get_technician()
        self.user_language = None
        if self.tech_employee and self.tech_employee.language: self.user_language = self.tech_employee.language
        else: self.user_language = LanguageChoices.ENGLISH
        try:
            cr_tag = ValidTag.objects.get(tag_string=self.card_reader_code)
        except ValidTag.DoesNotExist:
            self.err_msg = MessagesTranslationHelper.get('no_valid_tag_record', self.user_language) % {'tag': self.card_reader_code}
            self.valid = False
            return       
        try:
            machine_tag = ValidTag.objects.get(tag_string=self.asset_code)
        except ValidTag.DoesNotExist:
            self.err_msg = MessagesTranslationHelper.get('no_valid_tag_record', self.user_language) % {'tag': self.asset_code}
            self.valid = False
            return

        if not (self.card_reader_code != self.asset_code):
            self.err_msg = MessagesTranslationHelper.get('codes_are_the_same', self.user_language)
            self.valid = False
            return

        if self.asset_code and self.card_reader_code:
            try:
                cr = CardReaderAsset.objects.get(card_reader_tag=self.asset_code)
                self.valid = False
                self.err_msg = MessagesTranslationHelper.get('card_reader_tag_as_machine', self.user_language)
                return
            except CardReaderAsset.DoesNotExist:
                pass

        if self.scan_type in [BundleType.WAREHOUSE, BundleType.STACKED_WAREHOUSE]:
            id_text = re.findall('\(id:.*?\)', self.warehouse)[0].strip('()').split(':')
            room_fascard_code = id_text[-1]
            self.slot = None
        else:
            self.data_matrix_string = self.parse_data_matrix(self.data_matrix_string)
            str_to_hex = self.string_to_hex(self.data_matrix_string)
            try:
                datamatrix_response = self.get_datamatrix_response(str_to_hex)
            except Exception as e:
                logger.error(f'Failed getting a data matrix response from Fascard api for hex: {str_to_hex}')
                datamatrix_response = None

            if datamatrix_response:
                slot_fascard_id = datamatrix_response.get('MachineID')
                room_fascard_code = int(datamatrix_response.get('LocationID'))
                if not self.valid_slot(slot_fascard_id, room_fascard_code):
                    if not self.err_msg: self.err_msg = 'Invalid Slot'
                    return
            else:
                self.err_msg = MessagesTranslationHelper.get('datamatrix_doesnt_exists', self.user_language)
                self.valid = False
                return
        self.set_location(room_fascard_code)


class HardwareBundleJobProcessor(HardwareBundleManager):

    @classmethod
    def job_scheduler(cls, payload):
        from queuehandler.job_creator import SlotMachinePairingEnqueuer
        # SlotMachinePairingEnqueuer.enqueue_pairing_process(payload)
        response, missing_fields = cls.job_receiver(**payload)
        return response, missing_fields

    @classmethod
    def job_receiver(cls, **kwargs):
        ins = HardwareBundleManager(**kwargs)
        ins.validate_data()
        # print ("final data dict: {}".format(ins.__dict__))
        if ins.valid:
            msg = ''
            ins.save_model()
            ins.pair()
            if hasattr(ins, 'err_msg'):
                msg = ins.err_msg
            elif hasattr(ins, 'msg'):
                msg = ins.msg
            if hasattr(ins, 'location'):
                missing_scans = MissingBundleFinder().get(ins.location)
                if missing_scans: msg += "\n Slots that need to be scanned: \n" + missing_scans
            missing_fields = ins.missing_asset_fields if hasattr(ins, 'missing_asset_fields') else None
            return msg, missing_fields
        else:
            try:
                #Try to save failed scan if possible / debugging purposes
                ins.save_model()
            except:
                pass
            err_str = "There was an error: {}".format(ins.err_msg)
            logger.error(err_str)
            ins.send_email(err_str)
            return err_str, []


class BasicManager:

    def __init__(self, request: dict, tech_username: str=None, user: User=None):
        if tech_username and user: user=None
        if not tech_username and not user: raise Exception("Need at least one form of user parameter")
        self.request = request
        self.codereadr_username = tech_username
        self.user = user
        self._set_user_settings()
        self.clean_codes()

    def _set_user_settings(self):
        self.user_language = LanguageChoices.ENGLISH
        if self.codereadr_username:
            self.technician = TechnicianUtil.get_technician(self.codereadr_username)
            self.user_language = self.technician.language
            if self.technician.notifications_email:
                self.to_email = self.technician.notifications_email
            else:
                if TechnicianUtil.check_email(self.codereadr_username):
                    self.to_email = self.codereadr_username
        if self.user: self.to_email = self.user.email

    def clean_codes(self):
        parsed_request = self.request
        fieldsmap = self.fields_map
        for parsed_key,v in parsed_request.items():
            for field_name in fieldsmap.keys():
                if field_name in parsed_key:
                    new_field_name = fieldsmap.get(field_name)
                    setattr(self, new_field_name, v)

    def get_machine(self, asset_tag):
        machine = Machine.objects.filter(asset_code=asset_tag).first()
        return machine

    def get_card_reader(self, asset_tag):
        card_reader = CardReaderAsset.objects.filter(card_reader_tag=asset_tag).first()
        return card_reader

    def get_object(self, asset_tag):
        machine = self.get_machine(asset_tag)
        card_reader = self.get_card_reader(asset_tag)
        if machine: return machine
        elif card_reader: return card_reader
        return None

    def cmms_sync(self):
        from .signals import process_machine_thread
        process_machine_thread([self.current_obj])

    def slot_fascard_sync(self):
        from .signals import process_slot_thread
        if isinstance(self.current_obj, Machine):
            bundles = self.current_obj.get_current_bundles()
            asset_code = self.current_obj.asset_code
            if not asset_code: asset_code = 'Unknown'
            for bundle in bundles:
                final_label = f"#{getattr(bundle.slot, 'web_display_name', '')} -- ({asset_code})"
                if bundle:
                    process_slot_thread(
                        bundle.slot,
                        asset_code,
                        getattr(self.current_obj, 'asset_serial_number', ''),
                        getattr(self.current_obj, 'asset_factory_model', ''),
                    )

    def validate_data(self):
        raise NotImplementedError


class SwapTagManager(BasicManager):
    fields_map = {
        'current_tag' : 'current_tag',
        'new_tag' : 'new_tag'
    }

    def validate_data(self):
        self.current_obj = self.get_object(self.current_tag)
        self.new_obj = self.get_object(self.new_tag)

        if not self.current_obj:
            self.valid = False
            self.msg = MessagesTranslationHelper.get('invalid_current_tag', self.user_language)
            return
        if self.new_obj:
            self.valid = False
            self.msg = MessagesTranslationHelper.get('invalid_new_tag', self.user_language)
            return

        self.valid = True

    def swap(self):
        if isinstance(self.current_obj, Machine):
            self.current_obj.asset_code = self.new_tag
        elif isinstance(self.current_obj, CardReaderAsset):
            self.current_obj.card_reader_tag = self.new_tag
        self.current_obj.save()
        r = ValidTag.objects.get_or_create(tag_string=self.new_tag)
        return True

    def render_response(self):
        string = MessagesTranslationHelper.get('tag_swap', self.user_language) % {'current_tag': self.current_tag, 'new_tag': self.new_tag}
        #string =   "Previous tag: {self.current_tag}. New Tag: {self.new_tag}"
        return string

    def send_email(self):
        if self.to_email:
            message = EmailMessage(
                subject = self.email_subject,
                body = self.email_body,
                to = [self.to_email],
            )
            #message.content_subtype = "html"
            message.send(fail_silently=False) 

    @transaction.atomic
    def process(self, requires_approval=True):
        assert [hasattr(self, field) for field in self.fields_map.keys()]
        self.validate_data()
        if self.valid:
            if requires_approval:
                SwapTagLog.objects.create(
                    current_tag = self.current_tag,
                    new_tag = self.new_tag,
                    tech_username = self.codereadr_username
                )
                self.email_subject = MessagesTranslationHelper.get('tag_swap_approval_email_subject', self.user_language)
                #self.email_body = f"{self.render_response()}. Tag Swap Enqueued for approval. Please call to the office"
                self.email_body = MessagesTranslationHelper.get('tag_swap_approval_email_body', self.user_language) % {'rendered_response': self.render_response()}
                self.send_email()
                return self.email_body
            swapped = self.swap()
            if swapped:
                self.email_subject = MessagesTranslationHelper.get('successful_tag_swap', self.user_language)
                self.email_body = self.render_response()
                self.send_email()
                self.cmms_sync()
                return MessagesTranslationHelper.get('successful_tag_swap', self.user_language)
        else:
            return MessagesTranslationHelper.get(
                'unsuccessful_tag_swap', self.user_language
            ) + f": {self.msg}"


class MapOutAsset(BasicManager):
    DISPOSED = AssetMapOutChoices.DISPOSED
    EN_ROUTE = AssetMapOutChoices.EN_ROUTE
    PICKUP = AssetMapOutChoices.PICKUP
    UPKEEP_WORK_ORDER_CATEGORIES = {
        'disposed' : 'machine map-out — Disposed',
        'en-route-to-wareouse' : 'machine map-out — en route to Warehouse',
        'mark-for-pickup' : 'machine map-out — mark for pickup'
    }
    fields_map = {
        'asset-map-out' : 'asset_map_out',
        'asset-tag' : 'asset_tag',
        'description' : 'description',
    }

    def clean_codes(self):
        super().clean_codes()
        self.asset_map_out = '-'.join(self.asset_map_out.lower().split())

    def validate_data(self):
        self.valid = False
        self.current_obj = self.get_object(self.asset_tag)
        if not self.current_obj:
            self.msg = MessagesTranslationHelper.get('invalid_current_tag', self.user_language)
            return
        self.asset = self.get_object(self.asset_tag)
        if isinstance(self.asset, Machine): self.asset_type = HardwareType.MACHINE
        elif isinstance(self.asset, CardReaderAsset): self.asset_type = HardwareType.CARD_READER
        self.hardware_bundle = self.asset.hardwarebundle_set.all().order_by('-start_time').first()
        if self.hardware_bundle:
            hb_bundle_type = self.hardware_bundle.bundle_type
            if self.asset_map_out == self.EN_ROUTE and hb_bundle_type in [BundleType.WAREHOUSE, BundleType.STACKED_WAREHOUSE]:
                self.msg = MessagesTranslationHelper.get('asset_already_warehoused', self.user_language)
                return
        self.latest_status = AssetMapOut.objects.filter(
            asset_type=self.asset_type,
            asset_id=self.asset.id,
            approved=True
        ).last()
        if self.latest_status and self.latest_status.status == self.DISPOSED:
            self.msg = MessagesTranslationHelper.get('asset_already_disposed', LanguageChoices.ENGLISH)
            return
        self.valid = True

    def _fetch_latest_msm(self):
        if self.asset_type == HardwareType.MACHINE:
            old_machineslotmaps = MachineSlotMap.objects.filter(
                is_active = True,
                machine = self.current_obj
            ).order_by('-start_time')
        else:
            old_machineslotmaps = []
        return old_machineslotmaps

    def _create_work_order(self):
        location = getattr(self.hardware_bundle, 'location', None)
        if not location: return
        location_upkeep_code = location.upkeep_code if getattr(location, 'upkeep_code', None) else None
        location_maintainx_id = location.maintainx_id if getattr(location, 'maintainx_id', None) else None
        if not location_upkeep_code: return
        category = self.UPKEEP_WORK_ORDER_CATEGORIES.get(self.asset_map_out)
        asset = self.get_object(self.asset_tag)
        if not getattr(asset, 'upkeep_id', None): return
        payload = {
            'title' : f'Asset Map Out: {self.asset_map_out}',
            'asset' : getattr(asset, 'upkeep_id'),
            'location' : location_upkeep_code,
            'category' : category,
            'priority' : 2
        }
        api = UpkeepAPI()
        api.create_work_order(payload)
        #MAINTAINX IMPLEMENTATION
        if getattr(asset, 'maintainx_id'):
            categories = [MaintainxDefaultCategories.STANDARD_OPERATING_PROCEDURE] #NOTE: should we ask for new category??
            maintainx_payload = {
                'title' : f'Asset Map Out: {self.asset_map_out}',
                'assetId' : int(getattr(asset, 'maintainx_id')),
                'categories' : categories,
                'priority' : MaintainxWorkOrderPriority.MEDIUM,
                'description' : self.asset_map_out
            }
            if location_maintainx_id: maintainx_payload['locationId'] = int(location_maintainx_id)
            wo_manager = MaintainxWorkOrderManager()
            wo_manager.create_work_order(maintainx_payload)


    def _set_user_language(self):
        technician = getattr(self, 'technician', None)
        self.user_language = getattr(technician, 'language', None) or LanguageChoices.ENGLISH

    def get_current_equipment_type(self, slot, location):
        fascard_api = FascardApi(1)
        slot_response = fascard_api.get_machine(
            slot.slot_fascard_id
            )
        assert 'EquipID' in slot_response
        equipment_id = slot_response['EquipID']
        equipment = get_equipment_type(
                equipment_id,
                location
        )
        return equipment


    @transaction.atomic
    def map_out(self, asset_mapout_object=None) -> bool:
        """
        If the asset is marked for disposal, find its current active hardware bundle and deactivate it.
        Hardware bundle deactivation may cause other associated pieces to become orphan.

        If the asset is marked as any other state different than disposed (see class attributes), sets needs_rescanning
        in the AssetMapOut record equal to True. This will cause the asset to appear on the daily upkeep report
        until the asset is re scanned in the warehouse.
        """
        self._set_user_language()
        if not asset_mapout_object:
            status = AssetMapOut.objects.create(
                asset_type = self.asset_type,
                asset_id = self.asset.id,
                status = self.asset_map_out,
                description = self.description,
                scan_asset_tag = self.asset_tag,
                assigned_technician = getattr(self, 'technician', None),
                assigned_user = getattr(self, 'user', None),
                current_asset_bundle = self.hardware_bundle,
                approved = False
            )
            self.msg = MessagesTranslationHelper.get('mapout_approval', self.user_language)
            return True
        else:
            status = asset_mapout_object
        now = datetime.utcnow()
        if self.asset_map_out == self.DISPOSED:
            if self.hardware_bundle and self.hardware_bundle.is_active:
                BundlingProcessAbstract.orphane_pieces(
                    self.hardware_bundle,
                    leading_piece=None,
                    location=self.hardware_bundle.location,
                    technician = self.technician
                )
                BundlingProcessAbstract.deactivate_hardware_bundle(self.hardware_bundle)
            machineslotmaps = self._fetch_latest_msm()
            for msm in machineslotmaps:
                BundlingProcessAbstract.deactivate_machineslotmap(msm, now)
                slot_equipment_type = self.get_current_equipment_type(msm.slot, msm.slot.laundry_room)
                #BundlingProcessAbstract.add_machine_placeholder(msm.slot)
                new_machine_placeholder = Machine.objects.create(equipment_type = slot_equipment_type, machine_type = slot_equipment_type.machine_type)
                MachineSlotMap.objects.create(
                    slot = msm.slot,
                    machine = new_machine_placeholder,
                    start_time=datetime.now()
                )
        else:
            status.needs_rescanning = True
            status.save()
        self._create_work_order()
        self.current_obj = self.asset
        return True

    def process(self, asset_mapout_object=None) -> str:
        assert [hasattr(self, field) for field in self.fields_map.keys()]
        self.validate_data()
        if self.valid:
            mapped_out = self.map_out(asset_mapout_object=asset_mapout_object)
            if mapped_out:
                self.msg = getattr(self, 'msg', None) or MessagesTranslationHelper.get('successful_mapout', self.user_language)
                #self.send_email()
                #self.cmms_sync()
                self.cmms_sync()
                return self.msg
        else:
            return self.msg or MessagesTranslationHelper.get('unsuccessful_mapout', self.user_language)


class EmployeeScanAnalysis():
    email_template = "employee_scans_analysis_email.html"

    def get_scanning_data(self, start, end, employees_ids, room):
        bundles_queryset = HardwareBundlePairing.objects.filter(
            tech_employee__fascard_user__fascard_user_account_id__in=employees_ids,
            timestamp__gte=start,
            timestamp__lte=end,
            slot__isnull=False,
            location_id=room,
        )
        return bundles_queryset.values_list('slot__slot_fascard_id', flat=True)

    def send_email_notification(self, employee, data):
        to_email = employee.email_address
        if not to_email: to_email = 'suricatadev@gmail.com'
        #to_email = 'suricatadev@gmail.com'
        rendered_response = render_to_string(self.email_template, {'data': data})
        email = EmailMessage(
            'IMPORTANT: Missing Starts/Scans',
            rendered_response,
            settings.DEFAULT_FROM_EMAIL,
            [to_email]
        )
        email.content_subtype = "html"
        email.send(fail_silently=False)
    
    def run(self):
        data = {}
        activity_start_datetime = datetime.now() - relativedelta(minutes=20)
        activity_end_datetime = datetime.now()
        logging.info(f"Processing Employee Scans/Starts analysis with start_datetime: {activity_start_datetime} and end_datetime: {activity_end_datetime}")
        employees = FascardUser.objects.filter(
            is_employee = True,
            fascard_last_activity_date__gte = activity_start_datetime,
            fascard_last_activity_date__lte = activity_end_datetime)
        #testing
        # employees = FascardUser.objects.filter(id__in=[79911])
        # activity_start_datetime = datetime(2021,8,1)
        # activity_end_datetime = datetime(2021,8,10,11)
        for employee in employees:
            data = {}
            employee_txs = LaundryTransaction.objects.filter(
                local_transaction_date__gte=activity_start_datetime,
                local_transaction_date__lte=activity_end_datetime,
                transaction_type=TransactionType.VEND,
                fascard_user__fascard_user_account_id = employee.fascard_user_account_id)
            rooms_visited = employee_txs.values_list('laundry_room', flat=True).distinct()
            for room_id in rooms_visited:
                room = LaundryRoom.objects.get(id=room_id)
                all_slots = room.slot_set.filter(is_active=True)
                started_slots = employee_txs.filter(laundry_room=room).values_list('slot__slot_fascard_id', flat=True)
                scanned_slots = self.get_scanning_data(
                    activity_start_datetime, 
                    activity_end_datetime,
                    [employee.fascard_user_account_id],
                    room
                )
                non_started_slots = all_slots.exclude(slot_fascard_id__in=[int(s) for s in scanned_slots if s] + [int(s) for s in started_slots if s])
                non_scanned_slots = all_slots.exclude(slot_fascard_id__in=[int(s) for s in scanned_slots if s])
                if non_started_slots or non_scanned_slots:
                    data[room] = {'non_started_slots': non_started_slots, 'non_scanned_slots': non_scanned_slots}
            if data:
                self.send_email_notification(employee, data)
            return data

    @classmethod
    def run_as_job(cls):
        logger.info("Processing EmployeeScanAnalysis Job")
        ins = EmployeeScanAnalysis()
        ins.run()
        return True

        #fetch fascard user employees with activities over the last 20 minutes
        #{location: {'non_started': [], 'non_scanned': []}}
            #loop
                #find transactions done over the last X minutes and group them by location
                #loop over locations
                    #find non-started machines and non-scanned machines
        