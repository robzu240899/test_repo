'''
Created on Mar 5, 2017

@author: Thomas
'''


FASCARD_USER_SQL = '''
insert into laundrydb.fascard_user(
    name,
    addr_1,
    addr_2,
    city,
    state,
    zip,
    mobile_phone,
    office_phone,
    email_address,
    comments,
    language,
    notify_cycle_complete,
    fascard_creation_date,
    fascard_last_activity_date,
    balance,
    bonus,
    discount,
    free_starts,
    status,
    is_employee,
    loyalty_points,
    ballance_spent,
    bonus_spent,
    free_starts_spent,
    reload_method,
    reload_balance,
    reload_bonus,
    cash_spent,
    credit_card_spent,
    user_group_id,
    last_location_id,
    xxx_caution_fascard_user_id,
    fascard_user_account_id,
    laundry_group_id,
    coupons)
Select 
    name,
    addr_1,
    addr_2,
    city,
    state,
    zip,
    mobile_phone,
    office_phone,
    email_address,
    comments,
    language,
    notify_cycle_complete,
    fascard_creation_date,
    fascard_last_activity_date,
    balance,
    bonus,
    discount,
    free_starts,
    status,
    is_employee,
    loyalty_points,
    ballance_spent,
    bonus_spent,
    free_starts_spent,
    reload_method,
    reload_balance,
    reload_bonus,
    cash_spent,
    credit_card_spent,
    user_group_id,
    last_location_id,
    xxx_caution_fascard_user_id,
    fascard_user_account_id,
    laundry_group_id,
    coupons 
from laundry.laundry_fascard_user;
'''

TRANSACTION_SQL = '''

insert into laundrydb.laundry_transaction
(
    external_fascard_id,
    laundry_room_id,
    slot_id,
    machine_id,
    web_display_name,
    first_name,
    last_name,
    local_transaction_date,
    transaction_type,
    credit_card_amount,
    cash_amount,
    balance_amount,
    last_four,
    utc_transaction_time,
    local_transaction_time,
    external_fascard_user_id,
    fascard_user_id
)
select 
    transaction_id,
    laundry_room_id,
    slot_id,
    null,
    web_display_name,
    first_name,
    last_name,
    local_transaction_date,
    transaction_type,
    credit_card_amount,
    cash_amount,
    balance_amount,
    last_four,
    utc_transaction_time,
    local_transaction_time,
    user_account_id, 
    null
from laundry.laundry_transaction;

'''

TRANSACTION_USER_LINK_SQL = '''
UPDATE laundrydb.laundry_transaction a 
JOIN laundrydb.laundry_room b 
on a.laundry_room_id = b.id 
JOIN laundrydb.fascard_user c
ON b.laundry_group_id = c.laundry_group_id and a.fascard_user_account_id = c.external_fascard_user_id
SET a.fascard_user_id = c.id;
'''

