'''
Created on Apr 6, 2017

@author: Thomas
'''
from datetime import datetime, timedelta
import os

from django.test import TestCase

from main import settings

from Utils.CSVIngest.ingest import CSVIngestor

from fascard.config import FascardScrapeConfig

from roommanager.models import LaundryGroup,LaundryRoom, Slot
from roommanager.enums import SlotType

from .models import SlotState
from .enums import MachineStateType
from .endtime import EndTimeFixer
from .config import OutOfOrderConfig


class TestEndtimeFixer(TestCase):

    def setUp(self):
        CSVIngestor(LaundryGroup,file_name = os.path.join(settings.TEST_FILE_FOLDER,'test_null_endtime','laundry_group.csv')).ingest(date_format=None,datetime_format=FascardScrapeConfig.TIME_INPUT_FORMAT)
        CSVIngestor(LaundryRoom,file_name = os.path.join(settings.TEST_FILE_FOLDER,'test_null_endtime','laundry_room.csv')).ingest(date_format=None,datetime_format=FascardScrapeConfig.TIME_INPUT_FORMAT)
        self.arden = LaundryRoom.objects.get(display_name='1 Arden ST')

    def test_standard(self):
        '''We have several null endtime states.
        make sure each gets fixed
        make sure the most recent null endtime state is left alone
        '''

        slot_1 = Slot.objects.create(laundry_room=self.arden,
                                     slot_fascard_id = '1',
                                     web_display_name = '1',
                                     slot_type = SlotType.STANDARD
                                     )

        ss1 = SlotState.objects.create(slot=slot_1,
                                       start_time = datetime(2017,1,1,12),
                                       local_start_time = datetime(2017,1,1,8),
                                       end_time = None,
                                       local_end_time = None,
                                       duration = None,
                                       slot_status = MachineStateType.IDLE,
                                       recorded_time = datetime(2017,1,1),
                                       local_recorded_time = datetime(2017,1,1)
                                       )
        ss2 = SlotState.objects.create(slot=slot_1,
                                       start_time = datetime(2016,6,1,12),
                                       local_start_time = datetime(2017,6,1,8),
                                       end_time = None,
                                       local_end_time = None,
                                       duration = None,
                                       slot_status = MachineStateType.IDLE,
                                       recorded_time = datetime(2017,1,1),
                                       local_recorded_time = datetime(2017,1,1)
                                       )

        ss3 = SlotState.objects.create(slot=slot_1,
                                       start_time = datetime(2016,6,1,11,20),
                                       local_start_time = datetime(2016,6,1,7,20),
                                       end_time = datetime(2016,6,1,12),
                                       local_end_time = datetime(2017,6,1,8),
                                       duration = (datetime(2016,6,1,12) - datetime(2016,6,1,11,20)).total_seconds(),
                                       slot_status = MachineStateType.IDLE,
                                       recorded_time = datetime(2017,1,1),
                                       local_recorded_time = datetime(2017,1,1)
                                       )
        ss4 = SlotState.objects.create(slot=slot_1,
                                       start_time = datetime(2015,6,1,11,20),
                                       local_start_time = datetime(2015,6,1,7,20),
                                       end_time = None,
                                       local_end_time = None,
                                       duration = None,
                                       slot_status = MachineStateType.RUNNING,
                                       recorded_time = datetime(2017,1,1),
                                       local_recorded_time = datetime(2017,1,1)
                                       )

        ### Add these into ensure slots are considered in isolation!
        slot_2 = Slot.objects.create(laundry_room=self.arden,
                                     slot_fascard_id = '2',
                                     web_display_name = '1',
                                     slot_type = SlotType.STANDARD
                                     )
        s1 = datetime(2017,1,1,13)
        e1 = datetime(2017,1,1,13,30)
        s1_local = datetime(2017,1,1,13) - timedelta(hours=4)
        e1_local = datetime(2017,1,1,13,30) - timedelta(hours=4)
        for i in range(100):
            if i % 100 == 0:
                start_time = s1+timedelta(hours=i)
                end_time = None
                local_start_time = s1_local +timedelta(hours=i)
                local_end_time =  None
                duration = None
            else:
                start_time = s1+timedelta(hours=i)
                end_time = e1+timedelta(hours=i)
                local_start_time = s1_local+timedelta(hours=i)
                local_end_time =  e1_local + timedelta(hours=i)
                duration = (end_time-start_time).total_seconds()
            SlotState.objects.create(slot=slot_2,
                                start_time=start_time,
                                end_time = end_time,
                                local_start_time = local_start_time,
                                local_end_time = local_end_time,
                                duration = duration,
                                recorded_time = datetime(2017,1,1),
                                local_recorded_time = datetime(2017,1,1),
                                slot_status = MachineStateType.IDLE
                                )
        ########### End Add these into ensure slots are considered in isolation!

        ### Run Code ##
        EndTimeFixer.fix_endtimes(slot_1)
        ### End Run Code ##


        #### TEST! ###
        ss1_refresh = SlotState.objects.get(pk=ss1.pk)
        ss2_refresh = SlotState.objects.get(pk=ss2.pk)
        ss3_refresh = SlotState.objects.get(pk=ss3.pk)
        ss4_refresh = SlotState.objects.get(pk=ss4.pk)
        new_state = SlotState.objects.filter(start_time__gt=ss4_refresh.start_time).order_by('start_time').first()

        '''Nothing should change for slot state 1'''
        self.assertEqual(ss1.start_time,         ss1_refresh.start_time)
        self.assertEqual(ss1.end_time,           ss1_refresh.end_time)
        self.assertEqual(ss1.local_start_time,   ss1_refresh.local_start_time)
        self.assertEqual(ss1.local_end_time,     ss1_refresh.local_end_time)
        self.assertEqual(ss1.duration,           ss1_refresh.duration)


        '''Slot state 2 should be repaired '''
        self.assertEqual(ss2_refresh.start_time,         ss2.start_time)
        self.assertEqual(ss2_refresh.end_time,           ss1.start_time)
        self.assertEqual(ss2_refresh.local_start_time,   ss2.local_start_time)
        self.assertEqual(ss2_refresh.local_end_time,     ss1.local_start_time)
        self.assertEqual(ss2_refresh.duration,           (ss2_refresh.end_time-ss2_refresh.start_time).total_seconds())


        '''Nothing should change for slot state 3'''
        self.assertEqual(ss3.start_time,         ss3_refresh.start_time)
        self.assertEqual(ss3.end_time,           ss3_refresh.end_time)
        self.assertEqual(ss3.local_start_time,   ss3_refresh.local_start_time)
        self.assertEqual(ss3.local_end_time,     ss3_refresh.local_end_time)
        self.assertEqual(ss3.duration,           ss3_refresh.duration)

        '''Slot state 4 is a running state with a missing end time.  Should be split into 2 states,
        the first is the original state with a endtime 30 min after the start time.  The 2nd is a new id-sle state
        that runs from the new endtime to the next start time'''
        self.assertEqual(ss4_refresh.start_time,       ss4.start_time)
        self.assertEqual(ss4_refresh.end_time,         ss4.start_time+timedelta(minutes=OutOfOrderConfig.RUNNING_STATE_MIN))
        self.assertEqual(ss4_refresh.local_start_time, ss4.local_start_time)
        self.assertEqual(ss4_refresh.local_end_time,   ss4.local_start_time+timedelta(minutes=OutOfOrderConfig.RUNNING_STATE_MIN))
        self.assertEqual(ss4_refresh.duration,         (ss4_refresh.end_time-ss4_refresh.start_time).total_seconds())
        self.assertEqual(ss4_refresh.slot_status,       MachineStateType.RUNNING)


        '''There should be a new slot state created for an idle state after the run'''
        self.assertEqual(new_state.slot_status,      MachineStateType.IDLE)
        self.assertEqual(new_state.start_time,       ss4_refresh.end_time)
        self.assertEqual(new_state.local_start_time, ss4_refresh.local_end_time)
        self.assertEqual(new_state.end_time,         ss3_refresh.start_time)
        self.assertEqual(new_state.local_end_time,   ss3_refresh.local_start_time)
        self.assertEqual(new_state.duration,         (new_state.end_time-new_state.start_time).total_seconds())


        #### End TEST! ###
