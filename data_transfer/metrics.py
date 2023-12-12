'''
Created on Apr 14, 2017

@author: Thomas
'''


SQL_BILLING_GROUP = '''
insert into laundrydb.billing_group(
    id,
    display_name,
    schedule_type,
    min_compensation_per_day
)
select 
    id,
    display_name,
    schedule_type,
    min_compensation_per_day
from laundry.billing_group;
'''

SQL_LAUNDRY_ROOM_EXTENSION = '''
insert into laundrydb.laundry_room_extension(
    laundry_room_id,
    billing_group_id,
    num_units,
    square_feet_residential,
    has_elevator,
    is_outdoors
)
select 
    id,
    billing_group_id,
    num_units,
    square_feet_residential,
    has_elevator,
    is_outdoors
from laundry.laundry_room;
'''

SQL_REVENUE_SPLIT_RULE = '''
insert into laundrydb.revenue_split_rule (
    id,
    billing_group_id,
    revenue_split_formula,
    base_rent,
    landloard_split_percent,
    breakpoint,
    start_gross_revenue,
    end_gross_revenue,
    start_date,
    end_date
)
select 
    id,
    billing_group_id,
    revenue_split_formula,
    min_payment,
    landloard_split_percent,
    split_threshold,
    start_gross_revenue,
    end_gross_revenue,
    start_date,
    final_date
from laundry.revenue_split_rule;

'''

SQL_EXPENSE_TYPE = '''
insert into laundrydb.expense_type(
    id,
    display_name,
    description,
    expense_type
)
select 
    id,
    display_name,
    description,
    expense_type
from laundry.expense_type;
'''

SQL_EXPENSE_TYPE_MAP = '''
insert into laundrydb.billing_group_expense_type_map
(
    id,
    billing_group_id,
    expense_type_id,
    default_amount
)
select 
    id,
    billing_group_id,
    expense_type_id,
    default_amount
from laundry.laundry_room_expense_expense_type_map
where billing_group_id is not null;
'''

SCRIPTS = [SQL_BILLING_GROUP,SQL_LAUNDRY_ROOM_EXTENSION,SQL_REVENUE_SPLIT_RULE,
           SQL_EXPENSE_TYPE,SQL_EXPENSE_TYPE_MAP]


   