import copy
from outoforder.models import SlotStateError, SlotState
from roommanager.models import Slot

def get_slot_fascard_url(slot):
        room_fascard_id = slot.laundry_room.fascard_code
        slot_fascard_id = slot.slot_fascard_id
        url = 'https://admin.fascard.com/86/MachineHist?locationID={}&machID={}'
        return url.format(room_fascard_id, slot_fascard_id)

def get_work_order_url(slot):
        """
            Retrieves upkeep URL to create a work order for the asset associated to the 
            given slot
        """
        base_url = 'https://app.onupkeep.com/web/work-orders/new?linked-asset={}&linked-location={}'
        machine = Slot.get_current_machine(slot)
        final_url = None
        if machine.upkeep_id and slot.laundry_room and slot.laundry_room.upkeep_code:
            final_url = base_url.format(machine.upkeep_id, slot.laundry_room.upkeep_code)
        return final_url

def get_upkeep_url(slot):
    machine = Slot.get_current_machine(slot)
    return machine.get_upkeep_asset_url()

def get_maintainx_url(slot):
    machine = Slot.get_current_machine(slot)
    return machine.get_maintainx_asset_url()


def set_error_start_time(slot_error):
    try:
        error_start_time = slot_error.slot_state.start_time
    except:
        error_start_time = ''

def set_duration(slot_error):
    try:
        seconds = getattr(slot_error.slot_state, 'duration', 0)
        if seconds == 0 or seconds == None:
            final_duration = 0
            time_str = ''
        elif seconds <= 120:
            final_duration = seconds
            time_str = 'seconds'
        elif seconds > 120 and seconds <= 5400:
            final_duration = seconds / 60.0
            time_str = 'minutes'
        elif seconds >= 5400 and seconds <=86400:
            final_duration = ((seconds / 60.0) / 60.0)
            time_str = 'hours'
        elif seconds > 86400:
            final_duration = (((seconds / 60.0) / 60.0) / 12.0)
            time_str = 'days'
                #return in minutes
        duration = "{:.2f} {}".format(final_duration, time_str)
    except:
        duration = ''
    return duration
    

def map_slot_error_as_dict(slot_error, error_start_time=None, fields=None):
    if not error_start_time:
        error_start_time = set_error_start_time(slot_error)
    duration = set_duration(slot_error)
    error_data = {
        'building name':slot_error.slot_state.slot.laundry_room.display_name,
        'display name':slot_error.slot_state.slot.web_display_name,
        'fascard_id': slot_error.slot_state.slot.slot_fascard_id,
        'internal_id': slot_error.slot_state.slot.id,
        'error(s)':set([slot_error.error_message]),
        'start time': error_start_time,
        'end time':slot_error.slot_state.end_time,
        'duration': duration,
        'fascard_url': get_slot_fascard_url(slot_error.slot_state.slot),
        'upkeep_create_work_order' : get_work_order_url(slot_error.slot_state.slot),
        'upkeep_asset_url' : get_upkeep_url(slot_error.slot_state.slot)
    }

    if fields is None:
        #if no fields list was specified return all by default
        final_data = copy.deepcopy(error_data)
    else:
        final_data = {}
        for f in fields:
            final_data[f] = error_data.get(f, None)

    if isinstance(slot_error, SlotStateError):
        #if machine status is OK it means that the mlvmacherror was not ingested properly
        #and the status_text was setted by default to OK. So we better don't show it in the report
        if not slot_error.slot_state.mlvmacherror_description == 0:
            final_data['mlvmacherror_description'] = slot_error.get_mlv_error()
        final_data['slot_status_text'] =  slot_error.get_status_text()
        
    return final_data