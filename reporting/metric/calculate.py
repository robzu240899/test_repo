import logging
from decimal import Decimal
from django.db.models import Q, F, Sum, Count
from dateutil.relativedelta import relativedelta
from datetime import datetime,timedelta
from revenue.models import LaundryTransaction, Refund
from reporting.enums import LocationLevel, MetricType, DurationType
from revenue.enums import TransactionType, AddValueSubType
from reporting.models import MetricsCache, LaundryRoomExtension
from revenue.filterhelpers import StandardFilters as RevQs


logger = logging.getLogger(__name__)


class TimeManager(object):

    def __init__(self, start_date, duration):
        self.start_date = start_date
        self.duration = duration
        self._set_end_date()

    def _set_end_date(self):
        duration = self.duration
        start_date = self.start_date
        if duration == DurationType.DAY:
            end_date = start_date + relativedelta(days=1)
        elif duration == DurationType.MONTH:
            end_date = start_date + relativedelta(months=1)
        elif duration == DurationType.YEAR:
            end_date = start_date + relativedelta(years=1)
        elif duration == DurationType.BEFORE:
            end_date = None
        else:
            logger.error(f"CacheFramework.calculate_and_cache did not recognize the duration enum: {duration}", exc_info=True)
            raise Exception("CacheFramework.calculate_and_cache did not recognize the duration enum")
        if end_date:
            today = datetime.now().date()
            end_date = min([end_date,today])
        self.end_date = end_date

class AssignedTimeManager(TimeManager):

    def apply_time_filter(self,qryset):
        duration = self.duration
        start_date = self.start_date
        end_date = self.end_date

        if duration == DurationType.BEFORE:
            qryset = qryset.filter(assigned_local_transaction_time__date__lt=start_date)
        else:
            qryset = qryset.filter(assigned_local_transaction_time__date__gte=start_date)
            qryset = qryset.filter(assigned_local_transaction_time__date__lt=end_date)
        return qryset

class FascardTimeManager(TimeManager):

    def apply_time_filter(self,qryset):
        duration = self.duration
        start_date = self.start_date
        end_date = self.end_date

        if duration == DurationType.BEFORE:
            qryset = qryset.filter(local_transaction_time__date__lt=start_date)
        else:
            qryset = qryset.filter(local_transaction_time__date__gte=start_date)
            qryset = qryset.filter(local_transaction_time__date__lt=end_date)
        return qryset


class AssignedLocationManager(object):

    def __init__(self, location_type, location_id):
        self.location_type = location_type
        self.location_id = location_id

    def apply_location_filter(self, qryset):
        location_level = self.location_type
        location_id = self.location_id
        if location_level == LocationLevel.LAUNDRY_ROOM:
            qryset = qryset.filter(assigned_laundry_room_id=location_id)
        elif location_level == LocationLevel.MACHINE:
            qryset = qryset.filter(machine_id=location_id)
        elif location_level == LocationLevel.BILLING_GROUP:
            laundry_room_id_list = LaundryRoomExtension.objects.filter(billing_group_id=location_id).values_list('laundry_room_id',flat=True).distinct()
            qryset = qryset.filter(assigned_laundry_room_id__in=laundry_room_id_list)
        else:
            raise Exception("CacheFramework.calculate_and_cache did not recognize the location enum")
        return qryset

class FascardLocationManager(object):

    def __init__(self, location_type, location_id):
        self.location_type = location_type
        self.location_id = location_id

    def apply_location_filter(self, qryset):
        location_level = self.location_type
        location_id = self.location_id
        if location_level == LocationLevel.LAUNDRY_ROOM:
            qryset = qryset.filter(laundry_room_id=location_id)
        elif location_level == LocationLevel.MACHINE:
            qryset = qryset.filter(machine_id=location_id)
        elif location_level == LocationLevel.BILLING_GROUP:
            laundry_group_id_list = LaundryRoomExtension.objects.filter(billing_group_id=location_id).values_list('laundry_room_id',flat=True).distinct()
            qryset = qryset.filter(laundry_room_id__in=laundry_group_id_list)
        else:
            raise Exception("CacheFramework.calculate_and_cache did not recognize the location enum")
        return qryset


