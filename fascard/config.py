'''
Created on Mar 5, 2017

@author: Thomas
'''
from uuid import uuid4
import os

from main import settings
from main.settings import TEMP_DIR

class FascardLoginConfig():
    FORM_NUM = 0
    FIELDS = {'usr':'UserName','pw':'Password'}
    LOGIN_URL = 'https://admin.fascard.com/'
    EXPECTED_POSTLOGIN_URL = 'https://admin.fascard.com/%s/AccountSettings'
    CREDENTIALS = settings.FASCARD_CREDENTIALS

class FascardScrapeConfig():
    DOMAIN = 'https://admin.fascard.com'
    BUILDING_LIST_URL = 'https://admin.fascard.com/sysmaintls?page=0&sort=&dir=ASC'
    BUILD_SPECIFIC_URL_XPATHS = ['.//table[@class="pretty-table"][1]//tr[@class="listRowOdd"]',
                                 './/table[@class="pretty-table"][1]//tr[@class="listRowEven"]',
                                 './/table[@class="pretty-table"][1]//tr[@class="listRowAlertEven"]',
                                 './/table[@class="pretty-table"][1]//tr[@class="listRowAlertOdd"]']
    BUILD_SPECIFIC_URL_ATTR = 'onclick'

    SLOT_SPECIFIC_XPATHS = ['.//table[@class="pretty-table"][3]//tr[@class="listRowOdd"]',
                                 './/table[@class="pretty-table"][3]//tr[@class="listRowEven"]',
                                 './/table[@class="pretty-table"][3]//tr[@class="listRowAlertEven"]',
                                 './/table[@class="pretty-table"][3]//tr[@class="listRowAlertOdd"]'
                                 ]
    MACHINE_TYPE_XPATH = './/td[@class="listItem"][2]'
    SLOT_URL_ATTR = 'onclick'
    MACHINE_LOC_SPLIT = 'locationID='
    SLOT_ID_SPLIT = 'machid='
    DISPLAY_NUM_XPATH = './/td[@class="listItem"][1]'
    LAST_START_XPATH = './/td[@class="listItem"][4]'



    SLOT_STATE_XPATHS = ['.//table[@class="pretty-table"]//tr[@class="listRowOdd"]',
                                 './/table[@class="pretty-table"]//tr[@class="listRowEven"]',
                                 './/table[@class="pretty-table"]//tr[@class="listRowAlertEven"]',
                                 './/table[@class="pretty-table"]//tr[@class="listRowAlertOdd"]']
    SLOT_STATE_NUM_XPATH = './/td[@class="listItem"][1]'
    SLOT_STATE_STATUS_XPATH = './/td[@class="listItem"][2]'
    SLOT_STATE_START_TIME_XPATH = './/td[@class="listItem"][3]'
    SLOT_STATE_DURATION_XPATH = './/td[@class="listItem"][4]'
    TIME_INPUT_FORMAT = '%m/%d/%Y %I:%M:%S %p'


    @classmethod
    def create_laundry_room_url(cls,fascard_code):
        return 'https://admin.fascard.com/sysmaintls?locid=%s&page=1&TZOffset=0' % fascard_code

    @classmethod
    def create_url(cls,slot):
        return 'https://admin.fascard.com/MachineHist?locationID=%s&machid=%s&TZOffset=0' % (slot.laundry_room.fascard_code,slot.slot_fascard_id)


