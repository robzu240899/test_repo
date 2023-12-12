'''
Created on Apr 13, 2014

@author: Tom
'''
import logging
from datetime import datetime, timedelta
from collections import namedtuple
from copy import deepcopy
from pytz import timezone,utc
from fascard.config import FascardPricingConfig
from .betterbrowser import BetterBrowser, WrongEndPointError  #NB: Wrong Endpoint error is used by other imports.  should be fixed
from .instructions import FormInstruction
from .config import FascardLoginConfig,FascardScrapeConfig,FascardReportConfig
from .utils import TimeHelper

logger = logging.getLogger(__name__)

class FascardBrowser(BetterBrowser):

    def set_login_ins(self,bldg_group_id):
        credentials = self.__get_fascar_credentials(bldg_group_id)
        self.url_number = credentials['url_number']
        self.login_ins = FormInstruction(FascardLoginConfig.FORM_NUM,
                           FascardLoginConfig.FIELDS,
                           credentials,
                           FascardLoginConfig.EXPECTED_POSTLOGIN_URL % self.url_number)
        self.login_url = FascardLoginConfig.LOGIN_URL

    #Find all the building links and store them in the building_linkds field
    def set_building_links(self):
        self.building_links = []
        try:
            self.open(FascardScrapeConfig.BUILDING_LIST_URL)
        except WrongEndPointError:
            self.login()
            self.open(FascardScrapeConfig.BUILDING_LIST_URL)
        tree = self.get_tree()
        building_containers = []
        for building_xpath in FascardScrapeConfig.BUILD_SPECIFIC_URL_XPATHS:
            building_containers += tree.findall(building_xpath)
        for bc in building_containers:
            relative_link = bc.get(FascardScrapeConfig.BUILD_SPECIFIC_URL_ATTR)
            relative_link = relative_link.split("'")[1]
            abs_link = FascardScrapeConfig.DOMAIN+relative_link
            self.building_links.append(abs_link)

    def get_slots(self,room_id,room_fascard_code):
        Slot = namedtuple("BrowserSlot", ["laundry_room_id","slot_fascard_id","slot_link", "slot_display_name", "machine_txt","last_start_time"], verbose=False, rename=False)
        slots = []
        slot_containers = []
        self.open(FascardScrapeConfig.create_laundry_room_url(room_fascard_code))
        tree = self.get_tree()
        for xpath in FascardScrapeConfig.SLOT_SPECIFIC_XPATHS:
            slot_containers += tree.findall(xpath)
        for sc in slot_containers:
            slot_link = sc.get(FascardScrapeConfig.SLOT_URL_ATTR)  #TODO: figure out if this needs to change
            slot_link = slot_link.split("'")[1]
            slot_link = FascardScrapeConfig.DOMAIN+slot_link
            machine_txt = sc.find(FascardScrapeConfig.MACHINE_TYPE_XPATH).text.strip().lower()
            last_start_time = sc.find(FascardScrapeConfig.LAST_START_XPATH).text.strip()
            try:
                display_num = sc.find(FascardScrapeConfig.DISPLAY_NUM_XPATH).text.strip()
                if not display_num:
                    raise Exception("")
            except Exception as e:
                display_num = sc.find(FascardScrapeConfig.DISPLAY_NUM_XPATH+'/a').text.strip()
            slot_fascard_id = slot_link.split(FascardScrapeConfig.SLOT_ID_SPLIT)[1].split("&")[0]
            slots.append(Slot(room_id,slot_fascard_id,slot_link,display_num,machine_txt,last_start_time))

        return slots

    def download_report(self,report_name,export_to_file_name,start_date=None,end_date=None):
        url=FascardReportConfig.EXPORT_URL % self.url_number

        self.login()
        self.open(url)

        self.Br.select_form(nr=FascardReportConfig.EXPORT_FORM_NUM)

        # Set date range
        if start_date:
            start_date = self.date_to_fascar_string(start_date)
            self.Br.form[FascardReportConfig.EXPORT_FORM_START_DATE_FIELD_NAME] = start_date
        if end_date:
            end_date = self.date_to_fascar_string(end_date)
            self.Br.form[FascardReportConfig.EXPORT_FORM_END_DATE_FIELD_NAME] = end_date

        # report ID
        report_id = FascardReportConfig.REPORT_IDS[report_name]
        report_drop_down = self.Br.form.find_control(FascardReportConfig.EXPORT_FORM_SELECTOR)
        self.Br[report_drop_down.name] = [report_id]

        valid_report_type = report_id in set(item.name for item in report_drop_down.items)
        if not valid_report_type:
            exception_string = "Could not select report to download from fascard site."
            logger.error(exception_string)
            raise Exception (exception_string)

        tz_dropdown = self.Br.form.find_control(FascardReportConfig.TZ_FORM_SELECTOR)

        # check if UTC code is in set of item names
        valid_tz = FascardReportConfig.REPORT_TIME_ZONE[0] in set(item.name for item in tz_dropdown.items)

        if not valid_tz:
            exception_string = "Could not select report to download from fascard site."
            logger.error(exception_string)
            raise Exception (exception_string)

        self.Br[tz_dropdown.name] = [FascardReportConfig.REPORT_TIME_ZONE[0]]

        response = self.Br.submit()
        with open(export_to_file_name,'wb') as f:
            f.write(response.read())


    def __get_fascar_credentials(self,bldg_group_id):
        cred = FascardLoginConfig.CREDENTIALS[str(bldg_group_id).lower().strip()]
        return {'usr' : cred[0], 'pw' : cred[1], 'url_number' : cred[2]}

    @classmethod
    def date_to_fascar_string(cls,dt):
        month = str(dt.month)
        day = str(dt.day)
        year = dt.year
        if len(month) == 1:
            month = '0%s'%month
        if len(day) == 1:
            day = '0%s'%day
        return '%s/%s/%s' % (month,day,year)


    def get_states(self,slot):
        state_containers = []
        state_list = []
        SlotState = namedtuple("SlotState", ["start_time","end_time","duration",
                                             "recorded_time","local_recorded_time","slot_status",
                                             "local_start_time","local_end_time",
                                             "slot_id"], verbose=False, rename=False)
        record_time = datetime.utcnow()
        local_record_time = TimeHelper.convert_to_local(record_time,slot.laundry_room.time_zone)

        self.open(FascardScrapeConfig.create_url(slot)) #NB: create_url is for a slot, just poorly named
        tree = self.get_tree()
        for xpath in FascardScrapeConfig.SLOT_STATE_XPATHS:
            state_containers += tree.findall(xpath)
        for sc in state_containers:
            item_number = sc.find(FascardScrapeConfig.SLOT_STATE_NUM_XPATH).text.strip().lower()
            slot_status = sc.find(FascardScrapeConfig.SLOT_STATE_STATUS_XPATH).text.strip()

            start_time = TimeHelper.format_time(sc.find(FascardScrapeConfig.SLOT_STATE_START_TIME_XPATH)
                                                   .text.strip().lower())
            local_start_time = TimeHelper.convert_to_local(deepcopy(start_time),slot.laundry_room.time_zone)
            duration = sc.find(FascardScrapeConfig.SLOT_STATE_DURATION_XPATH).text.strip().lower()
            if item_number == '1':
                duration = None
                end_time = None
            else:
                duration = TimeHelper.duration_in_seconds(duration)
                end_time = start_time + timedelta(seconds=duration)
            local_end_time = TimeHelper.convert_to_local(deepcopy(end_time),slot.laundry_room.time_zone)
            s = SlotState(
                              start_time=start_time, end_time=end_time,
                              duration = duration, recorded_time = record_time,
                              local_recorded_time = local_record_time,
                              slot_status=slot_status,
                              local_start_time=local_start_time,
                              local_end_time=local_end_time,
                              slot_id=slot.id)
            state_list.append(s)
        return state_list

    def scrape_pricing(self,fascard_room_code):
        Price = namedtuple('Price', ['machine_type','product'])
        #Open the initial page
        url=FascardPricingConfig.REPORT_URL % self.url_number
        self.login()
        self.open(url)

        #Select the report type dropdown
        self.Br.form = list(self.Br.forms())[FascardPricingConfig.FORM_NUMBER]
        report_drop_down = self.Br.form.find_control(FascardPricingConfig.DROPDOWN_FORM_ID)
        #Select Pricing History report from the dropdown
        self.Br[report_drop_down.name] = [FascardPricingConfig.PRICING_REPORT_DROWPDOWN_VALUE]

        #Select the laundry room
        room_selector =  self.Br.form.find_control(FascardPricingConfig.DROPDOWN_FORM_ID)
        found_room = False
        for selector in room_selector.items:
            if selector.name == str(fascard_room_code):
                selector.selected=True
                found_room = True
                break
            else:
                pass
        if not found_room:
            exception_string = "Could not select report to download from fascard site."
            logger.error(exception_string)
            raise Exception (exception_string)

        #Submit the form

        response = self.Br.submit()

        #parse the data
        prices = []
        #TODO: start here
