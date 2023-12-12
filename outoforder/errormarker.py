import logging
import os
from collections import namedtuple
from copy import deepcopy
from datetime import datetime,timedelta
from django.db import transaction
from django.db.models import Q, Count,Max,Min
from roommanager.enums import SlotType, MachineType
from roommanager.models import LaundryRoom,Slot,EquipmentTypeSchedule
from outoforder import config 
from .enums import SlotErrorType, MachineStateType
from .models import Slot,SlotState,SlotStateError

logger = logging.getLogger(__name__)


class ErrorMarkerManager():
     
    @staticmethod
    def mark_all(laundry_room_id): 
        laundry_room = LaundryRoom.objects.get(pk=laundry_room_id)
        FascardErrorMarker(laundry_room).process()
        IdleErrorMarker(laundry_room).process()
        LongRunningMarker(laundry_room).process()
        ShortRunningMarker(laundry_room).process()
        FlickeringErrorMarker(laundry_room).process()
        DuplicateErrorMarker(laundry_room).process()
        CurfewErrorMarker(laundry_room).process()        
#         print 'NoTransactionErrorMarker'
#         NoTransactionErrorMarker().process()
        with transaction.atomic():
            to_update = SlotState.objects.select_for_update().filter(slot__laundry_room=laundry_room).exclude(end_time=None, error_checking_complete=False)
            to_update.update(error_checking_complete=True)

class ErrorMarker(object):
    
    def __init__(self,laundry_room):
        self.laundry_room = laundry_room
        self.initial_filter = SlotState.objects.filter(slot__laundry_room=laundry_room,
                                               error_checking_complete=False)
    
    def process(self):
        self._find_errors()
        self._mark_errors()
    
    def _create_error_msg(self,err):
        raise NotImplementedError("_create_error_msg not implemented by child class")
    
    def _find_errors(self):
        raise NotImplementedError("_find_errors not implemented by child class ")
    
    def _mark_errors(self):
        for bad_slot_state in self.bad_slot_states:
            err_msg = self._create_error_msg(bad_slot_state)
            #Make this thread-safe.  In the sense that it won't take forever to run the job gets 
            #sent out to 2 servers
            if SlotStateError.objects.filter(slot_state=bad_slot_state,error_type__in=self.ERROR_ENUMS).exists():
                continue 
            else:
                error_enum = self._set_error_enum(bad_slot_state)
                SlotStateError.objects.create(slot_state=bad_slot_state,
                                                  error_message=err_msg,
                                                  error_type=error_enum)
            bad_slot_state.error_checking_complete = True
            bad_slot_state.save()


class CurfewAbstract:

    def check_if_scheduled(self, slot_state, schedules):
        #Curfew Logic.
        #checks if the error is due to scheduled downtime
        for schedule in schedules:
            start = self.current_sunday_midnight + timedelta(minutes=schedule.start_from)
            end = self.current_sunday_midnight + timedelta(minutes=schedule.end_at)
            if slot_state.start_time > start and slot_state.start_time < end:
                if schedule.active is False:
                    #The machine should be inactive
                    #The error is scheduled
                    return True
        return False

    def check_curfew(self, bad_state):
        today = datetime.now().date()
        current_sunday = today - timedelta(days=today.weekday() + 1)
        self.current_sunday_midnight = datetime.combine(current_sunday, datetime.min.time())
        try:
            slot = bad_state.slot
            equipment_type = slot.equipment_type
            # machine = Slot.get_current_machine(slot)
            # if machine.machine_type == MachineType.COMBO_STACK:
            #     equipment_type = slot.get_current_equipment_type()
            #     if not equipment_type in machine.equipment_types.all():
            #         logger.error(f"A ComboStack Machine has improper equipment_types. It's missing {equipment_type}")
            # else:
            #     equipment_type = machine.equipment_types.first()
            equipment_schedules = self.schedules.filter(equipment_type=equipment_type)
            is_scheduled = self.check_if_scheduled(bad_state, equipment_schedules)
            if is_scheduled:
                return True
            else:
                return False
        except Exception as e:
            logger.error("Error checking if slot state is in curfew: {}".format(e), exc_info=True)
            return False


