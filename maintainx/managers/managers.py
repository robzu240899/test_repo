import logging
import pytz
from typing import List
from datetime import datetime
from dateutil.parser import parse
from urllib.parse import urlencode
from django.db import transaction
from django.conf import settings
from cmmsproviders.assets.manager import BaseAssetManager, AssetType
from cmmsproviders.locations.manager import BaseLocationManager
from cmmsproviders.workorders.manager import WorkOrderManager
from roommanager.enums import HardwareType
from roommanager.helpers import UploadAssetAttachments
from roommanager.models import MaintainxWorkOrderPart, MaintainxWorkOrderRecord, MaintainxUser, LaundryRoom, LaundryRoomMeter
from main.decorators import ProductionCheck
from maintainx.api import MaintainxAPI
from maintainx.config import WORK_ORDER_FIELD_MAP, WORK_ORDER_PART_FIELD_MAP, USER_FIELD_MAP
from maintainx.enums import MaintainxDefaultCategories
from upkeep.api import UpkeepAPI
from .helpers import MachineHelper, CardReaderHelper


logger = logging.getLogger(__name__)


class UpkeepLocationManager(BaseLocationManager):
    API_CLASS = UpkeepAPI
    provider_id_attr = 'upkeep_code'


class UpkeepAssetManager(BaseAssetManager):
    API_CLASS = UpkeepAPI
    provider_id_attr = 'upkeep_id'
    provider_meter_id_attr = 'upkeep_id'
    extra_fields_params_name = 'customFieldsAsset'
    provider_location_id_attr = 'upkeep_code'
    provider_name = 'Upkeep'
    location_manager = UpkeepLocationManager
    asset_provider_base_url = 'https://app.onupkeep.com/#/app/assets/view/{}'

    def _post_process_machine_creation(self, machine: AssetType) -> None:
        fields = list()
        for field in ('asset_picture', 'asset_serial_picture'):
            if getattr(machine, field): fields.append(field)
        self.attach_images_work_oders(machine, fields)

    def _handle_extra_fields(self, asset: AssetType, asset_payload: dict, local_custom_fields: list):
        update_fields, new_fields = self._fetch_extra_fields(asset, asset_payload, local_custom_fields)
        for field in update_fields:
            self.api.update_custom_field(
                getattr(asset, self.provider_id_attr),
                field.get('provider_id'),
                field.get('local_fields')
            )
        if new_fields: asset_payload.update({self.extra_fields_params_name: new_fields})
        return asset_payload

    def _format_provider_custom_fields(self, fields):
        return fields


class MaintainxLocationManager(BaseLocationManager):
    API_CLASS = MaintainxAPI
    provider_id_attr = 'maintainx_id'


class MaintainxAssetManager(BaseAssetManager):
    API_CLASS = MaintainxAPI
    provider_id_attr = 'maintainx_id'
    provider_meter_id_attr = 'maintainx_id'
    extra_fields_params_name = 'extraFields'
    provider_location_id_attr = 'maintainx_id'
    provider_name = 'Maintainx'
    location_manager = MaintainxLocationManager
    asset_provider_base_url = 'https://app.getmaintainx.com/assets/{}'

    def _post_process_machine_creation(self, machine: AssetType) -> None:
        pass
        #TODO: Automatically add pictures as attachments to machine via API call

    def _handle_extra_fields(self, asset: AssetType, asset_payload: dict, local_custom_fields: list) -> dict:
        update_fields, new_fields = self._fetch_extra_fields(asset, asset_payload, local_custom_fields)
        update_fields = [field['local_field'] for field in update_fields]
        fields = update_fields + new_fields
        final_payload = {}
        for field in fields:
            final_payload[field.get('name')]  = field.get('value') 
        if fields: asset_payload.update({self.extra_fields_params_name: final_payload})
        return asset_payload

    def build_meter_payload(self, asset: AssetType, asset_payload: dict) -> dict:
        meter_name  = asset_payload.get('name') + ' Meter'
        payload = {
            'name' : meter_name,
            'unit' : settings.MAINTAINX_METER_UNITS,
            'readingFrequency' : {'type': settings.MAINTAINX_METER_FREQUENCY},
            'locationId' : asset_payload.get('location')
        }
        if asset: payload['assetId'] = int(getattr(asset, 'maintainx_id', None))
        return payload

    def _format_provider_custom_fields(self, fields):
        return [{'name':k, 'value':v} for k,v in fields.items()]