class Metric():

    standard_filters = [Q(fascard_user__is_employee=False) | Q(fascard_user=None)]
    transaction_type_filters = None
    result_calculation = None
    TimeMangerClass = AssignedTimeManager
    LocationManagerClass = AssignedLocationManager

    #def __init__(self, location_type, location_id, duration, start_date):
    def __init__(self, location_type, location_id, duration, start_date, queryset=None):
        if queryset is None:
            queryset = LaundryTransaction.objects.filter(
                Q(fascard_user__is_employee=False) | Q(fascard_user=None))
        self.time_manager = self.TimeMangerClass(start_date, duration)
        self.location_manager = self.LocationManagerClass(location_type, location_id)
        self.qryset = queryset
        self._check_prerequists()

    def _check_prerequists(self):
        pass

    def _calculate_result(self):
        #get only the values needed
        self.qryset = self.qryset.values(*self.values_needed).aggregate(result = self.result_calculation)
        #self.qryset = self.qryset.aggregate(result = self.result_calculation)
        return self.qryset['result']

    def process(self):
        #self.qryset=LaundryTransaction.objects.all()
        #self.qryset=LaundryTransaction.objects.filter(*standard_filters)
        #for standard_filter in self.standard_filters:
        #    self.qryset = self.qryset.filter(standard_filter)
        for transaction_type_filter in self.transaction_type_filters:
            self.qryset = self.qryset.filter(transaction_type_filter)
        self.qryset = self.time_manager.apply_time_filter(self.qryset)
        self.qryset = self.location_manager.apply_location_filter(self.qryset)
        return self._calculate_result()

class RevenueFunds(Metric):
    '''
    Total money collected plus amount charged to credit cards
    '''
    values_needed = ('credit_card_amount','cash_amount')
    transaction_type_filters = [Q(transaction_type=TransactionType.ADD_VALUE) | Q(transaction_type=TransactionType.VEND)]
    result_calculation = Sum(F('credit_card_amount') + F('cash_amount'))

class RevenueFundsCredit(Metric):
    '''
    Amount charged to credit cards
    '''
    values_needed = ('credit_card_amount',)
    transaction_type_filters = [Q(transaction_type=TransactionType.ADD_VALUE) | Q(transaction_type=TransactionType.VEND)]
    result_calculation = Sum('credit_card_amount')

class RevenueFundsWebValueAdd(Metric):
    '''
    Total money collected via web value add transactions
    '''
    values_needed = ('credit_card_amount',)
    transaction_type_filters = [RevQs.WEB_VALUE_ADD_Q]
    result_calculation = Sum('credit_card_amount')


class RevenueFundsCreditDirectVend(Metric):
    '''
    Credit card used to start machine directly (ie no loyalty card involved)
    '''
    values_needed = ('credit_card_amount',)
    transaction_type_filters=  [Q(transaction_type=TransactionType.VEND)]
    result_calculation = Sum('credit_card_amount')

class RevenueFundsCreditPressentAddValue(Metric):
    '''
    Credit card was used in person to add value to a loyalty card
    '''
    values_needed = ('credit_card_amount',)
    transaction_type_filters = [Q(transaction_type=TransactionType.ADD_VALUE), Q(trans_sub_type=AddValueSubType.CREDIT_AT_READER)] #NB See enum definition for notes on what this means
    result_calculation = Sum('credit_card_amount')

class RevenueFundsCash(Metric):
    '''
    All cash that is collected
    '''
    values_needed = ('cash_amount',)
    transaction_type_filters = [Q(transaction_type=TransactionType.ADD_VALUE), Q(trans_sub_type=AddValueSubType.CREDIT_AT_READER)]  #NB See enum definition for notes on what this means
    result_calculation = Sum('cash_amount')

class RevenueFundsCheck(Metric):
    '''
    Checks are collected and value is added by an employee using a "Value Added To Account" adjustment on the website.
    '''
    values_needed = ('cash_amount',)
    transaction_type_filters = [Q(transaction_type=TransactionType.ADD_VALUE), Q(trans_sub_type=AddValueSubType.CASH)]  #NB See enum definition for notes on what this means
    result_calculation = Sum('cash_amount')

