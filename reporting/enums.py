'''
Created on Mar 4, 2017

@author: Thomas
'''

class RevenueSplitLevel(): 
    ROOM = 'ROOM'
    BILLING_GROUP = 'BILLING_GROUP'
    
    CHOICES = ((ROOM,'Room'),(BILLING_GROUP,'Billing Group'))

class RevenueSplitFormula():
    PERCENT = 'PERCENT'
    #NATURAL_BREAKPOINT = 'NATURAL_BREAKPOINT'
    GENERAL_BREAKPOINT = 'GENERAL_BREAKPOINT'
    
    #CHOICES = ((PERCENT,'Percent'),(NATURAL_BREAKPOINT,'Natural Breakpoint'),(GENERAL_BREAKPOINT,'General Breakpoint'))
    CHOICES = ((PERCENT,'Percent'),(GENERAL_BREAKPOINT,'General Breakpoint'))
    
class RevenueSplitScheduleType():
    CONSTANT = 'CONSTANT'
    GROSS_REVENUE = 'GROSS_REVENUE'
    TIME = 'TIME'
    CHOICES = ((CONSTANT,"Constant"),(GROSS_REVENUE,"Gross Revenue"),(TIME,"Time"))     
    
    
class ExpenseType(): 
    
    STANDARD = 'STANDARD'
    CREDIT_CARD_SPLIT = 'CREDIT CARD SPLIT'
    
    CHOICES = ((STANDARD,STANDARD),(CREDIT_CARD_SPLIT,CREDIT_CARD_SPLIT))


class LocationLevel():
    LAUNDRY_ROOM = 'LAUNDRY ROOM'
    MACHINE = 'MACHINE'
    BILLING_GROUP = 'BILLING GROUP'

    CHOICES = ((LAUNDRY_ROOM,'LAUNDRY ROOM'),(MACHINE,'MACHINE'),(BILLING_GROUP,'BILLING GROUP'))
    
class MetricType():
    REVENUE_FUNDS = 'REVENUE FUNDS'
    REVENUE_FUNDS_CREDIT = 'REVENUE_FUNDS_CREDIT'
    REVENUE_FUNDS_CREDIT_PRESENT_ADD_VALUE = 'REVENUE_FUNDS_CREDIT_PRESENT_ADD_VALUE'
    REVENUE_FUNDS_CREDIT_WEB_ADD_VALUE = 'REVENUE_FUNDS_CREDIT_WEB_ADD_VALUE'
    REVENUE_FUNDS_CREDIT_DIRECT_VEND = 'REVENUE_FUNDS_CREDIT_DIRECT_VEND'
    REVENUE_FUNDS_CASH = 'REVENUE_FUNDS_CASH'
    REVENUE_FUNDS_CHECK = 'REVENUE_FUNDS_CHECK'
    REVENUE_EARNED = 'REVENUE_EARNED'
    FASCARD_REVENUE_FUNDS = 'FASCARD_REVENUE_FUNDS'
    FASCARD_REVENUE_CHECKS = 'FASCARD_REVENUE_CHECKS'
    REVENUE_NUM_ZERO_DOLLAR_TRANSACTIONS = 'REVENUE_NUM_ZERO_DOLLAR_TRANSACTIONS'
    REVENUE_NUM_NO_DATA_DAYS = 'REVENUE_NUM_NO_DATA_DAYS'
    REFUNDS = 'REFUNDS'
    TRANSACTIONS_COUNT = 'TRANSACTIONS_COUNT'
    
    CHOICES = (
        (REVENUE_FUNDS, REVENUE_FUNDS),
        (REVENUE_FUNDS_CREDIT, REVENUE_FUNDS_CREDIT),
        (REVENUE_FUNDS_CREDIT_PRESENT_ADD_VALUE, REVENUE_FUNDS_CREDIT_PRESENT_ADD_VALUE),
        (REVENUE_FUNDS_CREDIT_WEB_ADD_VALUE, REVENUE_FUNDS_CREDIT_WEB_ADD_VALUE),
        (REVENUE_FUNDS_CREDIT_DIRECT_VEND, REVENUE_FUNDS_CREDIT_DIRECT_VEND),
        (REVENUE_FUNDS_CASH, REVENUE_FUNDS_CASH),
        (REVENUE_FUNDS_CHECK, REVENUE_FUNDS_CHECK),
        (REVENUE_EARNED, REVENUE_EARNED),
        (FASCARD_REVENUE_FUNDS, FASCARD_REVENUE_FUNDS),
        (REVENUE_NUM_ZERO_DOLLAR_TRANSACTIONS, REVENUE_NUM_ZERO_DOLLAR_TRANSACTIONS),
        (REVENUE_NUM_NO_DATA_DAYS, REVENUE_NUM_NO_DATA_DAYS),
        (REFUNDS, REFUNDS),
        (TRANSACTIONS_COUNT, TRANSACTIONS_COUNT),
    )


class DurationType():
    DAY = 'DAY'
    MONTH = 'MONTH'
    YEAR = 'YEAR'
    BEFORE = 'BEFORE'
    
    DAILY_BASIS = ((DAY,DAY), (BEFORE,BEFORE))
    CHOICES = ((DAY,DAY),(MONTH,MONTH),(YEAR,YEAR),(BEFORE,BEFORE))

    