class FascardErrorMarker(ErrorMarker, CurfewAbstract):
    
    ERROR_ENUMS = SlotErrorType.FASCAR_ERRORS
    CURFEW_CODES = [
        SlotErrorType.DISABLED,
    ]
    
    def _set_error_enum(self,bad_slot_state):  #NB: the two enum types have the same codes for fascard reported errors
        return bad_slot_state.slot_status
    
    def _find_errors(self):
        #TODO: Filter out locations in curfew
        self.bad_slot_states = self.initial_filter.filter(slot_status__lt=0, slot_status__gte=-5)
        self.schedules = EquipmentTypeSchedule.objects.filter(laundry_room=self.laundry_room)
        if self.schedules.count() >= 1:
            final_bad_slot_states = list()
            for bad_state in self.bad_slot_states:
                if bad_state.slot_status in self.CURFEW_CODES:
                    try:
                        r = self.check_curfew(bad_state)
                    except:
                        continue
                    if r: continue
                final_bad_slot_states.append(bad_state)
            self.bad_slot_states = final_bad_slot_states
        
    def _create_error_msg(self,bad_slot_state):
        return 'Error Reported by Fascard System'

class FlickeringErrorMarker(ErrorMarker):
    
    ERROR_ENUMS = [SlotErrorType.FLICKERING]

    def _set_error_enum(self,bad_slot_state):
        return SlotErrorType.FLICKERING
    
    def _find_errors(self):
        self.bad_slot_states = self.initial_filter.filter(duration__lte=config.ErrorMarkerConfig.FLICKER_DEF)
   
    def _create_error_msg(self,bad_slot_state):
        return 'Slot is flickering.'
    
class IdleErrorMarker(ErrorMarker):
    
    ERROR_ENUMS = [SlotErrorType.LONG_IDLE]
    
    def _set_error_enum(self,bad_slot_state):
        return SlotErrorType.LONG_IDLE
    
    def _create_error_msg(self,bad_slot_state):
        return 'Slot has been idle for too long.'
    
    def _find_errors(self):
        start_cutoff = datetime.utcnow() - timedelta(seconds=config.ErrorMarkerConfig.IDLE_MIN_SECONDS)
        durationQ = Q(duration__gte=config.ErrorMarkerConfig.IDLE_MIN_SECONDS) | ( Q(end_time=None) & Q(start_time__lte=start_cutoff) )
        excludeQ = Q(slot_status=MachineStateType.RUNNING) | Q(slot__slot_type=SlotType.DOUBLE)
        self.initial_filter = self.initial_filter.filter(durationQ).exclude(excludeQ)
        self.bad_slot_states = []
        for bss in self.initial_filter:
            #Chose the cutoff point
            idle_cutoff_seconds = bss.slot.idle_cutoff_seconds
            if idle_cutoff_seconds is None:
                idle_cutoff_seconds = config.ErrorMarkerConfig.IDLE_DEFAULT_SECONDS
            elif idle_cutoff_seconds < config.ErrorMarkerConfig.IDLE_MIN_SECONDS:
                idle_cutoff_seconds = config.ErrorMarkerConfig.IDLE_MIN_SECONDS
            elif idle_cutoff_seconds > config.ErrorMarkerConfig.IDLE_MAX_SECONDS:
                idle_cutoff_seconds = config.ErrorMarkerConfig.IDLE_MAX_SECONDS
            #Calculate the number of idle total_seconds()
            if bss.duration is not None:
                idle_seconds = bss.duration
            else:
                idle_seconds = (datetime.utcnow() - bss.start_time).total_seconds()
            #add to temp if appropriate 
            if idle_seconds > idle_cutoff_seconds:
                self.bad_slot_states.append(bss)
        
class LongRunningMarker(ErrorMarker):
    
    ERROR_ENUMS = [SlotErrorType.LONG_RUNNING]

    def _set_error_enum(self,bad_slot_state):
        return SlotErrorType.LONG_RUNNING
    
    def _find_errors(self):
        max_time = config.ErrorMarkerConfig.LONG_RUNNING_HOURS*3600
        self.still_running = deepcopy(self.initial_filter).filter(duration__gte=max_time,slot_status=MachineStateType.RUNNING).exclude(
                                                        end_time=None)
        self.not_running = deepcopy(self.initial_filter).filter(end_time=None,slot_status=MachineStateType.RUNNING)
        self.bad_slot_states = list(self.still_running)
        for nr in self.not_running:
            if (nr.recorded_time - nr.start_time).total_seconds() > max_time:
                self.bad_slot_states.append(nr)
        
    def _create_error_msg(self,bad_slot_state):
        return 'Long Running Machine'    

