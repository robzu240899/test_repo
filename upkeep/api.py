import requests
import logging
import json
from datetime import datetime
from django.conf import settings

logger = logging.getLogger(__name__)

class UpkeepAPI():
    update_create_fields_map = {
            'name': 'display_name',
            'address': '',
            'longitude': '',
            'latitude': '',
            'hideMap': '',
    }

    def __init__(self, email=None, password=None,):
        if email is None:
            self.email = settings.UPKEEP_USER
        else:
            self.email = email
        if password is None:
            self.password = settings.UPKEEP_PASSWORD
        else:
            self.password = password
        self.token = None
        self.session = requests.Session()
        self._get_auth_token(3)
        self._set_requests_session()

    def _get_auth_token(self, retries=1):
        from .models import StoredUpkeepToken
        now = datetime.now()
        latest_token = StoredUpkeepToken.objects.last()
        if latest_token:
            diff = (now - latest_token.saved_at).total_seconds()
            if diff <= 86400:
                self.token = latest_token.session_token
                return
        url = 'https://api.onupkeep.com/api/v2/auth/'
        email = self.email
        password = self.password

        payload = {
            'email': email,
            'password': password
        }
        headers = {
            'Content-Type': "application/json",
            'Cache-Control': "no-cache"
        }
        response = requests.post(url, json=payload, headers=headers)
        if response.status_code >= 200 and response.status_code <= 299:
            self.token = json.loads(response.text)['result']['sessionToken']
            StoredUpkeepToken.objects.create(session_token=self.token)
        else:
            if retries == 0:
                exception_string = "Could not authenticate to Upkeep API: Error {}".format(
                    response.status_code)
                logger.error(exception_string)
                raise Exception(exception_string)
            else:
                self._get_auth_token(retries=retries-1)

    def _set_requests_session(self):
        common_headers = {
            'Cache-Control': "no-cache",
            "Session-Token": self.token
        }
        self.session.headers.update(common_headers)

    def _get_response(self, method, url, data=None, parameters=None, silent_fail=False, json_data=None):
        request = requests.Request(method, url, data=data, params=parameters, json=json_data)
        prepped_request = self.session.prepare_request(request)
        response = self.session.send(prepped_request)
        if response.status_code >= 200 and response.status_code <= 299:
            return json.loads(response.text)
        else:
            if silent_fail: return json.loads(response.text)
            exception_string = "Unable to retrieve data from {}. Error {} - {}".format(
                url, response.status_code, response.text)
            logger.error(exception_string)
            raise Exception(exception_string)

    def get_all_locations(self):
        url = 'https://api.onupkeep.com/api/v2/locations'
        response = self._get_response('GET', url)
        return response['results']

    def get_location(self, upkeep_code):
        url = 'https://api.onupkeep.com/api/v2/locations/{}'.format(upkeep_code)
        response = self._get_response('GET', url)
        return response['result']

    def update_location(self, location, **kwargs):
        url= 'https://api.onupkeep.com/api/v2/locations/{}'.format(location.upkeep_code)
        data = {}
        for key,value in kwargs.items():
            if key in self.update_create_fields_map.keys():
                data[key] = value
        response = self._get_response('PATCH', url, data)
        return response['result']

    def create_location(self, location):
        url = 'https://api.onupkeep.com/api/v2/locations/'
        data = {}
        for upkeep_field, local_field in self.update_create_fields_map.items():
            try:
                data[upkeep_field] = getattr(location, local_field)
            except AttributeError:
                continue
        response = self._get_response('POST', url, data)
        return response['result']

    def delete(self, obj_type, upkeep_id, *args, **kwargs):
        url = f"https://api.onupkeep.com/api/v2/{obj_type}/{upkeep_id}"
        response = self._get_response('DELETE', url, *args, **kwargs)
        return response

    def create_asset(self, payload):
        url = 'https://api.onupkeep.com/api/v2/assets/'
        response = self._get_response('POST', url, json_data=payload)
        return response['result']

    def get_asset(self, upkeep_code):
        url = 'https://api.onupkeep.com/api/v2/assets/{}'.format(upkeep_code)
        response = self._get_response('GET', url)
        return response['result']

    def update_asset(self, upkeep_code, payload):
        url = 'https://api.onupkeep.com/api/v2/assets/{}'.format(upkeep_code)
        response = self._get_response('PATCH', url, json_data=payload)
        return response['result']

    def get_all_assets(self, **kwargs):
        params_payload = kwargs if kwargs else None
        url = 'https://api.onupkeep.com/api/v2/assets'
        response = self._get_response('GET', url, parameters=params_payload)
        return response['results']

    def get_all_meters(self, **kwargs):
        params_payload = kwargs if kwargs else None
        url = 'https://api.onupkeep.com/api/v2/meters/'
        response = self._get_response('GET', url, parameters=params_payload)
        return response['results']

    def get_meter(self, meter_id):
        url = "https://api.onupkeep.com/api/v2/meters/{}".format(meter_id)
        response = self._get_response('GET', url)
        return response['result']

    def delete_meter(self, meter_id):
        url = "https://api.onupkeep.com/api/v2/meters/{}".format(meter_id)
        response = self._get_response('DELETE', url)
        return response

    def create_asset_meter(self, payload):
        url = 'https://api.onupkeep.com/api/v2/meters/'
        response = self._get_response('POST', url, payload)
        return response['result']

    def update_asset_meter(self, meter_upkeep_id, payload):
        url = 'https://api.onupkeep.com/api/v2/meters/{}'.format(meter_upkeep_id)
        response = self._get_response('PATCH', url, payload)
        return response['result']

    def update_asset_meter_reading(self, meter, field, *args, **kwargs):
        url = 'https://api.onupkeep.com/api/v2/meters/{}/readings'.format(meter.upkeep_id)
        response = self._get_response('POST', url, {'value':getattr(meter, field, None)}, *args, **kwargs)
        return response['result']

    def update_custom_field(self, asset_id, custom_field_id, payload):
        url = 'https://api.onupkeep.com/api/v2/assets/{}/custom-fields/{}'.format(asset_id, custom_field_id)
        response = self._get_response('PATCH', url, payload)
        return response['result']

    def create_work_order(self, payload):
        payload['title'] = '[*AUTO*]' + payload['title']
        url = 'https://api.onupkeep.com/api/v2/work-orders/'
        response = self._get_response('POST', url, payload)
        return response.get('result')

    def update_work_order(self, payload, work_order_upkeep_id):
        url = 'https://api.onupkeep.com/api/v2/work-orders/{}'.format(work_order_upkeep_id)
        response = self._get_response('PATCH', url, payload, silent_fail=True)
        #By using silent_fail we avoid raising an exception when a work order was deleted and a 404 erorr is retrieved
        return response['result']

    def get_work_orders(self, *args, record_upkeep_id=None, **kwargs):
        """
        kwargs are assumed to be extra parameters for the final URL
        """
        params_payload = kwargs if kwargs else None
        if record_upkeep_id:
            url = 'https://api.onupkeep.com/api/v2/work-orders/{}'.format(record_upkeep_id)
            kwarg_name = 'result'
        else:
            url = 'https://api.onupkeep.com/api/v2/work-orders'
            kwarg_name = 'results'
        response = self._get_response('GET', url, parameters=params_payload, silent_fail=True)
        if response['success']:
            return response.get(kwarg_name)
        else:
            if response['message'] in ['work order not found', 'work orders not found']:
                return None
            raise Exception(f"Failed fetching work orders data via Upkeep API: {response}")

    def get_users(self):
        url = 'https://api.onupkeep.com/api/v2/users/'
        response = self._get_response('GET', url)
        return response['results']