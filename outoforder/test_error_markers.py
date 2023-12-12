from datetime import datetime, timedelta
import os

from django.test import TestCase

from main import settings

from Utils.CSVIngest.ingest import CSVIngestor

from fascard.config import FascardScrapeConfig

from roommanager.models import LaundryGroup,LaundryRoom, Slot, Machine, MachineSlotMap, EquipmentType, EquipmentTypeSchedule
from roommanager.enums import SlotType

from .models import SlotState, SlotStateError
from .enums import MachineStateType, SlotErrorType
from .errormarker import FascardErrorMarker, FlickeringErrorMarker, IdleErrorMarker, ShortRunningMarker, LongRunningMarker, CurfewErrorMarker
from .config import ErrorMarkerConfig

class TestErrorMarkers(TestCase):

    def setUp(self):
        CSVIngestor(LaundryGroup,file_name = os.path.join(settings.TEST_FILE_FOLDER,'test_null_endtime','laundry_group.csv')).ingest(date_format=None,datetime_format=FascardScrapeConfig.TIME_INPUT_FORMAT)
        CSVIngestor(LaundryRoom,file_name = os.path.join(settings.TEST_FILE_FOLDER,'test_null_endtime','laundry_room.csv')).ingest(date_format=None,datetime_format=FascardScrapeConfig.TIME_INPUT_FORMAT)

        self.arden = LaundryRoom.objects.get(display_name='1 Arden ST')

        self.slot_1 = Slot.objects.create(laundry_room=self.arden,
                             slot_fascard_id = '1',
                             web_display_name = '1',
                             slot_type = SlotType.STANDARD
                             )
        self.curfew_slot = Slot.objects.create(
            laundry_room=self.arden,
			slot_fascard_id = '11',
            web_display_name = '111',
            slot_type = SlotType.STANDARD)

        '''This has a fascard error (aka fascard says there is an error)'''
        self.ss1_slot_status_error = SlotState.objects.create(slot=self.slot_1,
                                       start_time = datetime(2017,1,1,12),
                                       local_start_time = datetime(2017,1,1,8),
                                       end_time = None,
                                       local_end_time = None,
                                       duration = None,
                                       slot_status = MachineStateType.ERROR,
                                       recorded_time = datetime(2017,1,1),
                                       local_recorded_time = datetime(2017,1,1)
                                       )

        '''This also has a fascard error (aka fascard says there is an error)'''
        self.ss2_slot_status_disabled = SlotState.objects.create(slot=self.slot_1,
                                       start_time = datetime(2017,1,1,12),
                                       local_start_time = datetime(2017,1,1,8),
                                       end_time = None,
                                       local_end_time = None,
                                       duration = None,
                                       slot_status = MachineStateType.DISABLED,
                                       recorded_time = datetime(2017,1,1),
                                       local_recorded_time = datetime(2017,1,1)
                                       )
        '''This also has a fascard error (aka fascard says there is an error)'''
        self.ss3_slot_status_diagnostic = SlotState.objects.create(slot=self.slot_1,
                                       start_time = datetime(2017,1,1,12),
                                       local_start_time = datetime(2017,1,1,8),
                                       end_time = None,
                                       local_end_time = None,
                                       duration = None,
                                       slot_status = MachineStateType.DIAGNOSTIC,
                                       recorded_time = datetime(2017,1,1),
                                       local_recorded_time = datetime(2017,1,1)
                                       )

        '''This also has a fascard error (aka fascard says there is an error)'''
        self.ss4_flicker = SlotState.objects.create(slot=self.slot_1,
                                       start_time = datetime(2016,1,1,1),
                                       local_start_time = datetime(2016,1,1,1),
                                       end_time = datetime(2016,1,1,1)+timedelta(seconds=2),
                                       local_end_time = None,
                                       duration = 2,
                                       slot_status = MachineStateType.RUNNING,
                                       recorded_time = datetime(2017,1,1),
                                       local_recorded_time = datetime(2017,1,1)
                                       )

        '''This is a double barred slot '''
        self.slot_2_double_barred =   Slot.objects.create(laundry_room=self.arden,
                                 slot_fascard_id = '2',
                                 web_display_name = '2',
                                 slot_type = SlotType.DOUBLE
                                 )
        '''Double barreled slots are always idle. This state should NOT be marked as idle for too long'''
        self.ss5_double_barreled_idle = SlotState.objects.create(slot=self.slot_2_double_barred,
                                       start_time = datetime(1900,1,1,1),
                                       local_start_time = datetime(1900,1,1),
                                       end_time = None,
                                       local_end_time = None,
                                       duration = None,
                                       slot_status = MachineStateType.IDLE,
                                       recorded_time = datetime(2017,1,1),
                                       local_recorded_time = datetime(2017,1,1)
                                       )
        '''Idle with no endtime'''
        self.ss6_idle_no_endtime = SlotState.objects.create(slot=self.slot_1,
                                       start_time = datetime(1900,1,1,1),
                                       local_start_time = datetime(1900,1,1),
                                       end_time = None,
                                       local_end_time = None,
                                       duration = None,
                                       slot_status = MachineStateType.IDLE,
                                       recorded_time = datetime(2017,1,1),
                                       local_recorded_time = datetime(2017,1,1)
                                       )

        '''idle with no edtime that is close to now'''
        start_time = datetime.utcnow() - timedelta(seconds=ErrorMarkerConfig.IDLE_MIN_SECONDS//2)
        self.ss6a_notidle_no_endtime = SlotState.objects.create(slot=self.slot_1,
                                       start_time = start_time,
                                       local_start_time = start_time,
                                       end_time = None,
                                       local_end_time = None,
                                       duration = None,
                                       slot_status = MachineStateType.IDLE,
                                       recorded_time = datetime(2017,1,1),
                                       local_recorded_time = datetime(2017,1,1)
                                       )

        '''Idle with endtime'''
        self.ss7_idle_no_endtime = SlotState.objects.create(slot=self.slot_1,
                                       start_time = datetime(1900,1,1,1),
                                       local_start_time = datetime(1900,1,1),
                                       end_time = datetime(2000,1,1,1),
                                       local_end_time = datetime(2000,1,1,1),
                                       duration = (datetime(2000,1,1,1)-datetime(1900,1,1,1)).total_seconds(),
                                       slot_status = MachineStateType.IDLE,
                                       recorded_time = datetime(2017,1,1),
                                       local_recorded_time = datetime(2017,1,1)
                                       )

        '''Used for testing null cutoff value, cutoff value over max, and cutoff value under min'''
        #NB: slot 1 has a null cutoff value idle time, so this case is already tested
        '''slot with an idle cutoff between the min and max'''
        self.slot_3_idle_cutoff_in_range =  Slot.objects.create(laundry_room=self.arden,
                         slot_fascard_id = '3',
                         web_display_name = '3',
                         slot_type = SlotType.STANDARD,
                         idle_cutoff_seconds = (ErrorMarkerConfig.IDLE_MIN_SECONDS + ErrorMarkerConfig.IDLE_MAX_SECONDS)//2
                         )
        #NB: we calculate based on duration, so we don't have to worry about what the start and end time is here
        self.ss8_normalcutoffvalue_idle_too_long = SlotState.objects.create(slot=self.slot_3_idle_cutoff_in_range,
                                       start_time = datetime(1900,1,1,1),
                                       local_start_time = datetime(1900,1,1,1),
                                       end_time = None,
                                       local_end_time = None,
                                       duration = (ErrorMarkerConfig.IDLE_MIN_SECONDS + ErrorMarkerConfig.IDLE_MAX_SECONDS)*3//4,
                                       slot_status = MachineStateType.IDLE,
                                       recorded_time = datetime(2017,1,1),
                                       local_recorded_time = datetime(2017,1,1)
                                       )
        # **
        self.ss9_normalcutoffvalue_idle_ok = SlotState.objects.create(slot=self.slot_3_idle_cutoff_in_range,
                                       start_time = datetime(1900,1,1,1),
                                       local_start_time = datetime(1900,1,1,1),
                                       end_time = None,
                                       local_end_time = None,
                                       duration = (ErrorMarkerConfig.IDLE_MIN_SECONDS + ErrorMarkerConfig.IDLE_MAX_SECONDS)//4,
                                       slot_status = MachineStateType.IDLE,
                                       recorded_time = datetime(2017,1,1),
                                       local_recorded_time = datetime(2017,1,1)
                                       )

        '''slot with an idle cutoff above the max'''
        self.slot_4_idle_cutoff_above_range =  Slot.objects.create(laundry_room=self.arden,
                         slot_fascard_id = '4',
                         web_display_name = '4',
                         slot_type = SlotType.STANDARD,
                         idle_cutoff_seconds = ErrorMarkerConfig.IDLE_MAX_SECONDS*2
                         )
        self.ss10_highcutoffvalue_idle_duration_between_max_and_slots_cutoff_value = SlotState.objects.create(
                slot = self.slot_4_idle_cutoff_above_range,
                start_time = datetime(1900,1,1,1),
                local_start_time = datetime(1900,1,1,1),
                end_time = None,
                local_end_time = None,
                duration = ErrorMarkerConfig.IDLE_MAX_SECONDS*1.5,
                slot_status = MachineStateType.IDLE,
                recorded_time = datetime(2017,1,1),
                local_recorded_time = datetime(2017,1,1)
                )

        '''slot with and idle cutoff below the min'''
        self.slot_5_idle_cutoff_below_range =  Slot.objects.create(laundry_room=self.arden,
                         slot_fascard_id = '5',
                         web_display_name = '5',
                         slot_type = SlotType.STANDARD,
                         idle_cutoff_seconds = ErrorMarkerConfig.IDLE_MIN_SECONDS//4
                         )
        # **
        self.ss11_lowcutoffvalue_notidle = SlotState.objects.create(
                slot = self.slot_5_idle_cutoff_below_range,
                start_time = datetime(1900,1,1,1),
                local_start_time = datetime(1900,1,1,1),
                end_time = None,
                local_end_time = None,
                duration = ErrorMarkerConfig.IDLE_MIN_SECONDS//4,
                slot_status = MachineStateType.IDLE,
                recorded_time = datetime(2017,1,1),
                local_recorded_time = datetime(2017,1,1)
                )
        #**
        self.ss12_lowcutoffvalue_idle_too_long = SlotState.objects.create(
                slot = self.slot_5_idle_cutoff_below_range,
                start_time = datetime(1900,1,1,1),
                local_start_time = datetime(1900,1,1,1),
                end_time = None,
                local_end_time = None,
                duration = ErrorMarkerConfig.IDLE_MIN_SECONDS+10,
                slot_status = MachineStateType.IDLE,
                recorded_time = datetime(2017,1,1),
                local_recorded_time = datetime(2017,1,1)
                )


        '''This is a long running machine with and end time.  It should create an error'''
        self.ss13_long_running_with_endtime = SlotState.objects.create(
                slot = self.slot_1,
                start_time = datetime(2017,1,1),
                local_start_time = datetime(2017,1,1),
                end_time = datetime(2018,1,1),
                local_end_time = datetime(2018,1,1),
                duration = ErrorMarkerConfig.LONG_RUNNING_HOURS*3600 + 100,
                recorded_time = datetime(2017,1,1),
                local_recorded_time = datetime(2017,1,1),
                slot_status = MachineStateType.RUNNING
                )

        '''This is a long running machine without an endtime.  It should not create an error'''
        self.sss_14_long_running_with_no_endtime = SlotState.objects.create(
                slot = self.slot_1,
                start_time = datetime(2100,1,1),
                local_start_time = datetime(2100,1,1), #NB: doesn't matter what we put here
                end_time = None,
                local_end_time = None,
                duration = None,
                recorded_time = datetime(2100,1,1) + timedelta(seconds=ErrorMarkerConfig.LONG_RUNNING_HOURS*3600+100),
                local_recorded_time = datetime(2000,1,1), #NB this shouldn't matter
                slot_status = MachineStateType.RUNNING
                )

        '''This is a short running machine'''
        self.ss_15_short_running_machine = SlotState.objects.create(
                slot=self.slot_1,
                start_time = datetime(2017,1,1),
                local_start_time = datetime(2017,1,1),
                end_time = datetime(2017,1,1,0,10),
                local_end_time = datetime(2017,1,1,0,10),
                duration= ErrorMarkerConfig.SHORT_RUNNING_MAX_SEC-100,
                recorded_time = datetime(2017,1,1),
                local_recorded_time = datetime(2017,1,1),
                slot_status = MachineStateType.RUNNING
                )

        '''This is a machine that has been running for a short time but has no endtime.  It should not have an error'''
        self.ss_16_machine_that_just_started = SlotState.objects.create(
                slot=self.slot_1,
                start_time = datetime(2100,1,1),
                local_start_time =  datetime(2100,1,1),
                end_time = None,
                local_end_time = None,
                duration= None,
                recorded_time = datetime(2100,1,1)+timedelta(seconds=ErrorMarkerConfig.SHORT_RUNNING_MAX_SEC-10),
                local_recorded_time = datetime(2100,1,1)+timedelta(seconds=ErrorMarkerConfig.SHORT_RUNNING_MAX_SEC-10),
                slot_status = MachineStateType.RUNNING
                )

        self.equipment_type = EquipmentType.objects.create(
                fascard_id = 1,
                laundry_group_id = 1,
                machine_text = 'Wascomat',
                machine_type = 1, #dryer
                equipment_start_check_method = 'STANDARD',
        )

        self.machine_in_curfew = Machine.objects.create(
            equipment_type=self.equipment_type,
			machine_type = 1
        )

        self.msm_curfew = MachineSlotMap.objects.create(
            slot = self.curfew_slot,
            machine = self.machine_in_curfew,
			start_time=datetime.now() - timedelta(days=1)
        )

        self.curfew_schedule = EquipmentTypeSchedule.objects.create(
                laundry_room=self.arden,
                equipment_type = self.equipment_type,
                start_from = 0,
                end_at = 450,
                active = False,
        )

        today = datetime.now().date()
        current_sunday = today - timedelta(days=today.weekday() + 1)
        current_sunday_midnight = datetime.combine(current_sunday, datetime.min.time())

        self.machine_in_curfew_state = SlotState.objects.create(
            slot=self.curfew_slot,
            start_time = current_sunday_midnight + timedelta(minutes=10),
            local_start_time = current_sunday_midnight + timedelta(minutes=10),
            end_time = None,
            local_end_time = None,
            duration = None,
            slot_status = MachineStateType.DISABLED,
            recorded_time = current_sunday_midnight + timedelta(minutes=10),
            local_recorded_time = current_sunday_midnight + timedelta(minutes=10)
        )

        '''This is machine that has been running for a short time but has no endtime.  It should have no error'''

    def test_fascard_error_marker(self):
        '''Ensure a slot state error is created for fascard error states.  Ensure nothing else gets an error'''
        FascardErrorMarker(self.arden).process()

        error_state_one = SlotStateError.objects.filter(slot_state=self.ss1_slot_status_error,error_type=SlotErrorType.ERROR)
        self.assertEqual(error_state_one.count(),1)

        error_state_two = SlotStateError.objects.filter(slot_state=self.ss2_slot_status_disabled,error_type=SlotErrorType.DISABLED)
        self.assertEqual(error_state_two.count(),1)

        error_state_three = SlotStateError.objects.filter(slot_state=self.ss3_slot_status_diagnostic,error_type=SlotErrorType.DIAGNOSTIC)
        self.assertEqual(error_state_three.count(),1)

        '''ensure no other errors were recorded'''
        errors = SlotStateError.objects.all()
        self.assertEqual(errors.count(),3)

    def test_curfew(self):
        CurfewErrorMarker(self.arden).process()
        schedules = EquipmentTypeSchedule.objects.filter(laundry_room=self.arden)
        error_states = SlotStateError.objects.filter(slot_state__slot=self.curfew_slot,error_type=SlotErrorType.DISABLED)
        self.assertEqual(error_states.count(),1)
        self.assertEqual(error_states[0].error_message,'Disabled Machine in Curfew')

    def test_flickering_error_marker(self):
        FlickeringErrorMarker(self.arden).process()

        '''Ensure the flickering error was recorded'''
        error_states = SlotStateError.objects.filter(slot_state=self.ss4_flicker,error_type=SlotErrorType.FLICKERING)
        self.assertEqual(error_states.count(),1)

        '''ensure no other errors were recorded'''
        errors = SlotStateError.objects.all()
        self.assertEqual(errors.count(),1)

    def test_idle_error_marker(self):
        IdleErrorMarker(self.arden).process()

        '''Ensure the no end time idle state was recorder'''
        error_states1 = SlotStateError.objects.filter(slot_state=self.ss6_idle_no_endtime,
                                                     error_type=SlotErrorType.LONG_IDLE)
        self.assertEqual(error_states1.count(),1)

        '''Ensure null endtimes with recent start time is not recorded'''
        error_states2a = SlotStateError.objects.filter(slot_state=self.ss6a_notidle_no_endtime,
                                                      error_type=SlotErrorType.LONG_IDLE)
        self.assertEqual(error_states2a.count(),0)

        '''Ensure the non null end time idle state was recorder'''
        error_states2 = SlotStateError.objects.filter(slot_state=self.ss7_idle_no_endtime,
                                                     error_type=SlotErrorType.LONG_IDLE)
        self.assertEqual(error_states2.count(),1)

        '''ensure slot with idle cutoff value between min and max is recorded correctly'''
        error_states_3 = SlotStateError.objects.filter(slot_state=self.ss8_normalcutoffvalue_idle_too_long,
                                                       error_type=SlotErrorType.LONG_IDLE)
        self.assertEqual(error_states_3.count(),1)
        error_states_4 = SlotStateError.objects.filter(slot_state=self.ss9_normalcutoffvalue_idle_ok,
                                                       error_type=SlotErrorType.LONG_IDLE)
        self.assertEqual(error_states_4.count(),0)

        '''ensure slot with idle cutoff value above max is recorded correctly'''
        error_states_5 = SlotStateError.objects.filter(slot_state=self.ss10_highcutoffvalue_idle_duration_between_max_and_slots_cutoff_value,
                                                       error_type=SlotErrorType.LONG_IDLE)
        self.assertEqual(error_states_5.count(),1)

        '''ensure slot with idle cutoff value below min is recorded correctly'''
        error_states_6 = SlotStateError.objects.filter(slot_state=self.ss11_lowcutoffvalue_notidle,
                                                       error_type=SlotErrorType.LONG_IDLE)
        self.assertEqual(error_states_6.count(),0)
        error_states_7 = SlotStateError.objects.filter(slot_state=self.ss12_lowcutoffvalue_idle_too_long,
                                                       error_type=SlotErrorType.LONG_IDLE)
        self.assertEqual(error_states_7.count(),1)

        '''ensure double type slots have no idle too long errors'''
        error_states_8 = SlotStateError.objects.filter(slot_state=self.ss5_double_barreled_idle,
                                                       error_type=SlotErrorType.LONG_IDLE)
        self.assertEqual(error_states_8.count(),0)

    def test_long_running(self):
        LongRunningMarker(self.arden).process()

        '''Ensure the long running machine with and end time has an error'''
        self.assertEqual(SlotStateError.objects.filter(slot_state=self.ss13_long_running_with_endtime,
                                                       error_type = SlotErrorType.LONG_RUNNING
                                                       ).count(),1)

        '''Ensure the long running machine with no end time has an error'''
        self.assertEqual(SlotStateError.objects.filter(slot_state=self.sss_14_long_running_with_no_endtime,
                                                       error_type = SlotErrorType.LONG_RUNNING
                                                       ).count(),1)

        '''Ensure no other errors are created'''
        self.assertEqual(SlotStateError.objects.filter(error_type=SlotErrorType.LONG_RUNNING).count(),2)


    def test_short_running(self):
        ShortRunningMarker(self.arden).process()

        '''Ensure short running machine has an error'''
        self.assertEqual(SlotStateError.objects.filter(slot_state=self.ss_15_short_running_machine,
                                               error_type = SlotErrorType.SHORT_RUNNING
                                               ).count(),1)

        '''Ensure machine that are running normally right now have no errors'''
        self.assertEqual(SlotStateError.objects.filter(slot_state=self.ss_16_machine_that_just_started,
                                       error_type = SlotErrorType.SHORT_RUNNING
                                       ).count(),0)
