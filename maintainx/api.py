import boto3
import json
import logging
import requests
from django.conf import settings
from .exceptions import MaintainxTooManyRequests

logger = logging.getLogger(__name__)

class MaintainxAPI():
    update_create_fields_map = {
            'name': 'display_name',
            'description' : '',
            'address': '',
            'parentId' : '',
            'address' : '',
            'extraFields' : ''
    }

    def __init__(self, email=None, password=None,):
        self.api_key = settings.MAINTAINX_API_KEY
        self.session = requests.Session()
        self._set_requests_session()

    def _set_requests_session(self):
        common_headers = {
            'Cache-Control': "no-cache",
            'Content-Type': "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }
        self.session.headers.update(common_headers)
    
    def _get_response(self, method, url, data=None, parameters=None, silent_fail=False, json_data=None, files=None):
        request = requests.Request(method, url, data=data, params=parameters, json=json_data, files=files)
        prepped_request = self.session.prepare_request(request)
        response = self.session.send(prepped_request)
        if response.status_code >= 200 and response.status_code <= 299:
            if response.text: return json.loads(response.text)
            else: return {}
        else:
            if silent_fail:
                try:
                    return json.loads(response.text)
                except Exception as e:
                    logger.error(f"Failed request. Response code: {response.status_code}", exc_info=True)
            exception_string = "Unable to retrieve data from {}. Error {} - {}".format(
                url, response.status_code, response.text)
            logger.error(exception_string)
            if response.status_code == 429: raise MaintainxTooManyRequests(exception_string)
            raise Exception(exception_string)

    def get_all_locations(self):
        url = 'https://api.getmaintainx.com/v1/locations'
        response = self._get_response('GET', url)
        return response['locations']

    def get_location(self, maintainx_id):
        url = 'https://api.getmaintainx.com/v1/locations/{}'.format(maintainx_id)
        response = self._get_response('GET', url)
        return response['location']

    def create_location(self, location):
        url = 'https://api.getmaintainx.com/v1/locations/'
        data = {}
        for maintainx_field, local_field in self.update_create_fields_map.items():
            try:
                data[maintainx_field] = getattr(location, local_field)
            except AttributeError:
                continue
        response = self._get_response('POST', url, json_data=data)
        return response

    def update_location(self, location, **kwargs):
        url= 'https://api.getmaintainx.com/v1/locations/{}'.format(location.maintainx_id)
        data = {}
        for key,value in kwargs.items():
            if key in self.update_create_fields_map.keys():
                data[key] = value
        response = self._get_response('PATCH', url, json_data=data)
        return response['location']

    def delete_location(self, location):
        url= 'https://api.getmaintainx.com/v1/locations/{}'.format(location.maintainx_id)
        response = self._get_response('DELETE', url)
        return response

    def delete_location_by_id(self, location_id):
        url= 'https://api.getmaintainx.com/v1/locations/{}'.format(location_id)
        response = self._get_response('DELETE', url)
        return response

    def create_asset(self, payload):
        url = 'https://api.getmaintainx.com/v1/assets'
        response = self._get_response('POST', url, json_data=payload)
        return response

    def get_asset(self, maintainx_id):
        url = 'https://api.getmaintainx.com/v1/assets/{}'.format(maintainx_id)
        response = self._get_response('GET', url)
        return response['asset']

    def update_asset(self, maintainx_id, payload):
        url = 'https://api.getmaintainx.com/v1/assets/{}'.format(maintainx_id)
        response = self._get_response('PATCH', url, json_data=payload)
        return response['asset']

    def update_asset_attachment(self, asset_id, binary_content, filename):
        url = f'https://api.getmaintainx.com/v1/assets/{asset_id}/attachments/{filename}'
        #response = self._get_response('PUT', url, files={'file': binary_file})
        session = requests.Session()
        common_headers = {
            'Cache-Control': "no-cache",
            'Content-Type': "application/octet-stream",
            "Authorization": f"Bearer {self.api_key}"
        }
        session.headers.update(common_headers)
        request = requests.Request('PUT', url, data=binary_content)
        prepped_request = session.prepare_request(request)
        response = session.send(prepped_request)
        if response.status_code >= 200 and response.status_code <= 299:
            if response.text: return json.loads(response.text)
            else: return {}
        else:
            exception_string = "Unable to retrieve data from {}. Error {} - {}".format(
                url, response.status_code, response.text)
            logger.error(exception_string)
            raise Exception(exception_string)


    def delete_asset(self, maintainx_id):
        url = 'https://api.getmaintainx.com/v1/assets/{}'.format(maintainx_id)
        response = self._get_response('DELETE', url)
        return response

    def get_all_assets(self, **kwargs):
        params_payload = kwargs if kwargs else None
        url = 'https://api.getmaintainx.com/v1/assets'
        response = self._get_response('GET', url, parameters=params_payload)
        return response['assets']
    
    def get_all_meters(self, **kwargs):
        params_payload = kwargs if kwargs else None
        url = 'https://api.getmaintainx.com/v1/meters'
        response = self._get_response('GET', url, parameters=params_payload)
        return response['meters']

    def create_asset_meter(self, payload):
        url = 'https://api.getmaintainx.com/v1/meters'
        response = self._get_response('POST', url, json_data=payload)
        return response

    def get_meter(self, maintainx_meter_id):
        url = 'https://api.getmaintainx.com/v1/meters/{}'.format(maintainx_meter_id)
        response = self._get_response('GET', url)
        return response['meter']

    def delete_meter(self, maintainx_meter_id):
        url = 'https://api.getmaintainx.com/v1/meters/{}'.format(maintainx_meter_id)
        response = self._get_response('DELETE', url)
        return response
    
    def update_asset_meter(self, maintainx_meter_id, payload):
        url = 'https://api.getmaintainx.com/v1/meters/{}'.format(maintainx_meter_id)
        response = self._get_response('PATCH', url, json_data=payload)
        return response

    def update_asset_meter_reading(self, meter, field, *args, **kwargs):
        """
        maintainx requires us to create a new meter reading, while upkeep allow us to update the meter reading
        """
        if not meter.maintainx_id: return
        url = 'https://api.getmaintainx.com/v1/meters/{}/readings'.format(meter.maintainx_id)
        response = self._get_response(
            'POST', url, *args, json_data={'readingValue':getattr(meter, field, None)}, **kwargs
        )
        return response

    def update_asset_meter_reading_batch(self, array_payload, *args, **kwargs):
        """
        maintainx requires us to create a new meter reading, while upkeep allow us to update the meter reading
        """
        url = 'https://api.getmaintainx.com/v1/meterreadings'
        response = self._get_response('POST', url, *args, json_data=array_payload, **kwargs)
        return response

    def update_custom_field(self, asset_id, payload):
        """
        payload must be of the form {'property_name' : property_value}
        """
        assert isinstance(payload, dict)
        final_payload = {'extraFields' : payload}
        url = 'https://api.getmaintainx.com/v1/assets/{}'.format(asset_id)
        response = self._get_response('PATCH', url, json_data=final_payload)
        return response['asset']

    def create_work_order(self, payload, auto=True):
        if auto: payload['title'] = '[*AUTO*]' + payload['title']
        url = 'https://api.getmaintainx.com/v1/workorders'
        response = self._get_response('POST', url, json_data=payload)
        return response

    def update_work_order_status(self, payload, work_order_maintainx_id):
        url = "https://api.getmaintainx.com/v1/workorders/{}/status".format(work_order_maintainx_id)
        response = self._get_response('PATCH', url, json_data=payload, silent_fail=False)
        return response

    def update_work_order(self, payload, work_order_maintainx_id):
        if 'status' in payload:
            status = payload.pop('status')
            r = self.update_work_order_status({'status':status}, work_order_maintainx_id)
        if not payload: return
        url = 'https://api.getmaintainx.com/v1/workorders/{}'.format(work_order_maintainx_id)
        response = self._get_response('PATCH', url, json_data=payload, silent_fail=False)
        return response['workOrder']

    def update_work_order_attachment(self, work_order_maintainx_id, binary_file, filename):
        url = f'https://api.getmaintainx.com/v1/workorders/{work_order_maintainx_id}/attachments/{filename}'
        #response = self._get_response('PUT', url, files={'file': binary_file})
        session = requests.Session()
        common_headers = {
            'Cache-Control': "no-cache",
            'Content-Type': "application/octet-stream",
            "Authorization": f"Bearer {self.api_key}"
        }
        session.headers.update(common_headers)
        request = requests.Request('PUT', url, files={'file': binary_file})
        prepped_request = session.prepare_request(request)
        response = session.send(prepped_request)
        print (f"got response: {response}")
        if response.status_code >= 200 and response.status_code <= 299:
            if response.text: return json.loads(response.text)
            else: return {}
        else:
            exception_string = "Unable to retrieve data from {}. Error {} - {}".format(
                url, response.status_code, response.text)
            logger.error(exception_string)
            raise Exception(exception_string)

    def delete_work_order(self, maintainx_id: int):
        url = 'https://api.getmaintainx.com/v1/workorders/{}'.format(maintainx_id)
        response = self._get_response('DELETE', url)
        return response


    def _build_work_orders_url(self, params: dict, expand_on: list):
        url_str = ''
        all_params = []
        if params: all_params.extend([f'{param_name}={param_val}' for param_name, param_val in params.items()])
        if expand_on: all_params.extend([f'expand={expand_field}' for expand_field in expand_on])
        url_str += '&'.join(all_params)
        return url_str

    def get_work_orders(self, *args, record_maintainx_id=None, params: dict={}, expand_on: list=[]):
        """
        kwargs are assumed to be extra parameters for the final URL
        """
        if record_maintainx_id:
            kwarg_name = 'workOrder'
            url = 'https://api.getmaintainx.com/v1/workorders/{}'.format(record_maintainx_id)
        else:
            url_params_str = self._build_work_orders_url(params, expand_on)
            if url_params_str: url_params_str = '?' + url_params_str
            kwarg_name = 'workOrders'
            url = 'https://api.getmaintainx.com/v1/workorders'
            url = url + url_params_str
        response = self._get_response('GET', url, silent_fail=True)
        return response

    def get_parts(self):
        url = f"https://api.getmaintainx.com/v1/parts"
        response = self._get_response('GET', url)
        return response['parts']


    def get_user(self, user_id=''):
        url = f"https://api.getmaintainx.com/v1/users/{user_id}"
        response = self._get_response('GET', url)
        if not user_id: return response['users']
        else: return response['user']

        # if response['success']:
        #     return response.get(kwarg_name)
        # else:
        #     if response['message'] in ['work order not found', 'work orders not found']:
        #         return None
        #     raise Exception("Failed fetching work orders data via Maintainx API")