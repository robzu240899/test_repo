'''
Created on Mar 5, 2017

@author: Thomas
'''


LAUNDRY_GROUP_SQL = '''
insert into laundrydb.laundry_group(id,display_name,notes,is_active)
select * from laundry.laundry_group;
'''

LAUNDRY_ROOM_SQL = '''
insert into laundrydb.laundry_room(id,laundry_group_id,display_name,fascard_code,is_active,time_zone)
select id,laundry_group_id,display_name,fascar_code,is_active,time_zone from laundry.laundry_room;
'''

SLOT_SQL = '''

insert into laundrydb.slot(
    id,
    laundry_room_id,
    slot_fascard_id,
    web_display_name,
    clean_web_display_name,
    idle_cutoff_seconds,
    is_active,
    last_run_time,
    slot_type
    )
select
    id,
    laundry_room_id,
    slot_fascard_id,
    web_display_name,
    clean_web_display_name,
    idle_cutoff_seconds,
    is_active,
    last_run_time,
    slot_type
from laundry.slot;
'''

SLOT_STATE_SQL = '''

insert into laundrydb.slot_state(
id,
start_time,
end_time,
local_start_time,
local_end_time,
duration,
slot_status,
recorded_time,
local_recorded_time,
error_checking_complete,
certified_error_free,
has_endtime_guess,
is_filler_state,
is_guess_state,
state_order,
slot_id
)
select
id,
start_time,
end_time,
local_start_time,
local_end_time,
duration,
slot_status,
recorded_time,
local_recorded_time,
error_checking_complete,
certified_error_free,
has_endtime_guess,
is_filler_state,
is_guess_state,
state_order,
slot_id
from laundry.slot_state;
'''

SCRIPTS = [LAUNDRY_GROUP_SQL,LAUNDRY_ROOM_SQL,SLOT_SQL,SLOT_STATE_SQL]