class LegalStructureType():
    COOP = 'COOP'    
    CONDO = 'CONDO'
    RENTAL = 'RENTAL'
    STUDENT_HOUSING = 'STUDENT HOUSING'
    OTHER = 'OTHER'
    UNKNOWN = 'UNKNOWN'
    
    CHOICES = (
        (COOP,COOP),
        (CONDO,CONDO),
        (RENTAL, RENTAL),
        (STUDENT_HOUSING, STUDENT_HOUSING),
        (OTHER,OTHER),
        (UNKNOWN,UNKNOWN)
    )
    
class BuildingType():
    APARTMENTS = 'APARTMENTS'    
    APARTMENT_BUILDING = 'APARTMENT BUILDING'
    DORMITORY = 'DORMITORY'
    GARDEN_APARTMENTS = 'GARDEN APARTMENTS'
    STUDENT_HOUSING = 'STUDENT HOUSING'
    OTHER = 'OTHER'
    UNKNOWN = 'UNKNOWN'
    
    CHOICES = (
        (APARTMENTS,APARTMENTS), 
        (APARTMENT_BUILDING,APARTMENT_BUILDING),
        (DORMITORY, DORMITORY),
        (GARDEN_APARTMENTS, GARDEN_APARTMENTS),
        (STUDENT_HOUSING,STUDENT_HOUSING),
        (UNKNOWN,UNKNOWN),
        (OTHER,OTHER)
    )   
    

class BGSPaymentMethods():
    ACH = 'ach'
    CHECK = 'check'
    UNKNOWN = 'unknown'

    CHOICES = (
        (ACH, ACH),
        (CHECK, CHECK),
        (UNKNOWN, UNKNOWN)
    )


class REVENUE_DATA_GRANULARITY():
    DAILY = 'daily'
    MONTHLY = 'monthly'

    CHOICES = (
        (DAILY, 'Daily'),
        (MONTHLY, 'Monthly'),
    )


class InternalDerivedMetricCalcRule():
    DIVIDE_BY_REVENUE = 'DIVIDE BY REVENUE'
    BOOLEAN = 'BOOLEAN'
    PLAIN = 'PLAIN'
    
    CHOICES = ((DIVIDE_BY_REVENUE,DIVIDE_BY_REVENUE),(BOOLEAN,BOOLEAN),(PLAIN,PLAIN))
    
    
class TransactionReportType():
    CHOICES =( 
        ('checks_deposits', 'Checks Deposits'),
        ('auto_reloads', 'Auto Reloads'),
        ('web_value_adds', 'Web Value Adds'),
        ('employee_adds', 'Employees ---- value adds to employee accounts'), 
        ('employee_activity', 'Employees ---- machine starts by employees'),
        ('employee_timesheet', 'Employees ---- Timesheet'),
        ('customer_admin_ajusts', 'Employees ---- Admin adjust to customers'),  
    ) 
  

class SortParameters:
    ALPHABETICAL = 'alphabetical'
    FASCARD_CODE = 'fascard_code'
    CHOICES = (
        ('fascard_code', 'Fascard Code'),
        ('alphabetical', 'Alphabetical')
    )


class ClientReportFileType:
    HTML = 'html'
    PDF = 'pdf'

    CHOICES = (
        (HTML, HTML),
        (PDF, PDF)
    )

class ClientRentReportMetrics:
    CLIENT_SHARE = 'client_share'
    RENT_PERCENTAGE_REVENUE = 'rent_percent_revenue'
    ACESNET_AFTER_RENT = 'aces_after_rent'
    ACESNET_PERCENTAGE_REVENUE = 'acesnet_percentage_revenue'

    # CHOICES = (
    #     (CLIENT_SHARE, 'Client Share'),
    #     (RENT_PERCENTAGE_REVENUE, 'Rent as percentage of gross revenue'),
    #     (ACESNET_AFTER_RENT, 'Aces net revenue after rent'),
    #     (ACESNET_PERCENTAGE_REVENUE, 'Aces net revenue after rent as percentage of gross revenue')
    # )

    CHOICES_DICT = {
        CLIENT_SHARE :  'Rent Payment Amount',
        RENT_PERCENTAGE_REVENUE : 'Rent as percentage of gross revenue',
        ACESNET_AFTER_RENT : 'Aces net revenue after rent',
        ACESNET_PERCENTAGE_REVENUE : 'Aces net revenue after rent as percentage of gross revenue', 
    }

    CHOICES = [(k,v) for k,v in CHOICES_DICT.items()]

class ClientLowLevelReportType:
    REFUNDS = 'refunds'
    TRANSACTIONS = 'transactions'
    NON_RECURRENT_EXPENSES = 'nonrecurrent-expenses'
    ERROR = 'error'

    CHOICES = (
        (REFUNDS, REFUNDS),
        (TRANSACTIONS, TRANSACTIONS),
        (NON_RECURRENT_EXPENSES, NON_RECURRENT_EXPENSES),
        (ERROR, ERROR)
   )


class RefundReportType:
    REFUND_BASIC_REPORT = 'basic'
    REFUND_METRIC_REPORT = 'asmetric'

    CHOICES = (
        (REFUND_BASIC_REPORT, 'Completed Refunds'),
        (REFUND_METRIC_REPORT, 'Metric: REVENUE_FUNDS - REFUNDS')
    )