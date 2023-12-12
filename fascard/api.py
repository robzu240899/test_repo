import logging
import requests
from main import settings
import json
from datetime import datetime


logger = logging.getLogger(__name__)

class FascardApi(object):

    def __init__(self, laundry_group_id=None, username=None, password=None,):
        logger.info("initializing fascard api client")
        if username is None:
            # self.username = settings.FASCARD_CREDENTIALS[str(
            #     laundry_group_id)][0]
            self.username = settings.FASCARD_USERNAME
        else:
            self.username = username
        if password is None:
            # self.password = settings.FASCARD_CREDENTIALS[str(
            #     laundry_group_id)][1]
            self.password = settings.FASCARD_PASSWORD
        else:
            self.password = password
        self.token = None
        self._get_auth_token()

    def _get_auth_token(self, retries=1):
        from reporting.models import StoredFascardToken
        url = "https://m.fascard.com/api/AuthToken"
        username = self.username
        password = self.password

        payload = "{\n\t\"UserName\": \"%s\",\n\t\"Password\": \"%s\"\n}" % (
            username, password)
        headers = {
            'Content-Type': "application/json",
            'Cache-Control': "no-cache"
        }
        logger.info("Getting auth token")
        response = requests.request("POST", url, data=payload, headers=headers)
        logger.info("got a response for auth token request")

        request_new_token = False
        stored_token = StoredFascardToken.objects.order_by('saved_at').last()
        if stored_token:
            token_age = (datetime.now() - stored_token.saved_at).seconds
            if token_age >= 1600: request_new_token = True                
            else: self.token = stored_token.session_token
        else:
            request_new_token = True
        
        if request_new_token:
            if response.status_code >= 200 and response.status_code <= 299:
                logger.info("got a SUCCESSFUL response for auth token request")
                self.token = json.loads(response.text)['Token']
                StoredFascardToken.objects.create(session_token = self.token)
            else:
                logger.info("got a BAD response for auth token request")
                if retries == 0:
                    exception_string = "Could not authenticate to Fascard Mobile API"
                    logger.error(exception_string)
                    print (json.loads(response.text))
                    raise Exception(exception_string)
                else:
                    self._get_auth_token(retries=retries-1)

    def _get_response(self, url, parameters=None, method=None, silent_fail=False):  # TODO: add in retries
        logger.info(f"Trying to get response for url: {url}")
        headers = {
                'Cache-Control': 'no-cache',
                "Authorization": 'Bearer %s' % self.token
        }
        if method == 'POST':
            headers['Content-Type'] = 'application/json'
            logger.info("Getting POST request")
            response = requests.request("POST", url, headers=headers, json=parameters)
            logger.info("GOT post request")
        else:
            logger.info("Getting GET request")
            response = requests.request("GET", url, headers=headers, params=parameters)
            logger.info("GOT GET request")
        if response.status_code >= 200 and response.status_code <= 299:
            return json.loads(response.text)
        else:
            logger.info(f"BAD response for url {url}")
            if "not found" in response.text: return
            exception_string = 'Fascard API was unable to retrieve data from: {}. Response: {}'
            exception_string = exception_string.format(url, response.text)
            logger.error(exception_string, exc_info=True)
            if silent_fail: return json.loads(response.text)
            else: raise Exception(exception_string)

    def get_machines(self, fascard_location_id=None, fascard_machine_id=None):
        url = "https://m.fascard.com/api/Machine"
        if fascard_location_id is not None and fascard_machine_id is not None:
            raise Exception(
                "Only one of fascard_location_id and fascard_machine_id must be supplied.")
        elif fascard_location_id is not None:
            parameters = {"LocationID": fascard_location_id}
        elif fascard_machine_id is not None:
            parameters = {"MachineID": fascard_machine_id}
        else:
            raise Exception(
                "fascard_location_id and fascard_machine_id are both null.  Exactly one must be supplied")
        return self._get_response(url, parameters)

    def get_machine(self, slot_id):
        assert slot_id is not None
        url = 'https://m.fascard.com/api/Machine?MachineID={}'.format(slot_id)
        return self._get_response(url)[0]

    def get_machine_history(self, machine_fascard_id=None, limit=0):
        if machine_fascard_id is not None:
            url = "https://m.fascard.com/api/Machine/{}/History".format(machine_fascard_id)
            return self._get_response(url)
        else:
            raise Exception('Machine fascard id is required')

    def get_equipment(self, fascard_location_id=None):
        url = "https://m.fascard.com/api/Equip"
        if fascard_location_id is not None:
            parameters = {"LocationID": fascard_location_id}
        else:
            parameters = {}
        return self._get_response(url, parameters)

    def get_pricing(self, fascard_location_id):
        url = "https://m.fascard.com/api/Equip?"
        parameters = {"LocationID": fascard_location_id}
        return self._get_response(url, parameters)

    def get_user_account(self, user_account_id=None):
        if user_account_id is not None:
            aces_id = settings.FASCARD_ACES_ID
            url = 'https://m.fascard.com/api/UserAccount/{}/{}/'.format(aces_id, user_account_id)
            return self._get_response(url)
        else:
            raise Exception('User account id is required')

    def get_slots_by_room(self, laundry_room_code=None):
        assert laundry_room_code is not None
        url = "https://m.fascard.com/api/Machine?LocationID={}".format(laundry_room_code)
        try:
            return self._get_response(url)
        except:
            return []
        

        #we are going to make some spaces here while we work, now, first of all we need to add the last activity parameter @robzu.99, logic here so far is dor me to make the 
        #parameter of datetime from now until one day prior which is the last time we did the update which was effectively running nightly run

    def get_user_account_list(self, limit, prev, lastid, last_activity_date=None):
        """
        @last_activity_date must be ISO format.
        """
        url = 'https://m.fascard.com/api/UserAccount/{}?limit={}&prev={}&lastID={}'
        if last_activity_date: url = url + f'&lastActivity={last_activity_date}'
        return self._get_response(url.format(
            settings.FASCARD_ACES_ID,
            limit,
            prev,
            lastid
        ))

    def get_transactions_list(self, lastID, user_account_id=0, limit=1000, Older=False):
        assert lastID
        url = 'https://m.fascard.com/api/Transact?AccountID={}&UserAccountID={}&Limit={}&lastID={}&Older={}'
        return self._get_response(url.format(
            settings.FASCARD_ACES_ID,
            user_account_id,
            limit,
            lastID,
            Older
        ))

    def get_datamatrix_info(self, hex_code):
        assert hex_code is not None
        url = "https://m.fascard.com/api/Start/"

        payload = {
            'Type': 2,
            'Code': hex_code
        }
        #response = requests.request("POST", url, data=payload, headers=headers)
        return self._get_response(url, payload, "POST")

    def refund_loyalty_account(self, fascard_user_id, payload):
        url = 'https://m.fascard.com/api/UserAccount/86/{}'.format(fascard_user_id)
        return self._get_response(url, payload, "POST")

    def get_loyalty_account(self, card_number):
        url = 'https://m.fascard.com/api/UserAccount/86?cardno={}'.format(card_number)
        try:
            return self._get_response(url)[0]
        except:
            return {}
        
    def update_slot_label(self, slot_id, new_label):
        logger.info(f"Updating slot label in fascard for slot {slot_id}, new label: {new_label}", exc_info=True)
        url = 'https://m.fascard.com/api/Machine/{}/'.format(slot_id)
        payload = {"Label": new_label}
        return self._get_response(url, payload, "POST")

    def edit_machine(self, slot_id, payload):
        logger.info(f"Editing slot label in fascard for slot {slot_id}: {payload}", exc_info=True)
        url = 'https://m.fascard.com/api/Machine/{}/'.format(slot_id)
        return self._get_response(url, payload, "POST")

    def get_room(self, location_id, silent_fail=True):
        url = 'https://m.fascard.com/api/Location/{}/'.format(location_id)
        response = self._get_response(url, silent_fail=silent_fail)
        if 'ErrorCode' in response: return response
        else: return response[0]

    def get_satellite(self, location_id):
        url = 'https://m.fascard.com/api/Satellite?LocationID={}'.format(location_id)
        response = self._get_response(url)
        if response: return response[0]


