import logging
import time
from typing import Dict, List, Tuple, Sequence, TypeVar
from django.db import transaction
from django.conf import settings
from main.decorators import ProductionCheck
from roommanager.models import *
from roommanager.enums import HardwareType, VerboseMachineType, BundleType
from .api import UpkeepAPI
from .utils import AssetPicturesMap


logger = logging.getLogger(__name__)


AssetType = TypeVar("AssetType", CardReaderAsset, Machine)

class UpkeepManager:

    def __init__(self):
        self.API = UpkeepAPI()

    @ProductionCheck
    def create_location(self, location):
        """
        Creates a new location in Upkeep and associates it to the location passed as parameter
        """
        assert isinstance(location, LaundryRoom)
        response = self.API.create_location(location)
        location.upkeep_code = response['id']
        location.save()

    
    @ProductionCheck
    def update_location(self, location, **kwargs):
        assert isinstance(location, LaundryRoom)
        self.API.update_location(location, **kwargs)

    @ProductionCheck
    def activate_location(self, location):
        assert isinstance(location, LaundryRoom)
        assert hasattr(location, 'upkeep_code')
        current_name = self.API.get_location(location.upkeep_code)['name']
        if 'DISABLED' in current_name:
            data = {'name': current_name.strip('DISABLED')}
            self.API.update_location(location, **data)

    @ProductionCheck
    def deactivate_location(self, location):
        """
        Adds the word 'DISABLED' to the location's name in Upkeep
        """
        assert isinstance(location, LaundryRoom)
        assert hasattr(location, 'upkeep_code')
        current_name = self.API.get_location(location.upkeep_code)['name']
        if not 'DISABLED' in current_name:
            data = {'name': 'DISABLED ' + current_name}
            self.API.update_location(location, **data)

    @ProductionCheck
    def sync_names(self):
        rooms = LaundryRoom.objects.filter(upkeep_code__isnull=False)
        for room in rooms:
            current_name = self.API.get_location(room.upkeep_code)['name']
            if room.display_name != current_name:
                data = {'name': room.display_name}
                self.API.update_location(location, **data)

    @ProductionCheck
    def sync_locations(laundry_group_id):
        #check for both names and active status and update
        locations = LaundryRoom.objects.filter(laundry_group__id=laundry_group_id)
        for location in locations:
            if location.is_active:
                if hasattr(location, 'upkeep_code'):
                    fields_to_update = {}
                    upkeep_location = self.API.get_location(location.upkeep_code)
                    self.update_location(location)
                else:
                    self.save_location(location)
            else:
                if hasattr(location, 'upkeep_code'):
                    self.deactivate_location(location)
                if location.display_name != upkeep_location.get('name'):
                    fields_to_update.update({'name':location.display_name})

