import logging
from datetime import datetime, date
from dateutil.relativedelta import relativedelta
from maintainx.api import MaintainxAPI
from upkeep.api import UpkeepAPI
from .enums import LocationLevel, DurationType
from queuehandler.job_creator import MetricsCreator
from .models import BillingGroup, LaundryRoomExtension

logger = logging.getLogger(__name__)

def trigger_metrics_compute(sender, instance, created, **kwargs) -> bool:
    if not created: return
    today = date.today()
    month_start_date = date(today.year, today.month, 1)
    possible_dates = [month_start_date]
    if isinstance(instance, BillingGroup):
        bg_instance = instance
        location_level_map = [
            (LocationLevel.BILLING_GROUP, [instance.id]),
        ]
    elif isinstance(instance, LaundryRoomExtension):
        bg_instance = instance.billing_group
        location_level_map = [
            (LocationLevel.LAUNDRY_ROOM, [instance.laundry_room.id])
        ]
    operations_start_date = getattr(bg_instance, 'operations_start_date', None)
    lease_term_start = getattr(bg_instance, 'lease_term_start', None)
    possible_dates.extend([operations_start_date, lease_term_start])
    possible_dates = [possible_date for possible_date in possible_dates if possible_date]
    start_date = min(possible_dates)
    end_date = today
    MetricsCreator.create_metrics(start_date, end_date, location_level_maps=location_level_map)
    start_date = date(start_date.year, start_date.month, 1)
    delta_months = relativedelta(max(start_date, end_date), min(start_date, end_date)).months
    for i in range(delta_months):
        monthly_end_date = start_date + relativedelta(days=1)
        MetricsCreator.create_metrics(start_date, monthly_end_date, duration_type=DurationType.MONTH, location_level_maps=location_level_map)
        start_date = start_date + relativedelta(months=1)
    return True

def _room_work_order(laundry_room_ext):
    ext_link = 'http://system.aceslaundry.com/admin/reporting/laundryroomextension/{}/change/'.format(laundry_room_ext.id)
    description = """ All new rooms demand the manual completion of a Laundry Room Extension.
    Link of automatically created Laundry Room Extension: {}"
    """.format(ext_link)
    location = laundry_room_ext.laundry_room
    upkeep_payload = {
        'title' : f'LaundryRoomExtension must be completed for {laundry_room_ext}',
        'description' : description,
        'location' : getattr(location, "upkeep_code"),
        'assignedToUser' : 'qX89EYRbka', #Juanyta
        'category' : 'Administrative',
        'priority' : 2
    }
    maintainx_payload = {
        'title' : f'LaundryRoomExtension must be completed for {laundry_room_ext}',
        'description' : description,
        'locationId' : getattr(location, "maintainx_id"),
        'assignees' : [{"type": "USER","id": 157408}], #juanita
        'categories' : ['Standard Operating Procedure'],
        'priority' : "MEDIUM"
    }
    try:
        api = UpkeepAPI()
        api.create_work_order(upkeep_payload)
    except Exception as e:
        print (e)
        logger.error(e)
    try:
        api = MaintainxAPI()
        api.create_work_order(maintainx_payload)
    except Exception as e:
        print (e)
        logger.error(e)


def room_work_order(sender, instance, created, **kwargs):
    if not created: return
    _room_work_order(instance)