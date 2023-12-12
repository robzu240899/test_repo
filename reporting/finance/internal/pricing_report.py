import collections
import calendar
import csv
import logging
import time
import itertools
import pandas as pd
import os
from collections import namedtuple
from decimal import Decimal
from datetime import datetime, date, timedelta
from dateutil.relativedelta import relativedelta
from uuid import uuid1
from collections import namedtuple
from copy import deepcopy
from django.db.models import Q, Sum
from main import settings
from itertools import groupby
from ...models import PriceHistory
from reporting.metric.calculate import RevenueEarned
from reporting.enums import LocationLevel, DurationType, MetricType, REVENUE_DATA_GRANULARITY
from reporting.helpers import Helpers
from reporting.models import MetricsCache, CustomPriceHistory
from reporting.finance.mixins import PricingChangesDataMixin
from reporting.utils import PricingPeriodDataStructure, EquipmentDataStructure, CyclePlaceholder
from revenue.enums import TransactionType
from revenue.models import LaundryTransaction
from roommanager.models import LaundryRoom, EquipmentType, MachineSlotMap

use_sentry = settings.USE_SENTRY_LOGGING

if use_sentry:
    from sentry_sdk import capture_exception, configure_scope


logger = logging.getLogger(__name__)


class DateRange(object):

    def __init__(self):
        self.start_date = None
        self.final_date = None


class PricingReport(object):

    def __init__(self, start_date, final_date, laundry_room_ids, seperate_buildings):
        self.start_date = start_date
        self.final_date = final_date
        self.laundry_room_ids = laundry_room_ids
        self.seperate_buildings = seperate_buildings
        self.csv_data = []

    def generate_csv(self):
        if self.seperate_buildings:
            [self.generate_formatted_data([laundry_room_id])
             for laundry_room_id in self.laundry_room_ids]
        else:
            self.generate_formatted_data(self.laundry_room_ids)
        csv_name = 'PricingHistory_%s_%s.csv' % (
            datetime.now().date(), uuid1())
        csv_name = os.path.join(settings.TEMP_DIR, csv_name)
        with open(csv_name, 'w') as f:
            writer = csv.writer(f)
            for row in self.csv_data:
                writer.writerow(row)
        return csv_name


    def generate_formatted_data(self, laundry_room_ids):

        # Represents the laundry room - machine type - cycle type object that we track over time
        CycleLevelKey = namedtuple(
            'CycleLevelKey', ['laundry_room_id', 'machine_type', 'cycle_type'])
        day_count = (self.final_date - self.start_date).days + 1
        price_data = {}
        dates_list = []  # list of dates.  ie 1/2/2017, 1/3,2017...
        date_range_list = []  # list of DateRange objects
        cycle_level_key_set = set()

        for dt in (self.start_date + timedelta(n) for n in range(day_count)):
            dates_list.append(dt)
            daily_price_data = {}
            for ph in PriceHistory.objects.filter(laundry_room_id__in=laundry_room_ids, price_date=dt):
                cycle_level_key = CycleLevelKey(
                    ph.laundry_room.id, ph.machine_type.lower().strip(), ph.cycle_type.lower().strip())
                cycle_level_key_set.add(cycle_level_key)
                daily_price_data[cycle_level_key] = ph.price
            price_data[dt] = daily_price_data

        # A date range is a range of dates where prices have not changed.  Let's create them here.
        if len(dates_list) == 1:
            date_range = DateRange()
            date_range.start_date = self.start_date
            date_range.final_date = self.start_date
            date_range_list.append(DateRange)
        else:
            for i in range(len(dates_list)):
                if i == 0:
                    date_range = DateRange()
                    date_range.start_date = dates_list[0]
                else:
                    t0 = dates_list[i-1]
                    t1 = dates_list[i]
                    if price_data[t0] == price_data[t1]:
                        pass
                    else:
                        date_range.final_date = t0
                        date_range_list.append(deepcopy(date_range))
                        date_range = DateRange()
                        date_range.start_date = t1
                    if i == len(dates_list) - 1:
                        date_range.final_date = t1
                        date_range_list.append(deepcopy(date_range))

        cycle_level_key_list = list(cycle_level_key_set)
        cycle_level_key_list.sort(key=lambda x: x.cycle_type)
        cycle_level_key_list.sort(key=lambda x: x.machine_type)
        cycle_level_key_list.sort(key=lambda x: LaundryRoom.objects.get(
            pk=x.laundry_room_id).display_name)

        headers = ['Laundry Room', 'Machine Type', 'Cycle Type']
        for date_range in date_range_list:
            headers.append('%s to %s' % (date_range.start_date.strftime(
                '%m/%d/%Y'), date_range.final_date.strftime('%m/%d/%Y')))
        self.csv_data.append(headers)

        for cycle_key in cycle_level_key_list:
            row = [LaundryRoom.objects.get(pk=cycle_key.laundry_room_id).display_name,
                   cycle_key.machine_type, self._clean_cycle_type(cycle_key.cycle_type)]
            for date_range in date_range_list:
                try:
                    row.append(price_data[date_range.start_date][cycle_key])
                except KeyError:
                    row.append("N/A")
            self.csv_data.append(deepcopy(row))

        # add a line break
        self.csv_data.append([' ', ' '])

        return self.csv_data

    def _clean_cycle_type(self, cycle_type):
        if cycle_type:
            cycle_type = cycle_type.replace("+", "Plus ")
        return cycle_type


