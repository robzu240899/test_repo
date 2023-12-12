'''
Created on Mar 5, 2017

@author: Thomas
'''
import logging
import re
from django.core.mail import EmailMessage
from django.conf import settings
from fascard.api import FascardApi, OOOReportAPI
from dateutil.relativedelta import relativedelta
from datetime import datetime, date
from roommanager import enums
from roommanager.enums import MachineType, HardwareType
from .models import LaundryRoom, Slot, MachineSlotMap, Machine, EquipmentType

logger = logging.getLogger(__name__)


class SlotDeactivator():

    @classmethod
    def deactivate_bundle(cls, slot):
        from roommanager.job import BundlingProcessAbstract
        latest_bundle = slot.hardwarebundle_set.all().order_by('-start_time').first()
        if latest_bundle and latest_bundle.is_active:
            BundlingProcessAbstract.orphane_pieces(
                latest_bundle, 
                "slot",
                slot.laundry_room
            )
            BundlingProcessAbstract.deactivate_hardware_bundle(
                latest_bundle
            )
        return True

    @classmethod
    def deactivate(cls, slot_fascard_id, reason):
        from roommanager.job import BundlingProcessAbstract
        try:
            slot = Slot.objects.get(slot_fascard_id=slot_fascard_id)
            latest_bundle = slot.hardwarebundle_set.all().order_by('-start_time').first()
            if latest_bundle:
                deactivated_bundle = cls.deactivate_bundle(slot)
            machine_slot_map = MachineSlotMap.objects.filter(slot=slot, is_active=True).order_by('-start_time').first()
            if machine_slot_map is not None:
                machine_slot_map.is_active = False
                machine_slot_map.end_time = datetime.now()
                machine_slot_map.save()
            slot.is_active = False
            slot.save()
            #send email
            email = EmailMessage(
                subject='[ALERT] A Slot has been deactivated',
                body=f'Slot {slot} has been deactivated. Reason: {reason}',
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=settings.IT_EMAIL_LIST
            )
            email.send(fail_silently=False)
        except Exception as e:
            raise e
            logger.error("Failed to deactivate slot with slot_id: {}. Exception: {}".format(
                slot_id,
                e)
            )
        logger.info(f"Deactivated Slot with slot_fascard_id: {slot_fascard_id}")



