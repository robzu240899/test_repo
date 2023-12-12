import pytz
import logging
import time
from datetime import datetime, timedelta
from dateutil.parser import parse
from django.db import transaction
from cmmsproviders.workorders.manager import WorkOrderManager
from roommanager.models import WorkOrderRecord, WorkOrderPart, UpkeepUser
from .api import UpkeepAPI
from .config import WORK_ORDER_FIELD_MAP, WORK_ORDER_PART_FIELDMAP, UPKEEP_USER_FIELD_MAP
from .enums import WorkOrderStatus

logger = logging.getLogger(__name__)


class WorkOrderFetcher(WorkOrderManager):
    DATE_FIELDS = ['created_date', 'completed_date', 'updated_date', 'duedate']
    CONVERT_FROM = 'UTC'
    CONVERT_TO = 'America/New_York'
    model = WorkOrderRecord
    WORK_ORDER_FIELD_MAP = WORK_ORDER_FIELD_MAP
    provider_id_attr = 'upkeep_id'

    def __init__(self):
        self.api = UpkeepAPI()

    def _process_records(self, new_records):
        for upkeep_record in new_records:
            logger.info("Creating new work order record with ID: {}".format(upkeep_record['id']))
            with transaction.atomic():
                transformed_record = self.transform_record(upkeep_record, WORK_ORDER_FIELD_MAP)
                existing = WorkOrderRecord.objects.filter(upkeep_id=transformed_record['upkeep_id'])
                if existing:
                    self.update_record(upkeep_record)
                    work_order = WorkOrderRecord.objects.get(upkeep_id=upkeep_record.get('id'))
                else:
                    work_order = WorkOrderRecord.objects.create(**transformed_record)                    
                if 'parts' in upkeep_record:
                    logger.info("Saving parts")
                    val = upkeep_record.get('parts')
                    for part in val:
                        formatted_part = self.transform_record(part, WORK_ORDER_PART_FIELDMAP)
                        #what if the part already exists?
                        try:
                            record = WorkOrderPart.objects.get(upkeep_id=formatted_part.get('upkeep_id'))
                            continue
                        except WorkOrderPart.DoesNotExist:
                            pass
                        except Exception as e:
                            logger.error(e, exc_info=True)
                            continue
                        try:
                            part_obj = WorkOrderPart.objects.create(**formatted_part)
                            work_order.parts.add(part_obj)
                        except Exception as e:
                            logger.error(f"Failed saving part for work order {upkeep_record}: {e}")
                    work_order.save()
        logger.info("Finished processing new work orders")


    def run(self, delta_hours=28):
        unix_timestamp = (datetime.now() - timedelta(hours=delta_hours)).timestamp() * 1000
        new_records = self.api.get_work_orders(
            createdAtGreaterThan=unix_timestamp,
            includes='parts')
        if not new_records: return
        to_update = self.api.get_work_orders(updatedAtGreaterThan=unix_timestamp)
        time.sleep(5)
        for upkeep_record in to_update:
            try:
                self.update_record(upkeep_record)
            except Exception as e:
                logger.error("Failure updating work order ({}): {}".format(
                    upkeep_record['id'], e))
                continue

    def _full_sync(self, start_at=50000, stop_at=0, step_size=-1000):
        """
        Start_at represents the number of hours to go back in time to start ingesting work orders.

        Tries re ingesting work orders so parts are saved (we missed parts in our first version)
        """
        if step_size > 0: raise Exception("Step size must be negative")
        for delta in range(start_at, stop_at, step_size):
            unix_timestamp_upper = (datetime.now() - timedelta(hours=delta)).timestamp() * 1000
            unix_timestamp_lower = (datetime.now() - timedelta(hours=delta + step_size )).timestamp() * 1000
            new_records = self.api.get_work_orders(
                createdAtGreaterThan=unix_timestamp_upper,
                createdAtLessThan=unix_timestamp_lower,
                includes='parts'
            )
            if not new_records: continue
            self._process_records(new_records)
            time.sleep(2)


    @classmethod
    def run_as_job(cls):
        ins = WorkOrderFetcher()
        ins.run()


class UserFetcher():

    def _sync_users(self):
        api = UpkeepAPI()
        user_records = api.get_users()
        users = []
        for record in user_records:
            user_id = record.get('id')
            if not user_id: continue
            try:
                user = UpkeepUser.objects.get(upkeep_id=user_id)
            except UpkeepUser.DoesNotExist:
                transformed_data = {}
                for provider_field_name, local_field_name in UPKEEP_USER_FIELD_MAP.items():
                    transformed_data[local_field_name] = record.get(provider_field_name, None)
                user = UpkeepUser.objects.create(**transformed_data)
            users.append(user)
        return users


    @classmethod
    def run_as_job(cls):
        ins = UserFetcher()
        ins._sync_users()