class PricingPeriodMetricsHandler():

    def __init__(self, laundry_room, start_date, end_date, location_level, revenue_dfs, normalized_revenue_dfs):
        self.laundry_room = laundry_room
        self.start_date = start_date
        self.end_date = end_date
        self.location_level = location_level
        self.revenue_dfs = revenue_dfs
        self.normalized_revenue_dfs = normalized_revenue_dfs
        self.period_length = (self.end_date - self.start_date).days
        if not self.laundry_room or not self.start_date or not self.end_date:
            raise Exception("Need both Revenue and Dates to build time series data analysis.")

    def _get_formatted_months(self):
        r = relativedelta(self.end_date, self.start_date)
        total = (r.years * 12) + r.months + r.days*(12/365.0)
        return round(total, 1)

    def compute_monthly_revenue_mean(self):
        if self.period_length > 0: monthly_revenue_mean = Decimal(self.get_total_revenue() / self.period_length) * Decimal(365.25/12)
        else: monthly_revenue_mean = 0
        rounded = round(monthly_revenue_mean, 2)
        self.monthly_revenue_mean = rounded
        return "%.2f" % rounded

    def get_total_revenue(self):
        final_df = pd.concat(self.revenue_dfs, axis=1)
        total_revenue_timeseries = final_df.sum(axis=1)
        return total_revenue_timeseries.sum()

    def revenue_per_unit(self):
        assert hasattr(self, 'monthly_revenue_mean')
        units = self.laundry_room.get_units()
        if units and units > 0: return round((self.monthly_revenue_mean / units), 2)
        else: return Decimal('0.0')

    def get_revenue_timeseries(self):
        _df =  pd.concat(self.normalized_revenue_dfs, axis=1).sum(axis=1)
        _df = _df.to_frame()
        return  _df.to_json(date_format='iso')

    def get_metrics(self):
        return {
            'Total Revenue': self.get_total_revenue(),
            'Revenue Mean' : self.compute_monthly_revenue_mean(),
            'Revenue Per Unit' : self.revenue_per_unit(),
            'Revenue Timeseries' : self.get_revenue_timeseries(),
            'Total Months' : self._get_formatted_months(),
        }


# class PricingPeriodMetricsHandler():
#     """
#     This class can be refactored and incorporated into CustomPricingHistoryReport. This class is making redundant querys
#     the reason is, it was designed before we knew we were going to be getting daily revenue on an equipment basis

#     All the data this class fetches is already fetched on the daily equipment revenue. Everything should be turned into
#     a big dataframe and all the processing and metris calculation should be done by manipulating the pandas dataframe
#     """
#     def __init__(self, laundry_room, start_date, end_date, location_level, rolling_mean_periods, revenue_data_granularity):
#         self.rolling_mean_periods = rolling_mean_periods
#         self.laundry_room = laundry_room
#         self.start_date = start_date
#         self.end_date = end_date
#         self.location_level = location_level
#         self.revenue_data_granularity = revenue_data_granularity
#         if not self.laundry_room or not self.start_date or not self.end_date:
#             raise Exception(
#                 "Need both Revenue and Dates to build time series data analysis.")

#     def _get_formatted_months(self):
#         r = relativedelta(self.end_date, self.start_date)
#         total = (r.years * 12) + r.months + r.days*(12/365.0)
#         return round(total, 1)