class ConfigurationRecorder(object):

    @classmethod
    def record_equipment(cls, laundry_room_id):
        laundry_room = LaundryRoom.objects.get(pk = laundry_room_id)
        api = FascardApi(laundry_room.laundry_group_id)
        for equipment_type_data in api.get_equipment(laundry_room.fascard_code):
            fascard_id = equipment_type_data['ID']
            machine_text = equipment_type_data['EquipName']
            equipment_class = equipment_type_data['EquipClass']
            if equipment_class == 1:
                machine_type = MachineType.WASHER
            elif equipment_class == 2:
                machine_type = MachineType.DRYER
            else:
                machine_type = MachineType.UNKNOWN
            equipment_type = EquipmentType.objects.filter(laundry_group_id = laundry_room.laundry_group_id, fascard_id = fascard_id).first()
            if not equipment_type:
                EquipmentType.objects.create(laundry_group_id = laundry_room.laundry_group_id, fascard_id = fascard_id,
                                             machine_text = machine_text, machine_type = machine_type
                                             )

    @classmethod
    def update_slot_startcheck(cls, slot, equipment_type):
        try:
            slot.slot_type = equipment_type.equipment_start_check_method
            slot.save()
        except Exception as e:
            exception_string = 'Failed to set slot_type attribute to slot: {}'.format(slot)
            logger.error(exception_string)
            raise Exception(exception_string)

    # @classmethod
    # def check_machine_equipment(cls, equipment_type, machine, slot):
    #     if equipment_type.fascard_id != machine.equipment_type.fascard_id:
    #         equipment_name = equipment_type.machine_text.split('--')
    #         machine_equipment_name = machine.equipment_type.machine_text.split('--')
    #         f = lambda x: x.strip().lower()
    #         equipment_name = tuple(map(f,equipment_name[:2]))
    #         machine_equipment_name = tuple(map(f,machine_equipment_name[:2]))

    #         if equipment_name == machine_equipment_name:
    #             cls.__force_equipment_override(machine, equipment_type, slot)
    #         else:
    #             old_machine = machine
    #             SlotDeactivator.deactivate_bundle(slot)
    #             cls.__attach_machine(slot, old_machine, equipment_type)
    #         return True
    #     return False
    
    @classmethod
    def check_slot_equipment(cls, equipment_type, machine, slot):
        if equipment_type.fascard_id != slot.equipment_type.fascard_id:
            equipment_name = equipment_type.machine_text.split('--')
            slot_equipment_name = slot.equipment_type.machine_text.split('--')
            f = lambda x: x.strip().lower()
            equipment_name = tuple(map(f,equipment_name[:2]))
            slot_equipment_name = tuple(map(f,slot_equipment_name[:2]))
            if equipment_name == slot_equipment_name:
                cls.__force_equipment_override(equipment_type, slot)
            else:
                old_machine = machine
                SlotDeactivator.deactivate_bundle(slot)
                cls.__attach_machine(slot, old_machine, equipment_type)
            return True
        return False

    @classmethod
    def add_pricing_period(cls, laundry_room, reason):
        from reporting.finance.internal.tasks import PricingHistoryWorker
        from reporting.models import PricingPeriod
        latest_pricing_period = PricingPeriod.objects.filter(laundry_room=laundry_room).order_by('-start_date').first()
        if latest_pricing_period and latest_pricing_period.start_date < date.today():
            phr = PricingHistoryWorker(laundry_room.laundry_group_id)
            time = phr._get_formatted_time(laundry_room)
            phr.save_pricing_period(laundry_room, time, reason)

    @classmethod
    def process_machines(cls, laundry_room, force_equipment_override):
        api = FascardApi(laundry_group_id = laundry_room.laundry_group_id)
        fascard_slots_ids = []
        try:
            machines_data = api.get_machines(fascard_location_id = laundry_room.fascard_code)
        except:
            return fascard_slots_ids
        for machine_data in machines_data:
            #Extract data from the API's response
            slot_fascard_id = machine_data['ID']
            fascard_slots_ids.append(str(slot_fascard_id))
            web_display_name = machine_data['MachNo']
            fascard_equipment_type_id = machine_data['EquipID']
            #Get or create slot
            slot = Slot.objects.filter(laundry_room = laundry_room, slot_fascard_id=slot_fascard_id).first()
            if not slot:
                slot = Slot.objects.create(laundry_room = laundry_room,
                                slot_fascard_id = slot_fascard_id,
                                web_display_name = web_display_name,
                                clean_web_display_name = web_display_name)
            else:
                if slot.web_display_name != web_display_name:
                    slot.web_display_name = web_display_name
            #Attach machine to the slot if the machine has changed
            try:
                equipment_type = EquipmentType.objects.get(
                    fascard_id = fascard_equipment_type_id,
                    laundry_group_id = laundry_room.laundry_group_id
                )
            except Exception as e:
                raise Exception(
                    'Failed to load EquipmentType instance with fascard id: {}. Laundry Room: {}({}). Exception: {}'.format(
                        fascard_equipment_type_id,
                        laundry_room,
                        laundry_room.fascard_code,
                        e
                        )
                )
            if not slot.equipment_type:
                cls.__force_equipment_override(equipment_type, slot)
            machine = Slot.get_current_machine(slot)
            if not machine:
                cls.__attach_machine(slot, machine, equipment_type)
            else:
                #et_change = cls.check_machine_equipment(equipment_type, machine, slot)
                et_change = cls.check_slot_equipment(equipment_type, machine, slot)
                if et_change:
                    cls.add_pricing_period(laundry_room, 'Equipment Type Change / Override during Slot Config check.')
            cls.update_slot_startcheck(slot, equipment_type)
        return fascard_slots_ids

    @classmethod
    def check_slots_status(cls, fascard_slots_ids, laundry_room):
        if not fascard_slots_ids: return None
        api = FascardApi(laundry_group_id = laundry_room.laundry_group_id)
        alt_api = OOOReportAPI(laundry_group_id=laundry_room.laundry_group.pk)
        current_slots = Slot.objects.filter(laundry_room = laundry_room, is_active=True)
        current_slots_ids = current_slots.values_list('slot_fascard_id', flat=True)
        current_slots_ids = set(current_slots_ids)
        for slot_fascard_id in current_slots_ids - set(fascard_slots_ids):
            reason = 'Slot no longer retrieved on API Response'
            SlotDeactivator.deactivate(slot_fascard_id, reason)
        for slot in current_slots:
            if slot.is_active == False and slot.slot_fascard_id in fascard_slots_ids:
                valid_history = True
                try:
                    slot_history_response = alt_api.get_machine_history(machine_fascard_id=slot.slot_fascard_id)
                    if slot_history_response['status_code'] == 500 or slot_history_response['status_code'] == 403: valid_history = False
                except: valid_history = False
                last_msm = slot.machineslotmap_set.all().order_by('-start_time').first()
                conditions_to_check = [valid_history, last_msm]
                latest_bundle = slot.hardwarebundle_set.all().order_by('-start_time').first()
                if latest_bundle: conditions_to_check.append(latest_bundle.is_active)
                if last_msm: conditions_to_check.append(last_msm.is_active)                
                if all(conditions_to_check):
                    slot.is_active = True
                    slot.save()

    @classmethod
    def pricing_period_checker(cls, laundry_room, initial_slots_count):
        final_slots_count = Slot.objects.filter(
            laundry_room = laundry_room,
            is_active=True
        ).count()
        
        if initial_slots_count != final_slots_count:
            cls.add_pricing_period(laundry_room, f'Slots Count is different (Initial: {initial_slots_count}. Final: {final_slots_count}). Date: {date.today()}')

    @classmethod
    def record_slot_configuration(cls, limit_to_rooms, force_equipment_override=False):
        if isinstance(limit_to_rooms, int):
            limit_to_rooms = [limit_to_rooms]
        for laundry_room_id in limit_to_rooms:
            laundry_room = LaundryRoom.objects.get(pk=laundry_room_id)
            initial_slots_count = Slot.objects.filter(
                    laundry_room = laundry_room,
                    is_active=True).count()
            
            fascard_slots_ids = cls.process_machines(laundry_room, force_equipment_override)
            #Deactivating deprecated slots
            cls.check_slots_status(fascard_slots_ids, laundry_room)
            #TODO: deal with slot type
            #If there are new Slots on a laundry room, create a new pricing period in case
            #none has been created during the last 24 hours
            cls.pricing_period_checker(laundry_room, initial_slots_count)

    @classmethod
    def __is_new_machine(cls,machine, fascard_equipment_type_id):
        if machine is None:
            return True
        elif machine.equipment_type.fascard_id == fascard_equipment_type_id:
            return False
        else:
            return True

    @classmethod
    def __attach_machine(cls, slot, old_machine, equipment_type):
        now = datetime.utcnow()
        msmap = MachineSlotMap.objects.filter(machine=old_machine,slot=slot).order_by('-start_time').first()
        if msmap is not None:
            msmap.end_time = now
            msmap.save()
        new_machine = Machine.objects.create(machine_type = equipment_type.machine_type)
        cls.__force_equipment_override(equipment_type, slot)
        MachineSlotMap.objects.create(slot = slot, machine = new_machine, start_time=now)

    # @classmethod
    # def __force_equipment_override(cls, machine, equipment_type, slot):
    #     if machine:
    #         machine.equipment_type = equipment_type
    #         machine.save()
    #     else:
    #         new_machine = Machine.objects.create(equipment_type = equipment_type, machine_type = equipment_type.machine_type)
    #         now = datetime.utcnow()
    #         MachineSlotMap.objects.create(slot = slot, machine = new_machine, start_time=now)

    @classmethod
    def __force_equipment_override(cls, equipment_type, slot):
        slot.equipment_type = equipment_type
        slot.save()