class MaintainxMachineManager(MachineHelper, MaintainxAssetManager):
    hardware_type = HardwareType.MACHINE
    field_name_in_hardwarebundle = 'machine' #Field name in HardwareBundle model
    asset_code_field_name = 'asset_code'
    base_machine_url = 'https://system.aceslaundry.com/admin/roommanager/machine/{}/change/'
    create_required_fields = (
        'asset_code',
        'machine_type',
        'equipment_type'
    )

    def _get_custom_fields_payload(self, machine: AssetType) -> list:
        """
        returns payload to populate custom fields offered by provider
        """
        return [
            {
                'name' : 'Serial Number',
                'value' : str(getattr(machine, 'asset_serial_number', '')),
                'unit' : 'serial_number'
            },
            {
                'name' : 'Model',
                'value' : machine.get_asset_model(),
                'unit' : 'model'
            }
        ]

    def build_asset_payload(self, machine: AssetType) -> dict:
        asset_payload = super(MaintainxMachineManager, self).build_asset_payload(machine)
        return {
            'name' : asset_payload.get('name'),
            'description' : asset_payload.get('description'),
            'locationId' : int(asset_payload.get('location')),
            'barcode' : asset_payload.get('serial'),
            'assetTypes' : [asset_payload.get('category')],
        }

    def post_process(self, asset):
        """
        function called after creating/updating asset.
        """
        UploadAssetAttachments.run(asset.id)


class MaintainxCardReaderManager(CardReaderHelper, MaintainxAssetManager):
    category = 'card-reader'
    base_url = 'https://system.aceslaundry.com/admin/roommanager/cardreaderasset/{}/change/'
    hardware_type = HardwareType.CARD_READER
    field_name_in_hardwarebundle = 'card_reader' #Field name in HardwareBundle model
    asset_code_field_name = 'card_reader_tag'   

    def _get_custom_fields_payload(self, card_reader: AssetType) -> list:
        return []

    def build_asset_payload(self, cardreader: AssetType) -> dict:
        asset_payload = super(MaintainxCardReaderManager, self).build_asset_payload(cardreader)
        return {
            'name' : asset_payload.get('name'),
            'description' : asset_payload.get('description'),
            'locationId' : int(asset_payload.get('location')),
            'barcode' : asset_payload.get('serial'),
            'assetTypes' : [asset_payload.get('category')],
        }