#     def get_revenue(self):
#         """
#         Rewrite this function to receive a dataframe with all the data from daily equipment revenue
#         instead of querying data from MetricsCache
#         """
#         if self.revenue_data_granularity == REVENUE_DATA_GRANULARITY.MONTHLY:
#             delta = relativedelta(self.end_date, self.start_date)
#             initial_epochs_left = total_epochs = (delta.years*12) + delta.months
#             duration_level = DurationType.MONTH
#             epochs_unit = 'months'
#         else:
#             initial_epochs_left = total_epochs = (self.end_date - self.start_date).days
#             duration_level = DurationType.DAY
#             epochs_unit = 'days'
#         revenue_array = []
#         dates_array = []
#         next_start_date = self.start_date
#         epochs_left = initial_epochs_left
#         for day in range(epochs_left):
#             payload = {
#                 'location_level' : self.location_level,
#                 'location_id' : self.laundry_room.id,
#                 'duration' : duration_level,
#                 'metric_type' : MetricType.REVENUE_EARNED,
#                 'start_date' : next_start_date
#             }
#             try:
#                 result = MetricsCache.objects.get(**payload).result
#             except:
#                 payload.pop('metric_type')
#                 payload.pop('location_level')
#                 payload['location_type'] = self.location_level
#                 result = RevenueEarned(**payload).process()
#                 if not result: result = None
#             revenue_array.append(result)
#             dates_array.append(next_start_date)
#             next_start_date = next_start_date + relativedelta(**{epochs_unit : 1})
#         self.revenue = revenue_array
#         self.dates = dates_array
#         self.df = pd.DataFrame(self.revenue, index=self.dates, columns=['Revenue'])
#         self.df = self.df.dropna()
#         self.total_epochs = total_epochs
#         self.period_length = (self.end_date - self.start_date).days
#         return (revenue_array, dates_array)

#     def revenue_sum(self):
#         try:
#             revenue = list(filter(lambda x: (x is not None), self.revenue))
#             return Decimal(sum(revenue))
#         except Exception as e:
#             raise Exception(e)

#     def compute_monthly_revenue_mean(self):
#         if self.total_epochs > 0:
#             monthly_revenue_mean = (self.revenue_sum() / self.period_length) * Decimal(365.25/12)
#             #if self.revenue_data_granularity == REVENUE_DATA_GRANULARITY.DAILY:
#             #    monthly_revenue_mean = monthly_revenue_mean * Decimal(365.25/12)
#             #monthly_revenue_mean = ((self.revenue_sum() / self.total_days) * (365/12))
#         else:
#             monthly_revenue_mean = 0
#         rounded = round(monthly_revenue_mean, 2)
#         self.monthly_revenue_mean = rounded
#         return "%.2f" % rounded

#     def revenue_sma(self, periods):
#         rolling_mean = self.df.Revenue.rolling(window=periods).mean()
#         rolling_mean = rolling_mean.to_frame()
#         if self.revenue_data_granularity == REVENUE_DATA_GRANULARITY.DAILY: rolling_mean = (rolling_mean * (365/12.0))
#         response = rolling_mean.to_json(date_format='iso')
#         return response

#     def get_machines_in_laundryroom(self):
#         return Helpers().get_number_machines(self.laundry_room)

#     def revenue_per_unit(self):
#         assert hasattr(self, 'monthly_revenue_mean')
#         units = self.laundry_room.get_units()
#         if units and units > 0:
#             return round((self.monthly_revenue_mean / units), 2)
#         else:
#             return Decimal('0.0')

#     def get_all_metrics(self):
#         revenue, dates = self.get_revenue()
#         return {
#             'Total Revenue': self.revenue_sum(),
#             'Revenue Mean': self.compute_monthly_revenue_mean(),
#             'Revenue Per Unit' : self.revenue_per_unit(),
#             'Rolling Mean': self.revenue_sma(periods=self.rolling_mean_periods),
#             'Total Months': self._get_formatted_months(),
#         }