class ShortRunningMarker(ErrorMarker):
    
    ERROR_ENUMS = [SlotErrorType.SHORT_RUNNING]

    def _set_error_enum(self,bad_slot_state):
        return SlotErrorType.SHORT_RUNNING
    
    def _find_errors(self):
        self.bad_slot_states = self.initial_filter.filter(slot_status=MachineStateType.RUNNING,
                duration__lte=config.ErrorMarkerConfig.SHORT_RUNNING_MAX_SEC).exclude(end_time=None)
        
    def _create_error_msg(self,bad_slot_state):
        return 'Short Running Machine'


class DuplicateErrorMarker(ErrorMarker):

    ERROR_ENUMS = [SlotErrorType.DUPLICATE]

    def _set_error_enum(self,bad_slot_state):  #NB: the two enum types have the same codes for fascard reported errors
        return bad_slot_state.slot_status
    
    def _find_errors(self):
        self.bad_slot_states = self.initial_filter.filter(slot_status=SlotErrorType.DUPLICATE)
        
    def _create_error_msg(self,bad_slot_state):
        return 'Duplicate Machine Error'


class CurfewErrorMarker(ErrorMarker, CurfewAbstract):
    CURFEW_CODES = [
        SlotErrorType.DISABLED,
    ]
    ERROR_ENUMS = [SlotErrorType.DISABLED]

    def _find_errors(self):
        self.bad_slot_states = self.initial_filter.filter(slot_status=SlotErrorType.DISABLED)
        self.schedules = EquipmentTypeSchedule.objects.filter(laundry_room=self.laundry_room)
        final_bad_slot_states = list()
        if self.schedules.count() >= 1:
            for bad_state in self.bad_slot_states:
                try:
                    r = self.check_curfew(bad_state)
                    if r:
                        final_bad_slot_states.append(bad_state)
                except Exception as e:
                    continue
        self.bad_slot_states = final_bad_slot_states

    def _set_error_enum(self,bad_slot_state):
        return SlotErrorType.DISABLED

    def _create_error_msg(self,bad_slot_state):
        return 'Disabled Machine in Curfew'


