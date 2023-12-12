'''
Created on May 16, 2018

@author: tpk6
'''
import calendar
import logging
from collections import namedtuple
from copy import deepcopy
from datetime import date
from decimal import Decimal
from django.db.models import Sum
from revenue.enums import RefundChannelChoices, RefundTypeChoices
from revenue.utils import LocationRefunds
from revenue.models import RefundAuthorizationRequest
from ...metric.calculate import MetricsCache
from ...models import LaundryRoomExtension
from ...enums import MetricType, LocationLevel, DurationType


logger = logging.getLogger(__name__)


class MetricsFetcher(object):
    
    def __init__(self, billing_group, start_date):
        self.billing_group = billing_group
        self.start_date = start_date
        self.laundry_room_data = {}
        self.totals = None
        self.bg_allow_cashflow_refunds_deduction = self.billing_group.allow_cashflow_refunds_deduction
        self.__calculate_end_of_month()
        self.calculate_laundry_room_data()
        self.calculate_totals()

    def __calculate_end_of_month(self):
        self.end_date = date(
            self.start_date.year,
            self.start_date.month,
            calendar.monthrange(*tuple([self.start_date.year, self.start_date.month]))[1]
        )


    def fetch_result(self, duration, metric_type):
        payload = deepcopy(self.general_payload)
        payload.update(
            {
                'metric_type' : metric_type,
                'duration' : duration
            }
        )
        try:
            result = MetricsCache.objects.get(**payload).result
        except MetricsCache.DoesNotExist:
            result = 0
        return result

    def _get_refunds_requests(self, laundry_room):
        refund_requests = LocationRefunds(
            LocationLevel.LAUNDRY_ROOM,
            laundry_room.id,
            self.start_date,
            self.end_date
        ).get_refunds()
        return refund_requests
        

    def fetch_refunds(self, laundry_room):
        total_refunds_cc = total_refunds_check = 0
        refund_requests = self._get_refunds_requests(laundry_room)
        if self.bg_allow_cashflow_refunds_deduction:
            #Exclude refund_Requests that explicitly ask not to pass the damae expense and force override
            refund_requests = refund_requests.exclude(
                refund_type_choice = RefundTypeChoices.DAMAGE,
                charge_damage_to_landlord=False,
                force_charge_landlord_choice=True
            )
        else:
            #Add damage refunds that explicitly ask to pass the expense and force override
            refund_requests = refund_requests.filter(
                refund_type_choice = RefundTypeChoices.DAMAGE,
                charge_damage_to_landlord=True,
                force_charge_landlord_choice=True
            )
        try:
            refunds_credit_card = refund_requests.filter(
                refund_channel=RefundChannelChoices.AUTHORIZE
            ).values('refund_amount').aggregate(result=Sum('refund_amount'))
            refunds_check = refund_requests.filter(
                refund_channel=RefundChannelChoices.CHECK
            ).values('refund_amount').aggregate(result=Sum('refund_amount'))
            total_refunds_cc = refunds_credit_card.get('result') or Decimal('0.0')
            total_refunds_check = refunds_check.get('result') or Decimal('0.0')
        except Exception as e:
            logger.info('Failed fetching refunds for room: {}'.format(laundry_room,e))
            raise Exception(e)
        return total_refunds_cc,total_refunds_check
        
    def calculate_laundry_room_data(self):
        for laundry_extension in LaundryRoomExtension.objects.filter(billing_group = self.billing_group):
            laundry_room = laundry_extension.laundry_room
            monthlys = {
                'revenue' : MetricType.REVENUE_FUNDS,
                'revenue_credit' : MetricType.REVENUE_FUNDS_CREDIT,
                'revenue_cash' : MetricType.REVENUE_FUNDS_CASH,
                'revenue_checks' : MetricType.REVENUE_FUNDS_CHECK,
                'revenue_credit_machine_starts' : MetricType.REVENUE_FUNDS_CREDIT_DIRECT_VEND,
                'revenue_credit_value_add_inroom' : MetricType.REVENUE_FUNDS_CREDIT_PRESENT_ADD_VALUE,
                'revenue_credit_value_add_web' : MetricType.REVENUE_FUNDS_CREDIT_WEB_ADD_VALUE
            }
            befores = {
                'previous_revenue' : MetricType.REVENUE_FUNDS,
            }
            self.general_payload = {
                'location_id' : laundry_room.id,
                'location_level' : LocationLevel.LAUNDRY_ROOM,
                'start_date' : self.start_date,
            }
            dataset = {}
            for name, metric_type in monthlys.items():
                result = self.fetch_result(DurationType.MONTH,metric_type)
                dataset[name] = result
            for name, metric_type in befores.items():
                result = self.fetch_result(DurationType.BEFORE,metric_type)
                dataset[name] = result
            diff_assertion_metrics = (
                'revenue_credit',
                'revenue_credit_machine_starts',
                'revenue_credit_value_add_inroom',
                'revenue_credit_value_add_web'
            )
            diff_vals = list()
            for i, metric in enumerate(diff_assertion_metrics):
                if i == 0: diff_vals.append(dataset.get(metric))
                else:diff_vals.append(dataset.get(metric) * -1)
            diff = sum(diff_vals)
            assert abs(diff) < 0.001
            total_refunds_cc, total_refunds_check = self.fetch_refunds(laundry_room)
            self.laundry_room_data[laundry_room.id] =  {
                'display_name': laundry_room.display_name,
                'revenue': dataset.get('revenue'),
                'revenue_credit': dataset.get('revenue_credit'),
                'revenue_cash': dataset.get('revenue_cash'),
                'revenue_credit_machine_starts': dataset.get('revenue_credit_machine_starts'),
                'revenue_credit_value_add_inroom': dataset.get('revenue_credit_value_add_inroom'),
                'revenue_credit_value_add_web': dataset.get('revenue_credit_value_add_web'),
                'previous_revenue': dataset.get('previous_revenue'),
                'revenue_checks': dataset.get('revenue_checks'),
                'refunds_credit_card' : total_refunds_cc,
                'refunds_check' : total_refunds_check,
                'total_refunds' : total_refunds_cc + total_refunds_check
            }
    
    def calculate_totals(self):
        #TODO substract refunds from categories?
        #new totals calculation
        exclude_fields = ('display_name',)
        self.totals = {'display_name' : 'Totals'}
        for room, data in self.laundry_room_data.items():
            for k,v in data.items():
                if k in exclude_fields: continue
                if not k in self.totals: self.totals[k] = 0
                self.totals[k] += v
        self.totals['revenue_credit'] = self.totals['revenue_credit'] - self.totals['refunds_credit_card']
        self.totals['revenue_checks'] = self.totals['revenue_checks'] - self.totals['refunds_check']
        self.totals['revenue'] = self.totals['revenue'] - self.totals['total_refunds']