class RevenueEarned(Metric):
    '''
    Total amount spent to start laundry machines
    '''
    values_needed = ('credit_card_amount','cash_amount', 'balance_amount')
    transaction_type_filters = [Q(transaction_type=TransactionType.VEND)]
    result_calculation = Sum(F('credit_card_amount') + F('cash_amount') + F('balance_amount'))


class TransactionCount(Metric):
    transaction_type_filters = [Q(transaction_type=TransactionType.VEND)]

    def _calculate_result(self):
        return self.qryset.count()

class RevenueFascardFunds(RevenueFunds):
    '''
    Funds collected based on Fascard timing and Assigned room
    '''
    transaction_type_filters = [
        Q(transaction_type=TransactionType.ADD_VALUE) | Q(transaction_type=TransactionType.VEND) | Q(transaction_type=TransactionType.COINS)
    ]
    TimeMangerClass = FascardTimeManager
    LocationManagerClass = FascardLocationManager


class RevenueFascardChecks(RevenueFundsCheck):
    '''
    Total Amount of Checks per Original Laundry Room in attribution
    '''
    TimeMangerClass = FascardTimeManager
    LocationManagerClass = FascardLocationManager


class RevenueNumberDaysNoData(Metric):
    '''
    Number of days with zero revenue of any type (cash or funds)
    '''
    values_needed = ('cash_amount',)
    transaction_type_filters = [Q(transaction_type=TransactionType.ADD_VALUE) | Q(transaction_type=TransactionType.VEND)]
    result_calculation = Sum('cash_amount')

    def _calculate_result(self):
        start_date = self.time_manager.start_date
        end_date = self.time_manager.end_date
        days_in_period = (end_date-start_date).days
        self.qryset = self.qryset.values('local_transaction_date').annotate(num_tx=Count('id')).filter(num_tx__gt=0)
        num_days_with_tx = self.qryset.count()
        num_days_no_tx = days_in_period - num_days_with_tx
        return num_days_no_tx

class RevenueNumberZeroDollarTransactions(Metric):
    '''
    Number of days with zero revenue of any type (cash or funds)
    '''

    transaction_type_filters = [Q(transaction_type=TransactionType.VEND),
                                Q( Q(Q(credit_card_amount=0) | Q(credit_card_amount__isnull = True)) & Q(Q(cash_amount=0) | Q(cash_amount__isnull = True)) & Q(Q(balance_amount=0) | Q(balance_amount__isnull = True)) )]

    def _calculate_result(self):
        return self.qryset.count()


class RefundLocationManager(object):

    def __init__(self, location_type, location_id):
        self.location_type = location_type
        self.location_id = location_id

    def apply_location_filter(self, qryset):
        location_level = self.location_type
        location_id = self.location_id
        if location_level == LocationLevel.LAUNDRY_ROOM:
            qryset = qryset.filter(transaction__assigned_laundry_room_id=location_id)
        elif location_level == LocationLevel.MACHINE:
            qryset = qryset.filter(transaction__machine_id=location_id)
        elif location_level == LocationLevel.BILLING_GROUP:
            laundry_room_id_list = LaundryRoomExtension.objects.filter(billing_group_id=location_id).values_list('laundry_room_id',flat=True).distinct()
            qryset = qryset.filter(transaction__assigned_laundry_room_id__in=laundry_room_id_list)
        else:
            raise Exception("CacheFramework.calculate_and_cache did not recognize the location enum")
        return qryset


class RefundsTimeManager(TimeManager):

    def apply_time_filter(self,qryset):
        duration = self.duration
        start_date = self.start_date
        end_date = self.end_date
        if duration == DurationType.BEFORE:
            qryset = qryset.filter(timestamp__date__lt=start_date)
        else:
            qryset = qryset.filter(timestamp__date__gte=start_date)
            qryset = qryset.filter(timestamp__date__lte=end_date)
            #TODO: Change back to lt only
        return qryset