"""
Working on a pricing metric handler based on Pandas so we can avoid querying redundantly the database
Need to fix a couple of bugs. Almost ready for PRODUCTION

"""
#
# class PricingPeriodMetricsHandler2():
#     def __init__(self, laundry_room, location_level, rolling_mean_periods, dataframe):
#         self.rolling_mean_periods = rolling_mean_periods
#         self.laundry_room = laundry_room
#         self.location_level = location_level
#         self.dataframe = dataframe.dropna()
#         self.__set_total_revenue()
#
#     def _get_formatted_months(self):
#         r = relativedelta(self.dataframe.index[-1].to_pydatetime(), self.dataframe.index[-1].to_pydatetime())
#         total = r.months + r.days*(12/365.0)
#         return round(total, 1)
#
#     def __set_total_revenue(self):
#         self.dataframe["Total Revenue"] = self.dataframe[list(self.dataframe.columns)].sum(axis=1)
#
#     def compute_monthly_revenue_mean(self):
#         #compute_monthly_revenue_mean = ((self.revenue_sum() / self.total_days) * (365/12))
#         compute_monthly_revenue_mean = ((self.dataframe["Total Revenue"].sum() / len(self.dataframe.index)) * (365/12))
#         return round(compute_monthly_revenue_mean, 2)
#
#     def revenue_sma(self, periods):
#         rolling_mean = self.dataframe["Total Revenue"].rolling(window=self.rolling_mean_periods).mean()
#         rolling_mean = rolling_mean.to_frame()
#         rolling_mean = (rolling_mean * (365/12.0))
#         response = rolling_mean.to_json(date_format='iso')
#         return response
#
#     def revenue_sum(self):
#         return self.dataframe["Total Revenue"].sum()
#
#     def get_machines_in_laundryroom(self):
#         return Helpers().get_number_machines(self.laundry_room)
#
#     def get_all_metrics(self):
#         return {
#             'Total Revenue': self.revenue_sum(),
#             'Revenue Mean': self.compute_monthly_revenue_mean(),
#             'Rolling Mean': self.revenue_sma(periods=self.rolling_mean_periods),
#             'Total Months': self._get_formatted_months(),
#             'Total Machines': self.get_machines_in_laundryroom()
#         }

