'''
Created on Apr 5, 2017

@author: Thomas
'''
import logging
from datetime import datetime, timedelta
from dateutil.parser import parse
from django.db import transaction
from fascard.api import FascardApi, OOOReportAPI
from fascard.config import FascardScrapeConfig
from fascard.fascardbrowser import FascardBrowser
from fascard.utils import TimeHelper
from roommanager.models import LaundryRoom,Slot
from roommanager.enums import TimeZoneType
from roommanager.helpers import Helpers
from roommanager.slot_finder import SlotDeactivator
from .models import SlotState
from .enums import MachineStateType

logger = logging.getLogger(__name__)

class SlotStateIngestor():
    """
    Deprecated
    """

    @classmethod
    def ingest(cls,laundry_room_id):
        laundry_room = LaundryRoom.objects.get(pk=laundry_room_id)
        br = FascardBrowser()
        br.set_login_ins(laundry_room.laundry_group_id)
        for slot in list(Helpers.get_active_slots(laundry_room.id, use_room=True)):
            cls.__ingest_single_slot(br,slot)

    @classmethod
    @transaction.atomic()
    def __ingest_single_slot(self,br,slot):
        #Slot states
        slot = Slot.objects.select_for_update().get(pk=slot.pk)
        for br_slot_state in br.get_states(slot):
        #NB: br_slot_sta is a nanmed tuple object and NOT and orm object
            slot_state = SlotState.objects.filter(slot=slot,start_time=br_slot_state.start_time).first()
            if not slot_state:
                SlotState.objects.create(start_time=br_slot_state.start_time,end_time=br_slot_state.end_time,
                                      local_end_time = br_slot_state.local_end_time,
                                      duration=br_slot_state.duration,recorded_time=br_slot_state.recorded_time,
                                      local_recorded_time=br_slot_state.local_recorded_time,
                                      local_start_time = br_slot_state.local_start_time,
                                      slot_status = self.to_status_enum(br_slot_state.slot_status),
                                      slot_id=br_slot_state.slot_id)
            elif br_slot_state.end_time is None or slot_state.end_time is None or br_slot_state.end_time > slot_state.end_time:  #NB: this also works for slot_state end time null
                slot_state.end_time=br_slot_state.end_time
                slot_state.local_end_time = br_slot_state.local_end_time
                slot_state.duration = br_slot_state.duration
                slot_state.recorded_time = br_slot_state.recorded_time
                slot_state.local_recorded_time = br_slot_state.local_recorded_time
                slot_state.slot_status = self.to_status_enum(br_slot_state.slot_status)
                slot_state.save()

    @classmethod
    def to_status_enum(cls,txt):
        txt = txt.lower().strip()
        if txt.startswith('disabled'):
            return MachineStateType.DISABLED
        elif txt.startswith('error'):
            return MachineStateType.ERROR
        elif txt.startswith('offline'):
            return MachineStateType.OFFLINE
        elif txt.startswith('idle'):
            return MachineStateType.IDLE
        elif txt.startswith('running'):
            return MachineStateType.RUNNING
        elif txt.startswith('diagnostic'):
            return MachineStateType.DIAGNOSTIC
        elif txt.startswith('diag'):
            return MachineStateType.DIAGNOSTIC
        else:
            return MachineStateType.UNKNOWN


class SlotIngestionDataManager():
    model_class = SlotState

    def __init__(self, data):
        self.__dict__.update(**data)

    def add(self, var=None, name=None, **kwargs):
        if var and name:
            self.__dict__.update({var:name})
        if kwargs:
            self.__dict__.update(**kwargs)

    def clean(self):
        for key in list(self.__dict__.keys()):
            if key not in self.fields:
                self.__dict__.pop(key)

    def save_to_db(self):
        self.clean()
        self.model_class.objects.create(**self.__dict__)

    def update_to_db(self, slot_instance):
        self.clean()
        slot_instance.__dict__.update(**self.__dict__)
        slot_instance.save()

class StateDataStructure(SlotIngestionDataManager):
    model_class = SlotState
    fields = (
        'start_time',
        'local_start_time',
        'slot_id',
        'duration',
        'slot_status',
        'slot_status_text',
        'local_recorded_time',
        'mlvmacherror_description',
        'recorded_time',
        'end_time',
        'local_end_time',
        'mlvmacherror_description'
    )