class OOOReportAPI(FascardApi):
    def _get_response(self, url, parameters=None):  # TODO: add in retries
        headers = {
            'Cache-Control': "no-cache",
            "Authorization": "Bearer %s" % self.token
        }
        response = requests.request(
            "GET", url, headers=headers, params=parameters)
        if response.status_code >= 200 and response.status_code <= 299:
            data_response = json.loads(response.text)
        else:
            exception_string = 'Fascard API was unable to retrieve data from: %s' % url
            logger.error(exception_string)
            data_response = None
        return {'status_code': response.status_code, 'response': data_response}


class PricingHistoryAPI(FascardApi):
    locations_list_url = 'https://m.fascard.com/api/Location'
    equipment_url = 'https://m.fascard.com/api/Equip'
    equipment_pricing = 'https://m.fascard.com/api/Equip/{}/Schedule/{}'

    def __init__(self, laundry_group_id=None, username=None, password=None):
        if laundry_group_id is None:
            laundry_group_id = 1 #Defaulting to LG 1
        if username is None:
            # self.username = settings.FASCARD_CREDENTIALS[str(
            #     laundry_group_id)][0]
            self.username = settings.FASCARD_USERNAME
        else:
            self.username = username
        if password is None:
            # self.password = settings.FASCARD_CREDENTIALS[str(
            #     laundry_group_id)][1]
            self.password = settings.FASCARD_PASSWORD
        else:
            self.password = password
        self.token = None
        self.session = requests.Session()
        self._get_auth_token()
        self._set_requests_session()

    def _get_auth_token(self, retries=1):
        url = 'https://m.fascard.com/api/AuthToken'
        username = self.username
        password = self.password

        payload = {
            'UserName': username,
            'Password': password
        }
        headers = {
            'Content-Type': "application/json",
            'Cache-Control': "no-cache"
        }
        response = requests.post(url, json=payload, headers=headers)
        if response.status_code >= 200 and response.status_code <= 299:
            self.token = json.loads(response.text)['Token']
        else:
            if retries == 0:
                exception_string = "Could not authenticate to Fascard Mobile API: Error {}".format(
                    response.status_code)
                logger.error(exception_string)
                raise Exception(exception_string)
            else:
                self._get_auth_token(retries=retries-1)

    def _set_requests_session(self):
        common_headers = {
            'Cache-Control': "no-cache",
            "Authorization": "Bearer {}".format(self.token)
        }
        self.session.headers.update(common_headers)

    def _get_response(self, method, url, parameters):
        request = requests.Request(method, url, params=parameters)
        prepped_request = self.session.prepare_request(request)
        response = self.session.send(prepped_request)
        if response.status_code >= 200 and response.status_code <= 299:
            return json.loads(response.text)
        else:
            exception_string = "Unable to retrieve data from {}. Error {}".format(
                url, response.status_code)
            logger.error(exception_string)
            raise Exception(exception_string)
            #return None

    def get_available_locations(self):
        method = 'GET'
        parameters = {}
        all_locations = self._get_response(method, self.locations_list_url, parameters)
        #Filtering out rooms that do not belong to our account (Fascard bug)
        locations = [location for location in all_locations if int(location['AccountID'])==86]
        return locations

    def get_equipment_types(self, fascard_location_id=None):
        method = 'GET'
        if fascard_location_id is not None:
            parameters = {'LocationID': fascard_location_id}
        else:
            parameters = {}
        return self._get_response(method, self.equipment_url, parameters)

    def get_equipment_pricing(self, equipment_id=None, location_id=None):
        method = 'GET'
        parameters = {}
        if equipment_id is not None and location_id is not None:
            request_url = self.equipment_pricing.format(
                equipment_id, location_id)
            return self._get_response(method, request_url, parameters)
        else:
            raise Exception('Both equipment and location id are required')