class MaintainxWorkOrderManager(WorkOrderManager):
    DATE_FIELDS = ['created_date', 'completed_date', 'updated_date']
    SORT_FIELD = '-updatedAt'
    API_CLASS = MaintainxAPI
    CONVERT_FROM = 'UTC'
    CONVERT_TO = 'America/New_York'
    model = MaintainxWorkOrderRecord
    WORK_ORDER_FIELD_MAP = WORK_ORDER_FIELD_MAP
    provider_id_attr = 'maintainx_id'


    def get_work_order_assigness(self, records: List[dict]=None) -> List[MaintainxUser]:
        assignees = []
        for record in records:
            user_id = record.get('id')
            if not user_id: continue
            try:
                user = MaintainxUser.objects.get(maintainx_id=user_id)
            except MaintainxUser.DoesNotExist:
                if not 'name' in record:
                    try: user_data = self.API.get_user(user_id)
                    except: user_data = None
                else: user_data = record
                if user_data:
                    transformed_data = {}
                    for provider_field_name, local_field_name in USER_FIELD_MAP.items():
                        transformed_data[local_field_name] = user_data.get(provider_field_name, None)
                    user = MaintainxUser.objects.create(**transformed_data)
                else:
                    user = None
            if user: assignees.append(user)
        return assignees

    def get_work_order_parts(self, parts_list: List[dict]=[]) -> List[MaintainxWorkOrderPart]:
        parts = []
        for part_record in parts_list:
            try:
                part = MaintainxWorkOrderPart.objects.get(maintainx_id=part_record.get('id'))
            except MaintainxWorkOrderPart.DoesNotExist:
                transformed_record = self.transform_record(part_record, WORK_ORDER_PART_FIELD_MAP)
                part = MaintainxWorkOrderPart.objects.create(**transformed_record)
            parts.append(part)
        return parts

    def transform_record(self, obj_payload, fieldmap):
        """
        parses non-nested fields returned via API.

        Parts and Assignees are processed independently since they are nested fields.
        """
        record = {}
        for old,new in fieldmap.items():
            val = obj_payload.get(old, None)
            if isinstance(val, list):
                #handle categories field, with the form: ['Inspection', 'Project'] -> 'Inspection,Project'
                if len(val) > 0 and isinstance(val[0], str): val = ','.join(val)
            if val and new in self.DATE_FIELDS:
                val = parse(val).replace(tzinfo=None)
                val = self.clean_date(val)
            record[new] = val
        return record

    def _convert_date_pointer_to_utc(self, record: MaintainxWorkOrderRecord, field: str):
        if record and getattr(record, field):
            converted_date = self.clean_date(
                getattr(record, field), convert_from='America/New_York', convert_to='UTC'
            )
        else:
            converted_date = datetime(2000,1,1)
        return converted_date.replace(tzinfo=pytz.UTC)

    def save_record(self, record: dict, transformed_record: dict) -> bool:
        obj = self.model.objects.create(**transformed_record)
        assignees = self.get_work_order_assigness(record.get('assignees', []))
        parts = self.get_work_order_parts(record.get('parts', []))
        for assignee in assignees: obj.assignees.add(assignee)
        for part in parts: obj.parts.add(part)
        obj.save()
        return True

    def _sync_records(self):
        latest_record_created = self.model.objects.all().order_by('-created_date').first()
        latest_creation_date = self._convert_date_pointer_to_utc(latest_record_created, 'created_date')
        latest_record_updated = self.model.objects.all().order_by('-updated_date').first()
        latest_update_date = self._convert_date_pointer_to_utc(latest_record_updated, 'updated_date')
        cursor = None
        while True:
            get_request_params = {'sort' : self.SORT_FIELD}
            if cursor: get_request_params['cursor'] = cursor
            response =  self.API.get_work_orders(
                params = get_request_params,
                expand_on=['assignees', 'categories', 'asset', 'location', 'procedure', 'parts']
            )
            if not response['workOrders']: break
            for record in response['workOrders']:
                record_created_at = parse(record['createdAt'])
                record_udpdated_at = parse(record['updatedAt'])
                transformed_record = self.transform_record(record, self.WORK_ORDER_FIELD_MAP)
                with transaction.atomic():
                    if record_created_at > latest_creation_date:
                        self.save_record(record, transformed_record)
                        continue
                    if record_udpdated_at > latest_update_date:
                        #TODO: Double check this method works properly
                        self.update_record(record)
                        continue
                if record_created_at <= latest_creation_date and record_udpdated_at <= latest_update_date:
                    return True
            if not response['nextCursor']: break
            cursor = response['nextCursor']
        return True

    def _resync_all_records(self):
        cursor = None
        while True:
            get_request_params = {'sort' : self.SORT_FIELD}
            if cursor: get_request_params['cursor'] = cursor
            response =  self.API.get_work_orders(
                params = get_request_params,
                expand_on=['assignees', 'categories', 'asset', 'location', 'procedure', 'parts']
            )
            if not response['workOrders']: break
            for record in response['workOrders']:
                with transaction.atomic():
                    self.update_record(record)
            if not response['nextCursor']: break
            cursor = response['nextCursor']


    @classmethod
    def run_fetch_as_job(cls):
        ins = MaintainxWorkOrderManager()
        ins._sync_records()
        ins.sync_work_order_parts()
        ins.sync_maintainx_users()

    def sync_work_order_parts(self):
        api = MaintainxAPI()
        parts = api.get_parts()
        records = self.get_work_order_parts(parts_list=parts)

    def sync_maintainx_users(self):
        api = MaintainxAPI()
        user_records = api.get_user() #no params returns entire user list
        records = self.get_work_order_assigness(user_records)

    def create_work_order(self, payload: dict, *args, **kwargs)-> int:
        if not isinstance(payload, dict): raise AssertionError("Payload must be dict")
        if not 'title' in payload or not payload.get('title'): raise AssertionError("Invalid Work Order Title")
        if 'categories' in payload:
            if not isinstance(payload.get('categories'), list): raise AssertionError("Categories must be an array")
            for category in payload.get('categories'):
                if not category in MaintainxDefaultCategories.CATEGORIES_LIST: raise AssertionError("Unknown Category")
        try:
            response = self.API.create_work_order(payload)
        except Exception as e:
            logger.error(f"Failed Work Order Creation: {e}", exc_info=True)
            raise Exception(e)
        if 'id' in response:
            #handle attachments
            return response.get('id')
        else:
            return -1
        #when do we create a work order?
            #when a new bundle has been created and we need someone to add the image attachment.
            #refunded transaction
            #MapOutAsset
            #orphane_work_order
            #attach_images_work_oders

    def delete_work_order(self, maintainx_id: int)-> bool:
        response = self.API.delete_work_order(maintainx_id)
        if 'error' in response or 'errors' in response: return False
        else: return True
        #check status code

    def update_work_order(self, payload: dict, maintainx_id: int):
        return self.API.update_work_order_status(payload, maintainx_id)