class CustomPricingHistoryReport(PricingChangesDataMixin):
    """
    Creates an entire report with as many pricing periods as specified for every
    single laundry room specified.
    """
    RevenuePeriod = collections.namedtuple(
        'RevenuePeriod',
        ['total_revenue', 'normalized_revenue', 'start_date', 'period_days_length']
    )

    def __init__(self, laundry_room_id, called_from_queue=False, months=24):
        self.rolling_mean_periods = 1 #default
        self.months = months
        self.laundry_room_id = laundry_room_id
        self.location_level = LocationLevel.LAUNDRY_ROOM
        self.response_payload = {}
        self.called_from_queue = called_from_queue

    def _get_equipment_instance(self, id):
        """
        Returns django ORM representation of the equipment type
        """
        try:
            ins = EquipmentType.objects.get(pk=id)
        except Exception as e:
            raise Exception(
                'Failed to load EquipmentType instance: {}'.format(e))
        return ins


    def _fetch_valid_machines_and_slots(self, equipment, laundry_room, start_date, end_date):
        pricing_start_date = start_date
        pricing_end_date = end_date
        #Basic Query
        machine_slots = MachineSlotMap.objects.filter(
            machine__equipment_type=equipment, 
            slot__laundry_room=laundry_room)
        #MSM that started before pricing period and ended after the pricing period started
        #or has not ended
        long_existing_msm = machine_slots.filter(
            Q(start_time__date__lte=pricing_start_date),
            Q(end_time=None) | Q(end_time__date__gt=pricing_start_date)
        )
        #Those MSM that started during the pricing period
        during_pricing_period = machine_slots.filter(
            Q(start_time__date__gte=pricing_start_date) & Q(start_time__date__lte=pricing_end_date)
        )

        # 'Manual' union. Automated union did not work 
        slots = []
        machine_ids = []
        for q in [long_existing_msm, during_pricing_period]:
            for msm in q:
                if not msm.slot.slot_fascard_id in slots:
                    slots.append(msm.slot.slot_fascard_id)
                if not msm.machine.id in machine_ids:
                    machine_ids.append(msm.machine.id)
        return slots, machine_ids


    def _load_cycles(self, pricing_period_data, pricing_start_date, pricing_end_date, laundry_room, equipment):
        available_cycles = laundry_room.pricing_history.filter(
            equipment_type=equipment
        ).values_list('cycle_type', flat=True).distinct()
        for cycle_type in available_cycles:
            cycle_history_queryset = laundry_room.pricing_history.filter(
                equipment_type=equipment,
                cycle_type=cycle_type,
            )
            cycle_history = cycle_history_queryset.filter(
                detection_date__gte=pricing_start_date,
                detection_date__lt=pricing_end_date
            ).first()

            if not cycle_history:
                #if not cycle_history was create during the pricing period
                #then the latest cycle_history is still in effect
                previous_cycle = cycle_history_queryset.filter(
                    detection_date__lt=pricing_end_date
                ).order_by('-detection_date').first()
                if previous_cycle:
                    cycle_history  = CyclePlaceholder(cycle_type, getattr(previous_cycle, 'price'))
                else:
                    cycle_history = None

            pricing_period_data.add_cycle(equipment, cycle_history)
        

    def _get_next_month_start(self, current_date):
        month_start = date(current_date.year, current_date.month, 1)
        return month_start + relativedelta(months=1)

    def _fetch_daily(self, machine_ids, laundry_room, start_date, end_date):
        #TODO
        #Possible improvement: Avoid doing a for loop by making RevenueEarned AssignedLocationManager accept
        #multiple location ids
        next_start_date = start_date
        days_left = (end_date - start_date).days
        dates_array = []
        equipment_revenue = Decimal('0.00')
        for day in range(days_left):
            daily_result = Decimal('0.00')
            for machine in machine_ids:
                payload = {
                    "location_type" : LocationLevel.MACHINE,
                    "location_id" : machine,
                    "duration" : DurationType.DAY,
                    "start_date" : next_start_date
                }
                result = RevenueEarned(**payload).process()
                #TODO Caching this results is a really good idea since we only save
                #machine daily metrics for days that we are certain we will need in the future
                #whenever we request a new pricing changes report. This is better than computing
                #machine daily metrics everyday. the only issue is updating this metrics when offline
                #transactions come in
                daily_result += result or Decimal('0.00')
            equipment_revenue += daily_result or Decimal('0.00')
            dates_array.append(next_start_date)
            next_start_date = next_start_date + relativedelta(days=1)
        normalized_revenue = Decimal(equipment_revenue / days_left) * Decimal(365.25/12)
        return self.RevenuePeriod(equipment_revenue, normalized_revenue, start_date, days_left)

    def _fetch_monthly(self, machine_ids, laundry_room, next_start_date, next_end_date):
        result = Decimal('0.00')
        payload = { "location_level" : LocationLevel.MACHINE, "metric_type" : MetricType.REVENUE_EARNED,
            "location_id__in" : machine_ids, "duration" : DurationType.MONTH, "start_date" : next_start_date
        }
        try:
            agg_sum = MetricsCache.objects.filter(**payload).aggregate(Sum('result'))['result__sum']
            if agg_sum: result = agg_sum
        except:
            #TODO note that next_end_date is the next month's start date and it needs to be excluded from daily loop fetch
            result = self._fetch_daily(machine_ids, laundry_room, next_start_date, next_end_date).total_revenue
        period_length = (next_end_date - next_start_date).days
        normalized_revenue = Decimal(result / period_length) * Decimal(365.25/12)
        return self.RevenuePeriod(result, normalized_revenue, next_start_date, period_length)

    def get_revenue_data(self, equipment, laundry_room, start_date, end_date):
        slots, machine_ids = self._fetch_valid_machines_and_slots(equipment, laundry_room, start_date, end_date)
        periods = []
        next_start_date = start_date
        next_end_date = self._get_next_month_start(start_date)
        while True:
            if next_start_date >= end_date: break
            if not machine_ids: break
            current_delta = relativedelta(next_end_date, next_start_date)
            args = (machine_ids, laundry_room, next_start_date, next_end_date)
            if current_delta.months == 0: period_revenue = self._fetch_daily(*args)
            elif current_delta.months == 1: period_revenue = self._fetch_monthly(*args)
            else: raise Exception("Invalid Delta between dates in Pricing Changes revenue fetch")
            periods.append(period_revenue)
            next_start_date = next_end_date
            next_end_date = self._get_next_month_start(next_start_date)
            if next_end_date > end_date: next_end_date = end_date
        revenues = []
        normalized_revenues = []
        units_normalized_revenues = []
        dates_array = []
        for period in periods:
            revenues.append(period.total_revenue)
            normalized_revenues.append(period.normalized_revenue)
            units_normalized_revenues.append(period.normalized_revenue / len(slots) )
            dates_array.append(period.start_date)
        revenue_df = pd.DataFrame(revenues,index=dates_array,columns=[equipment.machine_text]).dropna()
        normalized_revenue_df = pd.DataFrame(normalized_revenues,index=dates_array,columns=[equipment.machine_text]).dropna()
        units_normalized_revenue_df = pd.DataFrame(units_normalized_revenues,index=dates_array,columns=[equipment.machine_text]).dropna()
        rolling_mean = normalized_revenue_df[equipment.machine_text].rolling(window=self.rolling_mean_periods).mean()
        rolling_mean = rolling_mean.to_frame()
        EquipmentRevenue = collections.namedtuple(
            'EquipmentRevenue',
            ['total_revenue', 'revenue_df', 'normalized_df' , 'units_normalized_df', 'rolling_mean', 'machine_count']
        )
        equipment_revenue_data = EquipmentRevenue(
            sum(revenues),
            revenue_df,
            normalized_revenue_df,
            units_normalized_revenue_df,
            rolling_mean, 
            len(slots)
        )
        return equipment_revenue_data

    def get_daily_equipment_revenue(self, equipment, laundry_room, start_date, end_date):
        """
        Daily level revenue by equipment type in laundry room
        """
        slots, machine_ids = self._fetch_valid_machines_and_slots(equipment, laundry_room, start_date, end_date)
        number_of_machines = len(slots) #total_slots #Assuming one slot means one machine during the pricing period
        initial_days_left = days_left = (end_date - start_date).days
        equipment_revenue = Decimal('0.00')
        next_start_date = start_date
        daily_revenue_array = []
        dates_array = []
        for day in range(days_left):
            daily_result = Decimal('0.00')
            for machine in machine_ids:
                payload = {
                    "location_level" : LocationLevel.MACHINE,
                    "metric_type" : MetricType.REVENUE_EARNED,
                    "location_id" : machine,
                    "duration" : DurationType.DAY,
                    "start_date" : next_start_date
                }
                try:
                    result = MetricsCache.objects.get(**payload).result
                except:
                    payload.pop('metric_type')
                    payload.pop('location_level')
                    payload['location_type'] = LocationLevel.MACHINE
                    result = RevenueEarned(**payload).process()
                daily_result += result or Decimal('0.00')
            #TO-DO: Handle machine_count=0
            equipment_revenue += daily_result or Decimal('0.00')
            if number_of_machines > 0: daily_result_machine_mean = round((daily_result / number_of_machines), 3)
            else: daily_result_machine_mean = Decimal('0.00')
            dates_array.append(next_start_date)
            daily_revenue_array.append(daily_result_machine_mean)
            next_start_date = next_start_date + relativedelta(days=1)
            #TO-DO: Create a dataframe with total equipment revenue, in order to used for Pricing Period Metrics
            #calculations. Then we can perform the machine_mean operations on top of the dataframe.
            #that's the bug @juan is getting on the pandas processor function

        revenue_column_name = equipment.machine_text
        revenue_df = pd.DataFrame(
            daily_revenue_array,
            index=dates_array,
            columns=[revenue_column_name]
        )
        revenue_df = revenue_df.dropna()
        revenue_json = revenue_df.to_json(date_format='iso')

        rolling_mean = revenue_df[revenue_column_name].rolling(window=self.rolling_mean_periods).mean()
        rolling_mean = rolling_mean.to_frame()
        rolling_mean = (rolling_mean *  (365.25/12))
        EquipmentRevenue = collections.namedtuple(
            'EquipmentRevenue',
            ['total_revenue', 'dataframe', 'rolling_mean', 'machine_count']
        )
        equipment_revenue_data = EquipmentRevenue(equipment_revenue, revenue_df, rolling_mean, number_of_machines)
        return equipment_revenue_data

    def get_monthly_equipment_revenue(self, equipment, laundry_room, start_date, end_date):
        slots, machine_ids = self._fetch_valid_machines_and_slots(equipment, laundry_room, start_date, end_date)
        number_of_machines = len(slots) 
        delta = relativedelta(end_date, start_date)
        total_months = (delta.years*12) + delta.months
        equipment_revenue = Decimal('0.00')
        next_start_date = start_date
        monthly_revenue_array = []
        dates_array = []
        for month_delta in range(total_months):
            monthly_result = Decimal('0.00')
            for machine in machine_ids:
                payload = {
                    "location_level" : LocationLevel.MACHINE,
                    "metric_type" : MetricType.REVENUE_EARNED,
                    "location_id" : machine,
                    "duration" : DurationType.MONTH,
                    "start_date" : next_start_date
                }
                try:
                    result = MetricsCache.objects.get(**payload).result
                except:
                    payload.pop('metric_type')
                    payload.pop('location_level')
                    payload['location_type'] = LocationLevel.MACHINE
                    result = RevenueEarned(**payload).process()
                monthly_result += result or Decimal('0.00')

            #TO-DO: Handle machine_count=0
            equipment_revenue += monthly_result or Decimal('0.00')
            if number_of_machines > 0:
                monthly_result_machine_mean = round((monthly_result / number_of_machines), 3)
            else:
                monthly_result_machine_mean = Decimal('0.00')
            days_factor = Decimal(365.25 / 12)
            days_in_month = calendar.monthrange(next_start_date.year, next_start_date.month)[1]
            monthly_result_machine_mean_normalized = (monthly_result_machine_mean / days_in_month) * days_factor
            dates_array.append(next_start_date)
            monthly_revenue_array.append(monthly_result_machine_mean_normalized)
            next_start_date = next_start_date + relativedelta(months=1)
            #TO-DO: Create a dataframe with total equipment revenue, in order to used for Pricing Period Metrics
            #calculations. Then we can perform the machine_mean operations on top of the dataframe.
            #that's the bug @juan is getting on the pandas processor function
        revenue_column_name = equipment.machine_text
        revenue_df = pd.DataFrame(
            monthly_revenue_array,
            index=dates_array,
            columns=[revenue_column_name]
        )
        revenue_df = revenue_df.dropna()
        revenue_json = revenue_df.to_json(date_format='iso')
        rolling_mean = revenue_df[revenue_column_name].rolling(window=self.rolling_mean_periods).mean()
        rolling_mean = rolling_mean.to_frame()
        #rolling_mean = (rolling_mean *  (365.25/12))
        EquipmentRevenue = collections.namedtuple(
            'EquipmentRevenue',
            ['total_revenue', 'dataframe', 'rolling_mean', 'machine_count']
        )
        equipment_revenue_data = EquipmentRevenue(equipment_revenue, revenue_df, rolling_mean, number_of_machines)
        return equipment_revenue_data


    def get_pricing_changes(self, laundry_room):
        all_changes = list()
        extract_fields = lambda x: [str(getattr(x, field, None)) for field in fields]
        fields = ('equipment_type', 'cycle_type', 'detection_date', 'formatted_price')
        pricing_history = laundry_room.pricing_history.all()
        pricing_history = pricing_history.order_by('equipment_type', 'detection_date')
        for equipment_type, cycles in groupby(pricing_history, lambda x: x.equipment_type):
            cycles_list = [c.id for c in cycles]
            cycles_queryset = CustomPriceHistory.objects.filter(id__in=cycles_list).order_by('cycle_type')                
            for cycle_name, cycles_by_name in groupby(cycles_queryset, lambda x: x.cycle_type):
                cycles_by_name = list(cycles_by_name)
                for i in range(1, len(cycles_by_name[1:])+1):
                    prev = cycles_by_name[i-1]
                    current = cycles_by_name[i]
                    prev_data = extract_fields(prev)
                    current_data = extract_fields(current)
                    current_data[3] =  (f"${prev_data[3]} -> ${current_data[3]}")
                    all_changes.append('| '.join(current_data))

    def _get_pricing_periods(self, laundry_room, start_from, end_at):
        long_existing_pricing_periods = laundry_room.pricing_periods.filter(
            Q(start_date__lte=start_from),
            Q(end_date=None) | Q(end_date__gt=start_from)
        ).order_by('start_date')
        during_pricing_period = laundry_room.pricing_periods.filter(
            Q(start_date__gte=start_from) & Q(start_date__lte=end_at)
        ).order_by('start_date')
        pricing_periods = []
        for p in long_existing_pricing_periods: pricing_periods.append(p)
        for p in during_pricing_period: pricing_periods.append(p)
        return sorted(pricing_periods, key= lambda x: x.start_date)

    def _post_process_room(self, room, zero_count_equipment_types):
        for pricing_period_dict in self.response_payload[room]:
            for pricing_period, vals in pricing_period_dict.items():
                for et in zero_count_equipment_types:
                    logger.info(f"Deleting {et} from pricing_period data structure")
                    if et in pricing_period_dict[pricing_period]['Equipments']: del pricing_period_dict[pricing_period]['Equipments'][et]

    def generate_response(self):
        """
        Generates payload with all the data for pricing periods, equipments and laundry rooms.
        """
        laundry_room = LaundryRoom.objects.get(id=self.laundry_room_id)
        self.response_payload[laundry_room] = []
        equipment_ids = laundry_room.pricing_history.values_list('equipment_type', flat=True).distinct()
        available_equipment = list(map(self._get_equipment_instance, equipment_ids))
        start_from = date.today() - relativedelta(months=self.months)
        end_at = date.today()
        pricing_periods = self._get_pricing_periods(laundry_room, start_from, end_at)
        zero_count_equipment_types = available_equipment.copy()
        for pricing_period in pricing_periods:
            pricing_start_date = getattr(pricing_period, 'start_date', None)
            pricing_end_date = getattr(pricing_period, 'end_date', None)
            if not pricing_end_date: pricing_end_date = datetime.today().date()
            if not pricing_start_date: raise Exception('The pricing_period has no starting date. Cannnot filter price history')
            pricing_period_length = (pricing_end_date - pricing_start_date).days
            pricing_period_data = PricingPeriodDataStructure(pricing_period)
            equipment_revenue_dfs = []
            equipment_normalized_dfs = []
            total_machines = 0
            for equipment in available_equipment:
                if pricing_end_date < datetime.today().date():
                    equipment_first_history = laundry_room.pricing_history.filter(
                        equipment_type=equipment).order_by('detection_date').first()
                    detection_date = getattr(equipment_first_history, 'detection_date')
                    if detection_date and detection_date > pricing_end_date:
                            continue
                pricing_period_data.set_equipment(equipment)
                self._load_cycles(pricing_period_data, pricing_start_date, pricing_end_date, laundry_room, equipment)
                try:
                    args = (equipment,laundry_room,pricing_start_date,pricing_end_date)
                    #if self.revenue_data_granularity == REVENUE_DATA_GRANULARITY.MONTHLY:
                    #    equipment_revenue_data = self.get_monthly_equipment_revenue(*args)
                    #elif self.revenue_data_granularity == REVENUE_DATA_GRANULARITY.DAILY:
                    #    equipment_revenue_data = self.get_daily_equipment_revenue(*args)
                    equipment_revenue_data = self.get_revenue_data(*args)
                except Exception as e:
                    logger.error("Failed fetching revenue data for location {}: {}".format(laundry_room.id,e))
                    if use_sentry: capture_exception(e)
                    raise Exception(e)
                equipment_revenue = equipment_revenue_data.total_revenue
                equipment_rolling_mean = equipment_revenue_data.rolling_mean
                equipment_revenue_dfs.append(equipment_revenue_data.revenue_df)
                equipment_normalized_dfs.append(equipment_revenue_data.normalized_df)
                equipment_machine_count = equipment_revenue_data.machine_count
                if equipment_machine_count > 0 and equipment in zero_count_equipment_types:
                    zero_count_equipment_types.remove(equipment)
                total_machines += equipment_machine_count
                try:
                    equipment_revenue_machine_mean = (
                        (equipment_revenue / pricing_period_length / equipment_machine_count)
                    )
                    #if self.revenue_data_granularity == REVENUE_DATA_GRANULARITY.DAILY:
                    equipment_revenue_machine_mean = equipment_revenue_machine_mean * Decimal(365.25/12)
                except:
                    equipment_revenue_machine_mean = Decimal('0.00')
                try:
                    #Revenue per machine per month per unit (mean) calculation
                    units = laundry_room.get_units()
                    if units > 0: equipment_revenue_machine_units_mean = equipment_revenue_machine_mean / units
                    else: equipment_revenue_machine_units_mean = Decimal('0.00')
                except:
                    equipment_revenue_machine_units_mean = Decimal('0.00')

                equipment_revenue_machine_mean = round(equipment_revenue_machine_mean, 2)
                pricing_period_data.update(equipment, {'Revenue': equipment_revenue_machine_mean})
                pricing_period_data.update(equipment, {'RevenuePerMachinePerUnit': equipment_revenue_machine_units_mean})
                pricing_period_data.update(equipment, {'RevenuePerEquipment': equipment_revenue_machine_mean * equipment_machine_count})
                pricing_period_data.update(equipment, {'MachineCount': equipment_machine_count})
                pricing_period_data.update(
                    equipment,
                    {'Revenue Array': equipment_rolling_mean.to_json(date_format='iso')}
                )

            self.called_from_queue = True
            if self.called_from_queue:
                metrics_handler = PricingPeriodMetricsHandler(
                    laundry_room,
                    pricing_start_date,
                    pricing_end_date,
                    self.location_level,
                    equipment_revenue_dfs,
                    equipment_normalized_dfs
                )
                metrics_data = metrics_handler.get_metrics()
                metrics_data['Total Machines'] = total_machines
                pricing_period_data.update(pricing_period, {'Metrics': metrics_data})
            self.response_payload[laundry_room].append(pricing_period_data.get_data())
        self._post_process_room(laundry_room, zero_count_equipment_types)
        return self.response_payload