class FascardReportConfig():
    EXPORT_URL = 'https://admin.fascard.com/%s/export'
    EXPORT_FORM_NUM = 0
    EXPORT_FORM_START_DATE_FIELD_NAME = 'txtStartDate'
    EXPORT_FORM_END_DATE_FIELD_NAME = 'txtEndDate'
    EXPORT_FORM_SELECTOR = 'cboExportID'

    REPORT_IDS = {"laundry transaction":"1",
                  "users":"4"}

    TZ_FORM_SELECTOR = 'sTimeZone'
    REPORT_TIME_ZONE = ("UTC",'UTC')
    CONVERT_TO_TIME_ZONE = 'America/New_York'

    EXPORT_FILE_NAME_BASE = os.path.join(os.path.dirname(os.path.realpath(__file__)),'downloaded_report_%s.csv')

    FASCARD_USER_FIELD_MAP ={ 'Name':'name',
                         'Addr1':'addr_1',
                         'Addr2':'addr_2',
                         'City':'city',
                         'State':'state',
                         "Zip":'zip',
                         "MobilePhone":'mobile_phone',
                         "OfficePhone":"office_phone",
                         "EmailAddress":"email_address",
                         "Comments":"comments",
                         "Language":'language',
                         "NotifyCycleComplete":"notify_cycle_complete",
                         "CreationDate":"fascard_creation_date",
                         "LastActivityDate":"fascard_last_activity_date",
                         "Balance":"balance",
                         "Bonus":"bonus",
                         "Discount":"discount",
                         "FreeStarts":"free_starts",
                         "Status":"status",
                         "Employee":"is_employee",
                         "LoyaltyPoints":"loyalty_points",
                         "BalanceSpent":"ballance_spent",
                         "BonusSpent":"bonus_spent",
                         "FreeStartsSpent":"free_starts_spent",
                         "ReloadMethod":"reload_method",
                         "ReloadBalance":"reload_balance",
                         "ReloadBonus":"reload_bonus",
                         "CashSpent":"cash_spent",
                         "CreditCardSpent":"credit_card_spent",
                         "UserGroupID":"user_group_id",
                         "LastLocationID":"last_location_id",
                         "UserID":"xxx_caution_fascard_user_id",
                         "UserAccountID":"fascard_user_account_id",
                         "Coupons":"coupons"
                        }

    FASCARD_API_USER_FIELD_MAP = {
        'ID': 'fascard_user_account_id',
        'UserID': 'xxx_caution_fascard_user_id',
        'EmailAddress': 'email_address',
        'Name': 'name',
        'Addr1': 'addr_1',
        'Addr2': 'addr_2',
        'City': 'city',
        'State': 'state',
        'ZipCode': 'zip',
        'MobilePhone': 'mobile_phone',
        'Language': 'language',
        'Employee': 'is_employee',
        'Balance': 'balance',
        'Bonus': 'bonus',
        'LoyaltyPoints': 'loyalty_points',
        'FreeStarts': 'free_starts_spent',
        'Discount': 'discount',
        'LastActivityDate': 'fascard_last_activity_date',
        'LastLocationID': 'last_location_id',
    }

    FASCARD_TRANSACTION_FIELD_MAP = {
        'RecID':'fascard_record_id',
        'DateTime':'utc_transaction_time',
        'TransType':'transaction_type',
        'LocationID':'fascard_code',
        'MachNo':'web_display_name',
        'CardNumber':'last_four',
        'CardName':'dirty_name',
        'CreditCardAmount':'credit_card_amount',
        'CashAmount':'cash_amount',
        'BalanceAmount':'balance_amount',
        'UserAccountID':'external_fascard_user_id',
        'TransID': 'authorizedotnet_id',
        'LoyaltyCardNumber': 'loyalty_card_number',
        'CardType':'card_type',
        'AdditionalInfo':'additional_info',
        'RootTransactID':'root_transaction_id',
        'BonusAmount':'bonus_amount',
        'NewBalance':'new_balance',
        'NewBonus':'new_bonus',
        'NewFreeStarts':'new_free_starts',
        'NewLoyaltyPoints':'new_loyalty_points',
        'LoyaltyPoints':'loyalty_points',
        'EmployeeUserID':'employee_user_id',
        'TransSubType':'trans_sub_type',
        'FreeStarts':'free_starts',
        'UnfundedAmount':'unfunded_amount',
        'SysConfigID':'sys_config_id'
    }

    FASCARDAPI_TRANSACTION_FIELD_MAP = {
        'ID': 'fascard_record_id',
        'AccountID': None,
        'DateTime': 'utc_transaction_time',
        'TransType': 'transaction_type',
        'TransSubType': 'trans_sub_type',
        'LocationID': 'fascard_code',
        'MachNo': 'web_display_name',
        'CashAmount': 'cash_amount',
        'CreditCardNumber': 'last_four',
        'CreditCardAmount': 'credit_card_amount',
        'LoyaltyCardNumber': 'loyalty_card_number',
        'BalanceAmount': 'balance_amount',
        'BonusAmount': 'bonus_amount',
        'LoyaltyPoints': 'loyalty_points',
        'FreeStarts': 'free_starts',
        'NewBalance': 'new_balance',
        'NewBonus': 'new_bonus',
        'AdditionalInfo': 'additional_info',
        'UserAccountID': 'external_fascard_user_id',
        'CreditCardName': 'dirty_name',
        'EmployeeUserID': 'employee_user_id',
        'NewFreeStarts': 'new_free_starts',
        'NewLoyaltyPoints': 'new_loyalty_points',
        'RootTransactID': 'root_transaction_id',
        'UnfundedAmount': 'unfunded_amount',
        'AccountID': 'sys_config_id'
    }

    @classmethod
    def create_user_report_file_name(cls):
        file_name = 'user_report_%s.csv' % uuid4()
        return os.path.join(TEMP_DIR,file_name)

    @classmethod
    def create_transaction_report_file_name(cls):
        file_name = 'transaction_report_%s.csv' % uuid4()
        return os.path.join(TEMP_DIR,file_name)

class FascardPricingConfig(object):
    REPORT_URL = 'https://admin.fascard.com/%s/report'
    FORM_NUMBER = 0
    DROPDOWN_FORM_ID = 'cboReportID'
    ROOM_CHECKBOX_NAME = 'postedLocItems.LocItemIDs'
    PRICING_REPORT_DROWPDOWN_VALUE = '9'
    SUBMIT_BUTTON_ID = 'generatebtn'


#TODO: merge settings files once we move over to Selenium for all scraping.

class FascardSeleniumLoginConfig(object):
    LOGIN_URL = 'https://admin.fascard.com/'
    EXPECTED_POSTLOGIN_URL = 'https://admin.fascard.com/%s/AccountSettings'
    USERNAME_ID = 'UserName'
    PASSWORD_ID = 'Password'
    SUBMIT_XPATH = '//input[@value="Sign In"]'

class FascardSeleniumPricingConfig(object):
    REPORT_MAIN_URL = 'https://admin.fascard.com/%s/report'
    DROPDOWN_NAME = 'cboReportID'
    DROPDOWN_PRICING_REPORT_TEXT = 'Pricing Summary'
    POST_DROPDOWN_SELECT_WAIT_FOR_NAME = 'cboReportID' #Yes, this is the same as Dropdown name.  We could use other values as well
    POST_DROPDOWN_SELECT_DELAY_SECONDS = 10
    CHECKOX_XPATH = './/input[@value="%s" and @name="postedLocItems.LocItemIDs"]'
    POST_CHECKBOX_SELECT_DELAY_SECONDS = 10
    POST_CHECKBOX_SELECT_WAIT_FOR_NAME = 'cboReportID' #Yes, this is the same as Dropdown name.  We could use other values as well
    SUBMIT_BUTTON_ID = 'generatebtn'
    POST_SUBMIT_DELAY_SECONDS = 15
    POST_SUBMIT_WAIT_FOR_XPATH = './/table[@class="report-table"]/tbody/tr'
    TABLE_ROWS_XAPTH =  './/table[@class="report-table"]/tbody/tr'