class Refunds(Metric):
    values_needed = ('amount',)
    result_calculation = Sum('amount')
    transaction_type_filters = []
    LocationManagerClass = RefundLocationManager
    TimeMangerClass = RefundsTimeManager

    def __init__(self, *args, queryset=None, **kwargs):
        if not queryset:
            queryset = Refund.objects.all()
        super(Refunds, self).__init__(*args, queryset=queryset, **kwargs)

    def process(self):
        self.qryset = self.time_manager.apply_time_filter(self.qryset)
        self.qryset = self.location_manager.apply_location_filter(self.qryset)
        return self._calculate_result()


class CacheFramework(object):

    @classmethod
    def calculate_and_cache(cls,metric_type,start_date,duration,location_level,location_id,queryset,metric_record):

        if metric_type in [MetricType.REVENUE_NUM_NO_DATA_DAYS,MetricType.REVENUE_NUM_ZERO_DOLLAR_TRANSACTIONS] and duration ==DurationType.BEFORE:
            raise Exception("Before may not be used with this metric type")

        kwargs = {
            'start_date' : start_date, 
            'duration' : duration, 
            'location_type' : location_level, 
            'location_id' : location_id,
            'queryset' : queryset
        }

        if metric_type == MetricType.REVENUE_FUNDS:
            result = RevenueFunds(**kwargs).process()
        elif metric_type == MetricType.REVENUE_EARNED:
            result = RevenueEarned(**kwargs).process()
        elif metric_type == MetricType.FASCARD_REVENUE_FUNDS:
            result = RevenueFascardFunds(**kwargs).process()
        elif metric_type == MetricType.FASCARD_REVENUE_CHECKS:
            result = RevenueFascardChecks(**kwargs).process()
        elif metric_type == MetricType.REVENUE_FUNDS_CREDIT_DIRECT_VEND:
            result = RevenueFundsCreditDirectVend(**kwargs).process()
        elif metric_type == MetricType.REVENUE_FUNDS_CREDIT_PRESENT_ADD_VALUE:
            result = RevenueFundsCreditPressentAddValue(**kwargs).process()
        elif metric_type == MetricType.REVENUE_FUNDS_CREDIT_WEB_ADD_VALUE:
            result = RevenueFundsWebValueAdd(**kwargs).process()
        elif metric_type == MetricType.REVENUE_FUNDS_CREDIT:
            result = RevenueFundsCredit(**kwargs).process()
        elif metric_type == MetricType.REVENUE_FUNDS_CASH:
            result = RevenueFundsCash(**kwargs).process()
        elif metric_type == MetricType.REVENUE_FUNDS_CHECK:
            result  = RevenueFundsCheck(**kwargs).process()
        elif metric_type == MetricType.REVENUE_EARNED:
            result = RevenueEarned(**kwargs).process()
        elif metric_type == MetricType.REVENUE_NUM_NO_DATA_DAYS:
            result = RevenueNumberDaysNoData(**kwargs).process()
        elif metric_type == MetricType.REVENUE_NUM_ZERO_DOLLAR_TRANSACTIONS:
            result = RevenueNumberZeroDollarTransactions(**kwargs).process()
        elif metric_type == MetricType.REFUNDS:
            kwargs.pop('queryset')
            result = Refunds(**kwargs).process()
        elif metric_type == MetricType.TRANSACTIONS_COUNT:
            result = TransactionCount(**kwargs).process()
        else:
            raise Exception("CacheFramework.calculate_and_cache did not recognize the metric type enum")

        #As convention, we'll say the result is 0 if it is None
        if result is None:
            result = Decimal("0.00")

        #Update the metric if it exsits, or create a new one.
        # metrics = MetricsCache.objects.filter(metric_type=metric_type,start_date=start_date,duration=duration,location_level=location_level,location_id=location_id)
        # if len(metrics)>1:
        #     raise Exception("2 metrics found. Max 1.")
        # else:
        #     metric = metrics.first()
        if not metric_record:
            metric_record = MetricsCache.objects.create(
                metric_type=metric_type,
                start_date=start_date,
                duration=duration,
                location_level=location_level,
                location_id=location_id,
                result=result
            )
        else:
            metric_record.result = result
            if metric_record.needs_processing:
                metric_record.needs_processing = False
            metric_record.save()
        return metric_record
