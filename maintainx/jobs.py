import logging
import pytz
import time
from typing import List
from urllib.parse import urlencode
from datetime import datetime
from dateutil.parser import parse
from main.decorators import ProductionCheck
from .exceptions import MaintainxTooManyRequests
from maintainx.api import MaintainxAPI
from cmmsproviders.workorders.manager import WorkOrderManager
from maintainx.config import WORK_ORDER_FIELD_MAP, USER_FIELD_MAP
from maintainx.managers.managers import MaintainxMachineManager, MaintainxCardReaderManager
from roommanager.models import MaintainxWorkOrderPart, MaintainxWorkOrderRecord, MaintainxUser, Machine, CardReaderAsset, MachineMeter, CardReaderMeter, LaundryRoomMeter


logger = logging.getLogger(__name__)

class MaintainxWorkOrderFetcher(WorkOrderManager):
    DATE_FIELDS = ['created_date', 'completed_date', 'updated_date']
    SORT_FIELD = '-updatedAt'
    CONVERT_FROM = 'UTC'
    CONVERT_TO = 'America/New_York'
    model = MaintainxWorkOrderRecord
    WORK_ORDER_FIELD_MAP = WORK_ORDER_FIELD_MAP
    provider_id_attr = 'maintainx_id'
    post_process_fields = ['assignees']

    def __init__(self):
        self.api = MaintainxAPI()

    @classmethod
    def get_assignees(self, ids: List[int]) -> List[MaintainxUser]:
        assignees = []
        for assignee_id in ids:
            try:
                user = MaintainxUser.objects.get(maintainx_id=assignee_id)
            except MaintainxUser.DoesNotExist:
                response = self.api.get_user(assignee_id)
                transformed_data = {}
                for provider_field_name, local_field_name in USER_FIELD_MAP:
                    transformed_data[local_field_name] = response.get(provider_field_name, None)
                user = MaintainxUser.objects.create(**transformed_data)
            assignees.append(user)

    def transform_record(self, obj_payload, fieldmap):
        d = {}
        for old,new in fieldmap.items():
            val = obj_payload.get(old, None)
            if isinstance(val, list):
                if len(val)>0 and isinstance(val[0], str): val = ','.join(val)
                #if isinstance(val[0], dict):
                # if dict and nested structre, pop from d so d is clean for saving
                # gotta post process nested structures after object has been saved.
                #     -> specially for m2m relationships
            if val and new in self.DATE_FIELDS:
                val = parse(val).replace(tzinfo=None)
                val = self.clean_date(val)
            d[new] = val
        return d

    def _convert_to_utc_date_pointer(self, record: MaintainxWorkOrderRecord, field: str):
        if record and getattr(record, field):
            converted_date = self.clean_date(
                getattr(record, field), convert_from='America/New_York', convert_to='UTC'
            )
        else:
            converted_date = datetime(2000,1,1)
        return converted_date.replace(tzinfo=pytz.UTC)

    def _handle_parts(self, record):
        if not record.get('parts'): return None
        for part in record.get('parts'):
            try:
                part_record = MaintainxWorkOrderPart.objects.get(part.get('id'))
            except MaintainxWorkOrderPart.DoesNotExist:
                pass
            except Exception as e:
                pass


    def _fetch_records(self):
        latest_db_record = self.model.objects.all().order_by('-timestamp').first()
        latest_record_created = self.model.objects.all().order_by('-created_date').first()
        latest_creation_date = self._convert_to_utc_date_pointer(latest_record_created, 'created_date')
        latest_record_updated = self.model.objects.all().order_by('-updated_date').first()
        latest_update_date = self._convert_to_utc_date_pointer(latest_record_updated, 'updated_date')
        to_create = []
        to_update = []
        cursor = None
        while True:
            get_request_params = {'sort' : self.SORT_FIELD}
            if cursor: get_request_params['nextCursor'] = cursor
            response =  self.api.get_work_orders(
                params = get_request_params,
                expand_on=['assignees', 'categories', 'asset', 'location', 'procedure', 'parts']
            )
            if not response['workOrders']: break
            for record in response['workOrders']:
                record_created_at = parse(record['createdAt'])
                record_udpdated_at = parse(record['updatedAt'])
                if record_created_at > latest_creation_date:
                    to_create.append(record)
                    continue
                if record_udpdated_at > latest_update_date:
                    to_update.append(record)
                    continue
                if record_created_at <= latest_creation_date and record_udpdated_at <= latest_update_date:
                    return to_create, to_update
            if not response['nextCursor']: break
            cursor = urlencode(response['nextCursor'])
        return to_create, to_update

    def run(self, delta_hours=28):
        to_create, to_update = self._fetch_records()
        for record in to_create:
            transformed_record = self.transform_record(record, self.WORK_ORDER_FIELD_MAP)
            try:
                MaintainxWorkOrderRecord.objects.create(**transformed_record)
                #TODO: Handle parts
            except Exception as e:
                logger.error(f"Failed creating work order record: {e}", exc_info=True)
        for record in to_update:
            try:
                self.update_record(record)
            except Exception as e:
                logger.error(f"Failed updating work order record: {e}", exc_info=True)

    @classmethod
    def run_as_job(cls):
        ins = MaintainxWorkOrderFetcher()
        ins.run()
    