class BaseUpkeepAssetManager:

    def __init__(self):
        self.api =  UpkeepAPI()

    def build_meter_payload(self, asset, asset_payload):
        meter_name  = asset_payload.get('name') + ' Meter'
        payload = {
            'name' : meter_name,
            'units' : settings.UPKEEP_METER_UNITS,
            'frequency' : settings.UPKEEP_METER_FREQUENCY,
            'asset' : getattr(asset, 'upkeep_id', None),
            'location' : asset_payload.get('location')
        }
        return payload

    @classmethod
    def _get_hardware_bundles(cls, asset: AssetType):
        p = {cls.field_name_in_hardwarebundle : asset}
        q = HardwareBundle.objects.filter(**p)
        return q

    @classmethod
    def get_related_data(cls, asset: AssetType):
        hardware_bundles = cls._get_hardware_bundles(asset)
        active_bundles = hardware_bundles.filter(is_active = True)
        related_slots = [] #Only one if bundle is Single or two if bundle is Stacked
        if active_bundles:
            for bundle in active_bundles:
                related_slots.append(bundle.slot)
        elif hardware_bundles:
            last_known = hardware_bundles.order_by('-start_time').first()
            hardware_bundles = [last_known]
            related_slots.append(last_known.slot)
        return related_slots, hardware_bundles, active_bundles


    @classmethod
    def _build_asset_name(cls, asset: AssetType, related_slots: Sequence[Slot],
        location: LaundryRoom) -> Tuple[str, str]:
        """
        If there is an outstanding HardwareBundleRequirement the asset is considered orphane
        and the string ORPH is appended. Otherwise, it checks whether the machine is warehoused or
        part of a bundle and construcs its Upkeep equivalent name string.

        Params:
        asset : either a Machine or a CardReader
            Object instance
        related slots: list
            List of object instances of the slots the machine is associated with.
        location : LaundryRoom
            Object instance
        """
        hbr = HardwareBundleRequirement.objects.filter(
            done=False, 
            hardware_id=asset.id,
            hardware_type=cls.hardware_type,
        ).count()
        payload = {cls.field_name_in_hardwarebundle : asset, 'is_active' : True}
        hb = HardwareBundle.objects.filter(**payload).last()
        if hbr:
            status = '-ORPH'
        else:
            if hb and hb.warehouse:
                status = 'WARHS'
            else:
                status = 'BUNDL'

        if status in ['BUNDL', '-ORPH']:
            web_display_names = []
            for slot in related_slots:
                web_display_names.append(getattr(slot, 'web_display_name', ''))
            name_list = [
                '&'.join(web_display_names), 
                getattr(asset, cls.asset_code_field_name, 'UnknownTag'),
                asset.get_asset_model(),
                str(status),
            ]
            location_name = getattr(location, 'display_name', None) or 'UnknownLocation'
            name =  "{}--#".format(location_name)
            name = name + '--'.join(name_list)
        else:
            make_model = asset.get_asset_model()
            asset_code = getattr(asset, cls.asset_code_field_name)
            first_four = asset_code[:4] if asset_code else ''
            name = '--'.join([make_model, first_four, status])
        if isinstance(asset, CardReaderAsset): name = "CardReader: " + name
        return name, status


    #@ProductionCheck
    def create_asset_meter(self, asset: AssetType, asset_payload: Dict) -> None:
        meter_payload = self.build_meter_payload(asset, asset_payload)
        meter_response = self.api.create_asset_meter(meter_payload)
        if 'id' in meter_response:
            meter_obj = getattr(asset, 'meter') #TODO: implement related_name
            meter_obj.upkeep_id = meter_response.get('id')
            meter_obj.save()
        else:
            logger.error('Failed Creating Meter for Asset {}. Response" {}'.format(
                asset,
                meter_response
            ))

    def _get_custom_fields_payload(self):
        """
        Get an API-ready payload of the custom upkeep fields associated with the asset.
        """
        raise NotImplementedError

    #@ProductionCheck
    def create_or_update(self, asset: AssetType) -> bool:
        """
        If there is an existing upkeep meter associated with the asset, updates
        the meter. Otherwise, creates a new upkeep meter and associates it with the asset

        The method gets called from signals processors in roommanager.signals

        Params:
        asset: Machine or CardReader
        """
        asset.refresh_from_db()
        if isinstance(asset, Machine) and getattr(asset, "placeholder", False):
            return False
        asset_payload = self.build_asset_payload(asset)
        local_custom_fields = self._get_custom_fields_payload(asset)
        try:
            assert asset_payload
        except AssertionError:
            logger.info(f"Couldn't get a valid payload for asset: {asset}")
            return
        created = False
        logger.info(f"Creating/Updating upkeep record for asset: {asset}")
        if asset.upkeep_id is None:
            if local_custom_fields:
                asset_payload.update({'customFieldsAsset': local_custom_fields})
            response = self.api.create_asset(asset_payload)
            if 'id' in response:
                asset.upkeep_id = response['id']
                asset.save()
                transaction.commit()
            self.create_asset_meter(asset, asset_payload)
            #attach images work orders
            if isinstance(asset, Machine):
                fields = list()
                for field in ('asset_picture', 'asset_serial_picture'):
                    if getattr(asset, field):
                        fields.append(field)
                self.attach_images_work_oders(asset, fields)
            created = True
        else:
            upkeep_custom_fields = self.api.get_asset(asset.upkeep_id).get('customFieldsAsset')
            new_fields = []
            if upkeep_custom_fields:
                upkeep_fields_db = {}
                for upkeep_custom_field in upkeep_custom_fields:
                    upkeep_fields_db[upkeep_custom_field.get('name')] = upkeep_custom_field
                for local_custom_field in local_custom_fields:
                    if local_custom_field.get('name') in upkeep_fields_db.keys():
                        field_name = local_custom_field.get('name')
                        upkeep_field = upkeep_fields_db.get(field_name)
                        if local_custom_field.get('value') and local_custom_field.get('value') != upkeep_field.get('value'):
                            self.api.update_custom_field(
                                asset.upkeep_id,
                                upkeep_field.get('id'),
                                local_custom_field
                            )
                    else:
                        new_fields.append(local_custom_field)
            else:
                new_fields = local_custom_fields
            if new_fields:
                asset_payload.update({'customFieldsAsset': new_fields})
            response = self.api.update_asset(asset.upkeep_id, asset_payload)
            meter_payload = self.build_meter_payload(asset, asset_payload)
            meter_obj = getattr(asset, 'meter')
            if meter_obj.upkeep_id:
                meter_obj.refresh_from_db()
                meter_response = self.api.update_asset_meter(meter_obj.upkeep_id, meter_payload)
            #asset pictures updates are handled in save method of Machine Model
        return created

    @classmethod
    def sync_transactions_meter(cls) -> None:
        """
        deprecated for low performance.
        """
        api = UpkeepAPI()
        q = {'upkeep_id__isnull' : False, 'transactions_counter__gt' : 0}
        qq = {'upkeep_id__isnull' : False, 'dryers_start_counter__gt' : 0}
        for meter in MachineMeter.objects.filter(**q):
            api.update_asset_meter_reading(meter, 'transactions_counter', silent_fail=True)
        for meter in CardReaderMeter.objects.filter(**q):
            api.update_asset_meter_reading(meter, 'transactions_counter', silent_fail=True)
        for meter in LaundryRoomMeter.objects.filter(**qq):
            api.update_asset_meter_reading(meter, 'dryers_start_counter', silent_fail=True)

    @classmethod
    def sync_asset_meters(cls, asset_meter_id: int, asset_type: str) -> None:
        """
        Syncs all upkeep meters associated with either a Machine or CardReader
        """
        api = UpkeepAPI()
        try:
            if asset_type == HardwareType.MACHINE:
                meter = MachineMeter.objects.get(id=asset_meter_id)
            elif asset_type == HardwareType.CARD_READER:
                meter = CardReaderMeter.objects.get(id=asset_meter_id)
            else:
                return
            api.update_asset_meter_reading(meter, 'transactions_counter', silent_fail=True)
        except Exception as e:
            logger.info("Failed updating meter for {} with id {}. {}".format(asset_type, asset_meter_id,e))

    @classmethod
    def sync_room_meters(cls, room_meter_id: int) -> None:
        "Syncs all upkeep meters associated with a LaundryRoom"
        api = UpkeepAPI()
        try:
            meter = LaundryRoomMeter.objects.get(id=room_meter_id)
            api.update_asset_meter_reading(meter, 'dryers_start_counter', silent_fail=True)
        except Exception as e:
            logger.info("Failed updating laundry room meter with id: {}. {}".format(room_meter_id, e))



