'''
Created on Apr 6, 2017

@author: Thomas
'''
from datetime import timedelta
from outoforder import enums 
from .config import OutOfOrderConfig
from .models import SlotState


class EndTimeFixer():
    
    @classmethod 
    def fix_endtimes(cls,slot):
        if SlotState.objects.filter(slot=slot,end_time=None).count() <= 1:
            return 
        else:
            null_endtime_states = list(SlotState.objects.filter(slot=slot,end_time=None).order_by('-start_time'))
            head_state = null_endtime_states.pop(0)  #This is the real current state.  don't touch it!
            for bad_slot_state in null_endtime_states:
                next_state = SlotState.objects.exclude(id=bad_slot_state.id).filter(
                    slot=slot,start_time__gte=bad_slot_state.start_time).order_by('start_time','id').first() 
                if (bad_slot_state.slot_status == enums.MachineStateType.RUNNING) and ( (next_state.start_time-bad_slot_state.start_time).total_seconds()/60.0 > OutOfOrderConfig.RUNNING_STATE_MIN):
                    bad_slot_state.end_time = bad_slot_state.start_time + timedelta(minutes=OutOfOrderConfig.RUNNING_STATE_MIN)
                    bad_slot_state.local_end_time = bad_slot_state.local_start_time + timedelta(minutes=OutOfOrderConfig.RUNNING_STATE_MIN)
                    bad_slot_state.has_endtime_guess = True 
                    bad_slot_state.is_filler_state = False 
                    bad_slot_state.is_guess_state = True
                    try:
                        bad_slot_state.duration = (bad_slot_state.end_time-bad_slot_state.start_time).total_seconds()
                    except Exception as e:
                        pass 
                    bad_slot_state.save()
                    
                    try:
                        dur = (next_state.start_time-bad_slot_state.end_time).total_seconds()
                    except:
                        pass
                    SlotState.objects.create(slot=bad_slot_state.slot,
                                                                   start_time = bad_slot_state.end_time,
                                                                   local_start_time = bad_slot_state.local_end_time,
                                                                   end_time = next_state.start_time,
                                                                   local_end_time = next_state.local_start_time,
                                                                   slot_status = enums.MachineStateType.IDLE,
                                                                   recorded_time = bad_slot_state.recorded_time,
                                                                   local_recorded_time = bad_slot_state.local_recorded_time,
                                                                   has_endtime_guess = False,
                                                                   is_filler_state = True,
                                                                   is_guess_state = True,
                                                                   duration = dur
                                                                   )           
                else:
                    bad_slot_state.end_time = next_state.start_time
                    bad_slot_state.local_end_time = next_state.local_start_time
                    bad_slot_state.has_endtime_guess = True 
                    bad_slot_state.is_filler_state = False 
                    bad_slot_state.is_guess_state = True 
                    try:
                        bad_slot_state.duration = (bad_slot_state.end_time - bad_slot_state.start_time).total_seconds()
                    except:
                        pass
                    bad_slot_state.save()