class APISlotStateIngestor():

    def __init__(self, laundry_room_id):
        self.laundry_room = LaundryRoom.objects.get(pk=laundry_room_id)
        self.fascard_api = OOOReportAPI()

    @classmethod
    def to_status_enum(cls,status_code):
        status_mapper = {
            0: MachineStateType.OFFLINE,
            1: MachineStateType.DISABLED,
            2: MachineStateType.IDLE,
            3: MachineStateType.RUNNING,
            4: MachineStateType.DIAGNOSTIC,
            5: MachineStateType.DUPLICATE,
            6: MachineStateType.ERROR,
            100: MachineStateType.FIRMWARE_DOES_NOT_EXIST,
            101: MachineStateType.FIRMWARE_DOWNLOADING_SATELLITE,
            102: MachineStateType.FIRMWARE_DOWNLOADING_READER
        }
        return status_mapper.get(status_code, MachineStateType.UNKNOWN)

    def ingest_states(self):
        for slot in list(Helpers.get_active_slots(self.laundry_room.id, use_room=True)):
            response = self.__ingest_single_slot_states(slot)

    def __ingest_single_slot_states(self, slot):
        #slot = Slot.objects.select_for_update().get(pk=slot.pk)
        states_response = self.fascard_api.get_machine_history(slot.slot_fascard_id)

        if states_response['status_code'] == 500 or states_response['status_code'] == 403:
            status_code = states_response['status_code']
            reason = f'Status Code {status_code}'
            SlotDeactivator.deactivate(slot.slot_fascard_id, reason)
            return True

        states = list()
        for slot_state in states_response['response']:
            #The StatusTime variable returned by the API is equal to StartTime variable given by the Webpage
            slot_state_data = StateDataStructure(slot_state)
            start_time = parse(slot_state_data.StatusTime)
            local_status_time = TimeHelper.convert_to_local(
                start_time,
                self.laundry_room.time_zone)
            slot_state_data.add(**{
                'start_time': start_time,
                'local_start_time': local_status_time,
                'slot_id': slot.id
            })
            states.append(slot_state_data)

        for x in range(len(states)):
            recorded_time = datetime.utcnow()
            if self.laundry_room.time_zone is None or self.laundry_room.time_zone == '':
                room_time_zone = TimeZoneType.EASTERN
            else:
                room_time_zone = self.laundry_room.time_zone
            local_recorded_time = TimeHelper.convert_to_local(
                recorded_time,
                room_time_zone
            )
            current_slot_state = states[x]
            if x == 0:
                #first position state
                end_time = None
                local_end_time = None
                state_duration = None
            elif x > 0:
                previous_slot_state = states[x-1]
                state_duration = (
                    previous_slot_state.local_start_time - current_slot_state.local_start_time
                ).seconds
                #calculate endtime and compare to previous_slot_state
                end_time = current_slot_state.start_time + timedelta(seconds=state_duration)
                local_end_time = TimeHelper.convert_to_local(
                    end_time,
                    self.laundry_room.time_zone)

                if end_time is None:
                    logger.error("Got an end_time is None error. Slot internal ID: {}".format(current_slot_state.slot_id))

            if '\n' in current_slot_state.StatusText:
                status_text = ''.join(current_slot_state.StatusText.split('\n'))
            else:
                status_text = current_slot_state.StatusText
            current_slot_state.add(**{
                'duration': state_duration,
                'slot_status': APISlotStateIngestor.to_status_enum(current_slot_state.Status),
                'slot_status_text': status_text,
                'recorded_time': recorded_time,
                'local_recorded_time': local_recorded_time,
                'end_time': end_time,
                'local_end_time': local_end_time,
                'mlvmacherror_description': current_slot_state.MlvMachError
             })
            try:
                existing_slot_state = SlotState.objects.filter(
                    slot_id=current_slot_state.slot_id,
                    start_time=current_slot_state.start_time,
                    slot_status =APISlotStateIngestor.to_status_enum(current_slot_state.Status) ).first()
            except:
                existing_slot_state = None
            if not existing_slot_state:
                current_slot_state.save_to_db()
            elif (current_slot_state.end_time is None or
                existing_slot_state.end_time is None or
                current_slot_state.end_time > existing_slot_state.end_time):

                current_slot_state.update_to_db(existing_slot_state)

        return states


class LastRunTimeIngestor(object):
    """
    Deprecated
    """

    @classmethod
    def ingest(cls,laundry_room_id):
        laundry_room = LaundryRoom.objects.get(pk=laundry_room_id)
        br = FascardBrowser()
        br.set_login_ins(laundry_room.laundry_group_id)
        br_slots = br.get_slots(laundry_room.id, laundry_room.fascard_code)
        for br_slot in br_slots:
            if br_slot.last_start_time == 'N/A':
                continue
            try:
                slot = Slot.objects.get(laundry_room=laundry_room,slot_fascard_id=br_slot.slot_fascard_id)
            except:
                continue
            slot.last_run_time = datetime.strptime(br_slot.last_start_time,FascardScrapeConfig.TIME_INPUT_FORMAT)
            slot.save()


class SlotDataStructure(SlotIngestionDataManager):
    model_class = Slot


class APILastRunTimeIngestor():
    @classmethod
    def ingest(cls,laundry_room_id):
        laundry_room = LaundryRoom.objects.get(pk=laundry_room_id)
        fascard_api = FascardApi(
            laundry_group_id=laundry_room.laundry_group.pk
        )
        fascard_slots = fascard_api.get_slots_by_room(laundry_room.fascard_code)
        processed_slots = [SlotDataStructure(slot_dict) for slot_dict in fascard_slots]
        for slot_data in processed_slots:
            try:
                if not slot_data.FinishTime: continue
                slot_parsed_date = parse(slot_data.FinishTime, ignoretz=True)
                if slot_parsed_date.year == 1:
                    continue
                try:
                    existing_slot = Slot.objects.get(laundry_room=laundry_room,slot_fascard_id=slot_data.ID)
                except:
                    continue
                existing_slot.last_run_time = slot_parsed_date
                existing_slot.save()
            except Exception as e:
                logger.error(
                    'Failed ingesting Last Run Time for Slot: {} in Room: {}'.format(slot_data.ID, laundry_room)
                )
                continue