#NOTE: Could rewrite class to pass machine as an __init__ parameter

#NOTE: Below class is only usef for Machine type Assets.
class UpkeepAssetManager(BaseUpkeepAssetManager):
    """
        Used for Machines only
    """
    create_required_fields = (
        'asset_code',
        'machine_type',
        'equipment_type'
    )
    base_machine_url = 'https://system.aceslaundry.com/admin/roommanager/machine/{}/change/'
    hardware_type = HardwareType.MACHINE
    field_name_in_hardwarebundle = 'machine' #Field name in HardwareBundle model
    asset_code_field_name = 'asset_code'

    # @classmethod
    # def _build_machine_name(cls, machine: Machine, related_slots: Sequence[Slot],
    #     location: LaundryRoom) -> Tuple[str, str]:
    #     """
    #     If there is an outstanding HardwareBundleRequirement the machine is considered orphane
    #     and the string ORPH is appended. Otherwise, it checks whether the machine is warehoused or
    #     part of a bundle and construcs its Upkeep equivalent name string.

    #     Params:
    #     machine : Machine
    #         Object instance
    #     related slots: list
    #         List of object instances of slots the machine is associated with.
    #     location : LaundryRoom
    #         Object instance
    #     """
    #     hbr = HardwareBundleRequirement.objects.filter(
    #         done=False, 
    #         hardware_id=machine.id,
    #         hardware_type=HardwareType.MACHINE,
    #     ).count()
    #     hb = HardwareBundle.objects.filter(
    #             machine = machine,
    #             is_active = True
    #         ).last()
    #     if hbr:
    #         status = '-ORPH'
    #     else:
    #         if hb and hb.warehouse:
    #             status = 'WARHS'
    #         else:
    #             status = 'BUNDL'

    #     if status in ['BUNDL', '-ORPH']:
    #         web_display_names = []
    #         for slot in related_slots:
    #             web_display_names.append(getattr(slot, 'web_display_name', None))
    #         machine_name_list = [
    #             '&'.join(web_display_names), 
    #             getattr(machine, 'asset_code', 'UnknownTag'),
    #             machine.get_asset_model(),
    #             str(status),
    #         ]
    #         location_name = getattr(location, 'display_name', None) or 'UnknownLocation'
    #         name =  "{}--#".format(location_name)
    #         name = name + '--'.join(machine_name_list)
    #     else:
    #         make_model = machine.get_asset_model()
    #         name = '--'.join([make_model, machine.asset_code[:4], status])
    #     return name, status

    def _get_custom_fields_payload(self, machine):
        return [
            {
                'name' : 'asset_make_serial',
                'value' : str(getattr(machine, 'asset_serial_number', '')),
                'unit' : 'serial_number'
            },
        ]

    @classmethod
    def _build_machine_description(cls, machine: Machine, related_slots: Sequence[Slot], 
        active_bundles: Sequence[HardwareBundle] = None) -> str:
        """
        Builds the description for a Machine's associated asset record in Upkeep

        Params:
        machine : Machine
            Object instance
        related slots: list
            List of object instances of slots the machine is associated with.
        active_bundles:
            List of active HardwareBundle objects that the machine is associated with.
        """
        slots_fascard_ids = ', '.join([slot.slot_fascard_id for slot in related_slots if slot])
        description = "Fascard ID(Slot): {}. Machine Admin URL: {}".format(
            slots_fascard_ids,
            cls.base_machine_url.format(machine.id)
        )
        if active_bundles:
            associated_assets_ulrs = list()
            slot_notes = 'Slot Notes: '
            for bundle in active_bundles:
                card_reader = getattr(bundle, 'card_reader', None)
                if card_reader:
                    associated_assets_ulrs.append(card_reader.get_upkeep_asset_url())
                if bundle.slot.custom_description:
                    slot_notes += f'Slot ({bundle.slot.slot_fascard_id}): {bundle.slot.custom_description}'
            assets_str = ". ".join(list(map(lambda x: f"Associated Asset: {x}", associated_assets_ulrs)))
            description = ". ".join([description, assets_str, slot_notes]) 
        if machine.machine_description:
            description = description + f" Machine Description: {machine.machine_description}"
        return description


    @ProductionCheck
    def create_work_order(self, machine, extra_payload):
        latest_msm = machine.machineslotmap_set.filter(is_active=True).last()
        if latest_msm: location = latest_msm.slot.laundry_room
        else: return False
        if machine.placeholder or location.upkeep_code is None: return False
        payload = {
            'asset' : machine.upkeep_id,
            'location' : location.upkeep_code,
            'assignedToUser' : 'qX89EYRbka', #Juanita
            'category' : 'Administrative - Picture Association',
            'priority' : 2
        }
        payload.update(extra_payload)
        self.api.create_work_order(payload)

    def attach_images_work_oders(self, machine, fields_list):
        ins = AssetPicturesMap()
        ins.parse_work_order(machine, fields_list)
        d = {
            'title' : ins.title,
            'description' : ins.description
        }
        self.create_work_order(machine, d)

    def build_asset_payload(self, machine):
        """
        Controls the creation of the entire payload to be sent during creation or update of the associated
        asset record in Upkeep

        Params:
        machine : Machine
            Object instance
        """
        for field in self.create_required_fields:
            if getattr(machine, field, None) is None:
                err_str = 'Machine information is incomplete. Missing field: {}'.format(field)
                logger.error(err_str)
                raise Exception(err_str)

        #NOTE: Can change hardware bundles for machineslotmaps. Would that be more reliable?        
        related_slots, hardware_bundles, active_bundles = self.get_related_data(machine)
        if all(related_slots): related_slots.sort(key=lambda x: x.web_display_name)
        self.latest_status_mapout = AssetMapOut.objects.filter(
            active=True,
            asset_type = HardwareType.MACHINE,
            asset_id = machine.id            
        ).order_by('-timestamp').first()

        category = VerboseMachineType.map_to_machinetype.get(machine.machine_type)
        if hardware_bundles: location = hardware_bundles[0].location
        else: location = DefaultRoom.objects.last().laundry_room
        machine_name, _ = self._build_asset_name(machine, related_slots, location)
        machine_model = machine.get_asset_model()
        machine_description = self._build_machine_description(machine, related_slots, active_bundles)
        if self.latest_status_mapout:
            machine_description += f" Latest Status Mapout: {self.latest_status_mapout.status}"
            machine_name += f" ({self.latest_status_mapout.status})"

        if machine_model is None:
            logger.error(
                "Could not sync asset to Upkeep: The Machine does not have an equipment type."
            )
            return False
        if location.upkeep_code is None:
            logger.error(
                "Could not sync asset to Upkeep: The location does not have an Upkeep code."
            )
            return False
        payload = {
            'model' : machine.get_asset_model(),
            'name' : machine_name,
            'serial' : machine.asset_code, #Barcode
            'location' : location.upkeep_code, #Location's Upkeep Code
            'category' : category, #enums.WASHER, enums.DRYER
            'description' : machine_description,
            #'status' : ,
        }
        return payload

    @classmethod
    def sync_transactions_meter(cls):
        api = UpkeepAPI()
        for meter in MachineMeter.objects.filter(upkeep_id__isnull=False, transactions_counter__gt=0):
            api.update_asset_meter_reading(meter, 'transactions_counter')
        #machine = Machine.objects.get(id=machine_id)
        #if machine.placeholder:
        #    return False
        #meter = getattr(machine, 'machinemeter', None)
        #if meter and meter.upkeep_id and meter.transactions_counter > 0:
        #    update_response = api.update_asset_meter_reading(meter)