class LaundryRoomMeterManager(MaintainxAssetManager):
    meter_field_name = 'maintainx_id'
    room_code_field = 'maintainx_id'

    @ProductionCheck
    def run(self):
        """
        creates metes in Maintainx for the first time
        """
        for room in LaundryRoom.objects.filter(is_active=True, maintainx_id__isnull=False):
            meter = getattr(room, 'meter', None)
            if not meter:
                try: meter = LaundryRoomMeter.objects.create(laundry_room=room)
                except Exception as e: logger.info("Failed creating local meter for room: {}. Exception: {}".format(room, e))
            meter.refresh_from_db()
            if getattr(meter, 'maintainx_id', None): continue
            payload = {'name' : room.display_name, 'location': getattr(room, self.room_code_field, None)}
            if payload['location']: payload['location'] = int(payload['location'])
            meter_payload = self.build_meter_payload(None, payload)
            meter_payload['name'] += ' (Dryers Starts)'
            try:
                meter_response = self.api.create_asset_meter(meter_payload)
            except Exception as e:
                logger.info("Failed upkeep meter creation for room: {}. Exception: {}".format(room, e))
                meter_response = None
            room.refresh_from_db()
            if meter_response and 'id' in meter_response:
                meter_obj = getattr(room, 'meter') #TODO: implement related_name
                setattr(meter_obj, self.meter_field_name, meter_response.get('id'))
                try: dryers_starts = room.get_dryer_starts_count()
                except: dryers_starts = 0
                meter.dryers_start_counter = dryers_starts
                meter_obj.save()
            else:
                logger.error('Failed Creating Meter for Room {}. Response" {}'.format(room,meter_response))