class MaintainxSync():
    API_CLASS = MaintainxAPI

    @ProductionCheck
    def _sync_asset_meters_centralized(self) -> None:
        """
        Syncs all upkeep meters associated with either a Machine or CardReader using a 60 request per minute
        buffer so we can comply with Maintainx's API rate limit
        """
        api = self.API_CLASS()
        api_calls_limit = 60
        #get list of both machines and card readers to be updated
        #for/while to process 60 per minute.
        meters = list(MachineMeter.objects.filter(maintainx_id__isnull=False))
        meters.extend(CardReaderMeter.objects.filter(maintainx_id__isnull=False))
        meters.extend(LaundryRoomMeter.objects.filter(maintainx_id__isnull=False))
        start = time.time()
        global_count = 0
        count = 0
        for i in range(0, len(meters), 100):
            array_payload = []
            for meter in meters[i:i+100]:
                try:
                    if isinstance(meter, MachineMeter) or isinstance(meter, CardReaderMeter): meter_val = getattr(meter, 'transactions_counter', None)
                    elif isinstance(meter, LaundryRoomMeter): meter_val = getattr(meter, 'dryers_start_counter', None)
                    else: meter_val = None
                    if meter_val == 0 or meter_val == None: continue
                    array_payload.append({"meterId" : int(meter.maintainx_id), "value": meter_val})
                except Exception as e:
                    logger.error("Failed adding meter for {} with id {} to batch array payload. {}".format(type(meter), meter.id, e))
            try:
                api.update_asset_meter_reading_batch(array_payload)
            except Exception as e:
                logger.error(f"Failed updating batch during iteration {i}th. Error: {e}")
            count +=1
            count, start = self.reset_counters(count=count, start=start, api_calls_limit=api_calls_limit)
            global_count +=1
        logger.info(f"Finished syncing all meters. Global count: {global_count}")

    @classmethod
    def sync_asset_meters_centralized(cls) -> None:
        ins = MaintainxSync()
        ins._sync_asset_meters_centralized()

    @ProductionCheck
    def _sync_assets_centralized(self, machines=[], card_readers=[]):
        """
        Syncs all upkeep meters associated with either a Machine or CardReader using a 60 request per minute
        buffer so we can comply with Maintainx's API rate limit
        """
        #get list of both machines and card readers to be updated
        #for/while to process 60 per minute.
        api_calls_limit = 30

        from django.db.models.query import QuerySet as qs

        if not machines: machines = Machine.objects.filter(maintainx_id__isnull=False)
        if not card_readers: card_readers = CardReaderAsset.objects.filter(maintainx_id__isnull=False)

        if type(machines) == qs: assets = list(machines)
        else: assets = machines

        if type(card_readers) == qs: assets.extend(list(card_readers))
        else: assets.extend(card_readers)
        machine_manager = MaintainxMachineManager()
        card_reader_manager = MaintainxCardReaderManager()
        start = time.time()
        global_count = 0
        count = 0
        for asset in assets:
            try:
                if isinstance(asset, Machine): manager = machine_manager
                elif isinstance(asset, CardReaderAsset): manager = card_reader_manager
                else: raise Exception("Unknown asset type")
                manager.create_or_update(asset)
                logger.info(f"Updated asset {asset}.")
            except MaintainxTooManyRequests: time.sleep(60)
            except Exception as e: logger.info(f"Failed updating asset {asset}. {e}")
            count += 1
            count, start = self.reset_counters(count=count, start=start, api_calls_limit=api_calls_limit)
            global_count +=1
        logger.info(f"Finished syncing all assets. Global count: {global_count}")


    @classmethod
    def sync_assets_centralized(cls) -> None:
        ins = MaintainxSync()
        ins._sync_assets_centralized()


    def reset_counters(self, count, start, api_calls_limit):
        """
        Apply a timeout to the sync of assets in MaintainX
        """
        # reset counter
        if count == api_calls_limit:
            logger.info(f"Hit {api_calls_limit} api calls limit")
            delta = (time.time() - start)

            if delta < 60:
                logger.info(f"delta: {delta}")
                logger.info(f"sleeping for: {65 - delta} seconds")
                time.sleep(65 - delta)
                start = time.time()

            count = 0
            logger.info("restarted counters")

        return count, start