class UpkeepCardReaderManager(BaseUpkeepAssetManager):
    category = 'card-reader'
    base_url = 'https://system.aceslaundry.com/admin/roommanager/cardreaderasset/{}/change/'
    hardware_type = HardwareType.CARD_READER
    field_name_in_hardwarebundle = 'card_reader' #Field name in HardwareBundle model
    asset_code_field_name = 'card_reader_tag'

    def _dict_as_string(self, d):
        return '--\n'.join([f'{k}: {v}' for k,v in d.items()])    

    # @classmethod
    # def _get_hardware_bundles(self, card_reader : CardReaderAsset):
    #     q = HardwareBundle.objects.filter(
    #         card_reader = card_reader,
    #     )
    #     return q
    def _get_custom_fields_payload(self, card_reader: AssetType):
        return {}

    def build_asset_payload(self, card_reader: AssetType):
        payload = {}
        description = {
            'Condition' : card_reader.condition,
            'Link' : self.base_url.format(card_reader.id)
        }
        payload['serial'] = getattr(card_reader, 'card_reader_tag')
        payload['model'] = card_reader.get_asset_model()
        payload['category'] = self.category
        current_bundle = card_reader.get_current_bundle()
        if current_bundle:
            if current_bundle.bundle_type in [BundleType.WAREHOUSE, BundleType.STACKED_WAREHOUSE]:
                description['Status'] = 'Warehouse'
            else:
                description['Status'] = 'Bundled'
            description['Machine'] = current_bundle.slot
            machine_url = current_bundle.machine.get_upkeep_asset_url()
            if machine_url:
                description['Associated Machine'] = machine_url
        else:
            description['Status'] = 'Available'
        self.latest_status_mapout = AssetMapOut.objects.filter(
            active=True,
            asset_type = HardwareType.CARD_READER,
            asset_id = card_reader.id
        ).order_by('-timestamp').first()
        if self.latest_status_mapout:
            description['Latest Status Mapout'] = latest_status_mapout.status
        payload['description'] = self._dict_as_string(description)
        related_slots, hardware_bundles, active_bundles = self.get_related_data(card_reader)
        #CardReader Name
        if hardware_bundles:
            location = hardware_bundles[0].location
        else:
            location = card_reader.get_location()
        name, status = self._build_asset_name(card_reader, related_slots, location)
        #name = "CardReader: {} - {}".format(card_reader.card_reader_tag, description['Status'])
        if self.latest_status_mapout:
            name += f" ({self.latest_status_mapout.status})"
        payload['name'] = name
        location = card_reader.get_location()
        if not getattr(location, 'upkeep_code'):
            UpkeepManager().create_location(location)
            location.refresh_from_db()
        payload['location'] = location.upkeep_code
        return payload