# 
# from Reports.base_report import BaseReport
# class ReportGenerator(BaseReport):
#     
#     def generate(self):
#         self.set_file_name()
#         #Generate Error Report CSV
#         two_days_ago = datetime.utcnow()-timedelta(days=2)
#         universal_Q =  Q(slot_state__slot__is_active=True) & Q(slot_state__slot__laundry_room__is_active=True)
#         nonreported_Q = universal_Q  & ( Q(slot_state__end_time=None) | ( Q(error_type=SlotErrorType.LONG_TRANSACTION_GAP) & Q(slot_state__end_time__gte=two_days_ago)) ) 
#         
#         non_flickering_errors = self._find_non_flickering_errors(nonreported_Q)
#         double_barreled_idle_errors = self._find_double_barreled_errors()
#         rolledup_non_flickering = self._rollup_slot_errors(non_flickering_errors,double_barreled_idle_errors)     
#         flickering_errors = self._find_flickering_errors(universal_Q)
#         
#         
#         self._generate_results(rolledup_non_flickering,flickering_errors) #Creates self.resuls
#         #Generate List of buildings with current errors
#         self._generate_body_and_title()
# 
#     def set_file_name(self):
#         tm = datetime.now()
#         tm = tm.strftime('%Y_%m_%d_%H_%M_%S')
#         self.file_name = os.path.join(settings.BASE_DIR,'OutOfOrder_%s.csv' % tm)
#       
#     def _find_non_flickering_errors(self,universalQ):
#         non_flickering_errors = models.SlotStateError.objects.filter(universalQ).exclude(error_type=SlotErrorType.FLICKERING)
#         return  [nfe for nfe in non_flickering_errors]
# 
#     def _find_flickering_errors(self,universalQ):
#         lookback_until =  datetime.utcnow() - timedelta(hours=24)
#         flickering =  models.SlotStateError.objects.filter(
#                     universalQ,error_type=SlotErrorType.FLICKERING,slot_state__start_time__gte=lookback_until).values(
#                     'slot_state__slot__id').annotate(num_times=Count('id'),start_time=Min('slot_state__start_time'),end_time=Max('slot_state__end_time'),
#                     display_name=Max('slot_state__slot__web_display_name'),building_name=Max('slot_state__slot__laundry_room__display_name')).filter(num_times__gte=4) #TODO: make dynamic
#         return flickering
#     
#     def _find_double_barreled_errors(self):
#         cuttoff_case_when_statement = '''
#         case when idle_cutoff_total_seconds() is null then %s
#         when idle_cutoff_total_seconds() > %s then %s
#         when idle_cutoff_total_seconds() < %s then %s 
#         else idle_cutoff_total_seconds()
#         end 
#         ''' % (config.IDLE_DEFAULT_SECONDS,
#                config.IDLE_MAX_SECONDS,config.IDLE_MAX_SECONDS,
#                config.IDLE_MIN_SECONDS,config.IDLE_MIN_SECONDS)
#         
#         sql = '''
#             select *
#             from slot b join laundry_room c on b.laundry_room_id = c.id 
#             WHERE slot_type = '%s' and b.is_active=1 and c.is_active=1
#             AND (last_run_time is null OR UTC_TIMESTAMP() > DATE_SUB(last_run_time, INTERVAL -%s SECOND));
#             ''' % (SlotType.DOUBLE,cuttoff_case_when_statement)
#         slots =  models.Slot.objects.raw(sql)
#         SlotStateErrorMockup = namedtuple('SlotStateErrorMarkup',['slot_state','error_message'])
#         SlotStateMockup = namedtuple('SlotStateMarkup',['slot','slot_id','start_time','end_time'])
#         slot_state_errors = []
#         for slot in slots:
#             slot_state = SlotStateMockup(slot,slot.id,slot.last_run_time,None)
#             slot_state_error = SlotStateErrorMockup(slot_state,'Double Barreled Idle')
#             slot_state_errors.append(slot_state_error)
#         return slot_state_errors
#             
#     def _generate_body_and_title(self):
#         room_list = set([result[0] for result in self.results if result[0] != 'building name' and 'flickering' not in result[0].lower()])
#         if len(room_list) >0:
#             room_list = '\n'.join(room_list)
#             self.body = 'Rooms with new errors: %s' % room_list
#             self.title = 'Out of Order Report: New Errors'
#         else:
#             self.body = 'No unreported errors.'
#             self.title = 'Out of Order Report: No New Errors'
#         self.to_list = settings.DEFAULT_OOO_EMAIL_LIST
# 
#     def _rollup_flickering_errors(self,flickering):
#         pass
#     
#     def _rollup_slot_errors(self,non_flickering,double_barreled):
#         slot_errors = {}
#         errors = non_flickering+double_barreled
#         for x in errors:
#             if x.slot_state.slot_id not in slot_errors:
#                 slot_errors[x.slot_state.slot_id] = {'building name':x.slot_state.slot.laundry_room.display_name,
#                                                      'display name':x.slot_state.slot.web_display_name,
#                                                      'error(s)':set([x.error_message]),
#                                                      'start time':x.slot_state.slot.get_last_run_start(),
#                                                      'end time':x.slot_state.end_time}
#             else:
#                 slot_errors[x.slot_state.slot_id]['error(s)'].add(x.error_message)
#                 
#                 if slot_errors[x.slot_state.slot_id]['end time'] is None:
#                     pass
#                 elif x.slot_state.end_time is None:
#                     slot_errors[x.slot_state.slot_id]['end time'] = None
#                 elif x.slot_state.end_time > slot_errors[x.slot_state.slot_id]['end time']:
#                     slot_errors[x.slot_state.slot_id]['end time'] = x.slot_state.end_time
#             
#         for slot_error in slot_errors.values():
#             slot_error['error(s)'] = ','.join(slot_error['error(s)'])
#         return slot_errors
#     
#     def _generate_results(self,slot_errors,flickering_errors):
#         headers = ['building name','display name','start time','end time','error(s)']
#         rows = []
#         rows.append(headers)
#         for x in slot_errors.values():
#             this_row = []
#             for header in headers:
#                 this_row.append(x[header]) 
#             rows.append(this_row)
#         rows.append(['------------------------------ FLICKERING --------------------------------------------'])
#         for y in flickering_errors:
#             this_row = [y['building_name'],y['display_name'],y['start_time'],y['end_time'],'Flickering']
#             rows.append(this_row)
#         self.results = rows 
#         
#     def post_send(self):
#         marked_unreported = SlotStateError.objects.filter(is_reported=False)
#         marked_unreported.update(is_reported=True)