class UpkeepAssetSyncJob():

    @classmethod
    def run_job(cls, asset_id: int, asset_type: str) -> bool:
        if asset_type == HardwareType.MACHINE:
            asset = Machine.objects.get(pk=asset_id)
            upkeep_manager = UpkeepAssetManager()
        elif asset_type == HardwareType.CARD_READER:
            asset = CardReaderAsset.objects.get(pk=asset_id)
            upkeep_manager = UpkeepCardReaderManager()
        else:
            return False
        created = upkeep_manager.create_or_update(asset)
        return created


class LaundryRoomMeterSetUp(BaseUpkeepAssetManager):
    """
    Creates meters for rooms for the first time.
    """

    @ProductionCheck
    def run(self):
        for room in LaundryRoom.objects.filter(is_active=True, meter__isnull=True, upkeep_code__isnull=False):
            if not getattr(room, 'upkeep_code', None):
                continue
            meter = getattr(room, 'meter', None)
            if not meter:
                try:
                    meter = LaundryRoomMeter.objects.create(laundry_room=room)
                except Exception as e:
                    logger.info("Failed creating local meter for room: {}. Exception: {}".format(room, e))
            payload = {'name' : room.display_name, 'location':room.upkeep_code}
            meter_payload = self.build_meter_payload(room, payload)
            meter_payload['name'] += ' (Dryers Starts)'
            try:
                meter_response = self.api.create_asset_meter(meter_payload)
            except Exception as e:
                logger.info("Failed upkeep meter creation for room: {}. Exception: {}".format(room, e))
                meter_response = None
            if meter_response and 'id' in meter_response:
                meter_obj = getattr(room, 'meter') #TODO: implement related_name
                meter_obj.upkeep_id = meter_response.get('id')
                try:
                    dryers_starts = room.get_dryer_starts_count()
                except:
                    dryers_starts = 0
                meter.dryers_start_counter = dryers_starts
                meter_obj.save()
            else:
                logger.error('Failed Creating Meter for Asset {}. Response" {}'.format(
                    asset,
                    meter_response
                ))