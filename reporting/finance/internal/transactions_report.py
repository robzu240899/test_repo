import csv
import copy
import logging
import pandas as pd
import numpy as np
from typing import List
from io import StringIO, BytesIO
from datetime import date, timedelta
from tablib import Dataset
from django.conf import settings
from django.core.files.base import ContentFile
from django.core.mail import EmailMessage
from django.db.models import Q
from django.template.loader import get_template
from revenue.enums import TransactionType, AddValueSubType
from revenue.models import LaundryTransaction, FascardUser
from roommanager.models import LaundryRoom, Slot, HardwareBundlePairing
from reporting.helpers import Helpers
from reporting.models import TimeSheetsReportStoredFile


logger = logging.getLogger(__name__) 


class BasicDataset():

    def __init__(self):
        self.buffer = StringIO()
        self.dataset = csv.writer(self.buffer)

    def append(self, row: List) -> None:
        self.dataset.writerow(row)

    def export(self) -> str:
        return self.buffer.getvalue()


class TransactionReport():
    transaction_headers = [
        'local_transaction_time',
        'transaction_type',
        'trans_sub_type',
        'fascard_user__name',
        'fascard_user__fascard_url',
        'fascard_user__is_employee',
        'credit_card_amount',
        'cash_amount',
        'balance_amount',
        'bonus_amount',
        'new_balance',
        'new_bonus',
        'additional_info',
        'assigned_laundry_room__display_name',
        'laundry_room__display_name',
        'slot',
        'machine__asset_code'
    ]
    
    TX_MAP = {
        'checks_deposits' : 
            {
                'transaction_type' : TransactionType.ADD_VALUE,
                'trans_sub_type' : AddValueSubType.CASH
            },
        'auto_reloads' :
            {
                'transaction_type' : TransactionType.ADMIN_ADJUST,
                'employee_user_id' : 0
            },
        'web_value_adds' :
            {
                'transaction_type' : TransactionType.ADD_VALUE,
                'trans_sub_type' : AddValueSubType.CREDIT_ON_WEBSITE
            },
        'employee_adds':
            {
                'transaction_type__in' : [TransactionType.ADMIN_ADJUST, TransactionType.ADD_VALUE],
                'fascard_user__is_employee' : True,
                'fascard_user__fascard_user_account_id__in' : None
            },
        'employee_activity':
            {
                'transaction_type' : TransactionType.VEND,
                'fascard_user__fascard_user_account_id__in' : None,
                'external_fascard_user_id__in' : None,
            },
        'employee_timesheet':
            {
                'transaction_type' : TransactionType.VEND,
                'fascard_user__fascard_user_account_id__in' : None,
                'external_fascard_user_id__in' : None,
            },
        'customer_admin_ajusts':
            {
                'transaction_type' : TransactionType.ADMIN_ADJUST,
                'employee_user_id__in' : None
            }
    }

    EXTRA_HEADERS = {
        'checks_deposits' : None,
        'auto_reloads' : None,
        'web_value_adds' : None,
        'employee_adds' : ['employee_adding_funds'],
        'employee_activity' : ['employee_adding_funds'],
        'customer_admin_ajusts' : ['employee_adding_funds']
    }

    def __init__(self, start, end, tx_type, employees, extra_data=None, custom_query=None, **kwargs):
        assert isinstance(start, date)
        assert isinstance(end, date)
        self.start = start
        self.end = end
        self.tx_type = tx_type
        self.employees = employees
        #self.extra_data = extra_data
        #self.custom_query = custom_query
        self.extra_data, self.custom_query = self.__init_extra_filters()
        self.extra_headers = copy.deepcopy(self.EXTRA_HEADERS.get(self.tx_type))
        self.dataset = Dataset()
        for k,v in kwargs.items():
            setattr(self, k, v)

    def __init_extra_filters(self):
        assert hasattr(self, 'tx_type')
        assert hasattr(self, 'employees')
        extra_filters = None
        custom_query = None
        employees_ids = [e.fascard_user_account_id for e in self.employees]
        if self.tx_type == 'customer_admin_ajusts' and len(employees_ids) > 0:
                extra_filters = {'employee_user_id__in' : [e.xxx_caution_fascard_user_id for e in self.employees]}
        elif len(employees_ids) > 0:
            if self.tx_type in ['employee_activity', 'employee_timesheet']:
                custom_query = [
                    Q(fascard_user__fascard_user_account_id__in=employees_ids) | Q(external_fascard_user_id__in=employees_ids)
                ]
            else:
                extra_filters = {
                    'fascard_user__fascard_user_account_id__in' : employees_ids,
                    'external_fascard_user_id__in' : employees_ids
                }
        return extra_filters, custom_query

    def as_row(self, record):
        row = []
        for record_header in self.report_headers:
            if hasattr(record, record_header):
                value = getattr(record, record_header)
            else:
                if '__' in record_header:
                    try:
                        value = record
                        for field in record_header.split('__'):
                            value = getattr(value, field)
                            if value is None:
                                break
                        if record_header == "fascard_user__fascard_url" and value is None:
                            tx_fascard_user_id = getattr(record, 'external_fascard_user_id')
                            value = f"https://admin.fascard.com/86/loyaltyaccounts?recid={tx_fascard_user_id}&page=1"
                    except Exception as e:
                        logger.error(e)
                        raise Exception(e)
            row.append(value)
        return row

    def generate_dataset(self):
        for record in self.queryset:
            self.dataset.append(self.as_row(record))
        self.dataset.headers = self.report_headers

    def _get_queryset(self, extra_filters):
        return LaundryTransaction.objects.filter(
            local_transaction_date__gte=self.start,
            local_transaction_date__lte=self.end,
            **extra_filters
        )

    def _build_filters(self):
        tx_map = copy.deepcopy(self.TX_MAP.get(self.tx_type))
        temp_dict = copy.deepcopy(tx_map)        
        for key,value in temp_dict.items():
            if value is None:
                try:
                    v = self.extra_data[key]
                    tx_map[key] = v
                except (KeyError, TypeError):
                    #In case no data was specified, drop that filter
                    tx_map.pop(key)
        return tx_map

    def _export(self):
        if isinstance(self.dataset, Dataset):
            return self.dataset.export('csv')
        elif isinstance(self.dataset, BasicDataset):
            return self.dataset.export()
        else:
            return None

    def _add_extra_headers(self):
        if self.extra_headers:
            self.report_headers = self.report_headers + self.extra_headers
        
    def get(self):
        tx_map = self._build_filters()
        self.report_headers = self.transaction_headers
        self._add_extra_headers()
        self.queryset = self._get_queryset(tx_map)
        if self.custom_query:
            for q in self.custom_query:
                self.queryset = self.queryset.filter(q)
        self.generate_dataset()
        return self._export()


class TransactionsTimeSheet(TransactionReport):
    """
    Special report of employee starts in timesheet style
    """
    transaction_headers = ()


    def __init__(self, *args, **kwargs):
        super(TransactionsTimeSheet, self).__init__(*args, **kwargs)
        self.dataset = BasicDataset()
        self.backend_processing = False

    def _add_extra_headers(self):
        pass

    def _format_time_delta(self, delta: timedelta) -> str:
        hours, remainder = divmod(delta.total_seconds(), 3600)
        minutes, seconds = divmod(remainder, 60)
        total_minutes = minutes + (seconds / 60.0)
        final_str = ""
        if hours >= 1: final_str += ' %.f hours, ' % hours
        final_str += '%.2f minutes ' % total_minutes
        final_str += "({:02}:{:02}:{:02})".format(int(hours), int(minutes), int(seconds))
        return final_str

    def _process_locations(self, current_day_data : pd.DataFrame, employee_name : str, employee_date, locations):
        #TODO: Nice to-do: break up this function into two: one for processing transactions and one for processing scans
        self.travel_time = timedelta(0)
        latest_end_time = None #Used to keep track of the latest start at a previous location in order to calculate time between rooms
        at_least_one_machine_started = True
        for i, location in enumerate(locations):
            location_obj = LaundryRoom.objects.filter(display_name=location).first()
            if not location_obj: continue
            location_starts = current_day_data.loc[location]
            location_start_time = pd.Timestamp(location_starts.index.values[0]).to_pydatetime()
            location_end_time = pd.Timestamp(location_starts.index.values[-1]).to_pydatetime()
            time_in_room = location_end_time - location_start_time
            location_data = {
                'name' : location,
                'dryers_started' : None,
                'total_dryers ' : None,
                'washers_started' : None,
                'total_washers' : None,
                'total_slots' : None,
                'non_scanned_slots' : None,
                'time_in_room' : self._format_time_delta(time_in_room),
                'time_since_previous_room' : None,
                'starts' : [],
                'scans' : [],
                'non_started_slots' : None
            }
            if i > 0:
                delta = location_start_time - latest_end_time
                if delta.total_seconds() >= 0:
                    self.travel_time += delta
                    location_data['time_since_previous_room'] = self._format_time_delta(delta)
                else:
                    location_data['time_since_previous_room'] = f"Overlap. Current Location's Start Time: {location_start_time.strftime('%Y-%m-%d %I:%M %p')}. \
                        Previous Location's End Time: {latest_end_time.strftime('%Y-%m-%d %I:%M %p')}"
            washers, dryers = Helpers.get_number_of_pockets(location_obj)
            location_data['total_washers'] = washers
            location_data['total_dryers'] = dryers
            location_starts_transactions = location_starts[location_starts["Type"]=='transaction']
            slots_started_ids = location_starts_transactions.SlotID.unique()
            slots_started = Slot.objects.filter(slot_fascard_id__in=slots_started_ids)
            all_slots = location_obj.slot_set.filter(is_active=True)
            location_data['total_slots'] = len(all_slots)
            #NON-STARTED SLOTS
            #location_data['non_started_slots'] = set(all_slots) - set(slots_started)
            msm_query = []
            for slot in slots_started:
                msm_query.append(
                    slot.machineslotmap_set.order_by('-start_time').first()
                )
            if msm_query:
                washers_started, dryers_started = Helpers.get_number_of_pockets(
                    location_obj,
                    qry = msm_query
                )
                at_least_one_machine_started = True
            else:
                washers_started = dryers_started = 0
            location_data['washers_started'] = washers_started
            location_data['dryers_started'] = dryers_started
            self.dataset[employee_name][employee_date]['locations'].append(location_data)
            latest_end_time = location_end_time
            #TODO: Add Starts data
                #(timestamp, slot, asset_code)
            location_data['starts'] = list(zip(*map(location_starts_transactions.get, ['Time','Slot#', 'SlotID', 'Machine', 'BundleStatus'])))
            #Add Scanning Info
            location_scans = location_starts[location_starts["Type"]=='scan']
            slots_scanned_ids = location_scans.SlotID.unique()
            location_data['non_started_slots'] = all_slots.exclude(slot_fascard_id__in=[int(s) for s in slots_scanned_ids if s] + [int(s) for s in slots_started_ids if s])
            location_data['scans'] = list(zip(*map(location_scans.get, ['Time','Slot#', 'SlotID', 'Machine', 'BundleStatus'])))
            if at_least_one_machine_started and self.travel_time.total_seconds() == 0:
                logger.error(f"At least one machine was started but travel time was zero for {employee_name} on {employee_date}")


    def _process_employee(self, employee_name, employee_dates):
        for employee_date in employee_dates:
            current_day_data = self.pandas_df.loc[(employee_name, employee_date)]
            day_start = current_day_data.index.values[0][1].to_pydatetime() #[1] references machine start timestamp
            day_end = current_day_data.index.values[-1][1].to_pydatetime()
            #TODO Also add locations that had only scans but no transactions
            locations = current_day_data.index.get_level_values('Location').unique()
            self.dataset[employee_name][employee_date] = {
                'rooms_visited': len(locations),
                'time_worked' : self._format_time_delta(day_end - day_start),
                'day_start_time' : day_start,
                'day_end_time' : day_end,
                'travel_time' : None,
                'locations' : []
            }
            #TODO: Calculate travel time between rooms.
            self._process_locations(current_day_data, employee_name, employee_date, locations)
            assert hasattr(self, 'travel_time')
            self.dataset[employee_name][employee_date]['travel_time'] = self._format_time_delta(self.travel_time)

    def create(self):
        self.backend_processing = True
        self.get()
        return "Success"

    def emailit(self):
        email = EmailMessage(
            'TimeSheet Report',
            'Please see attached',
            settings.DEFAULT_FROM_EMAIL,
            self.user_email.split(',')
        )
        template = get_template('timesheet_report.html')
        html_response = template.render({'dataset': self.dataset}).encode(encoding='UTF-8')
        html_binary_data = BytesIO(html_response)
        email.attach('timesheets_report.html', html_response, 'text/html')
        email.send(fail_silently=False)

    def save_file(self):
        assert hasattr(self, 'employee')
        assert hasattr(self, 'job_tracker')
        template = get_template('timesheet_report.html')
        html_response = template.render({'dataset': self.dataset}).encode(encoding='UTF-8')
        html_binary_data = BytesIO(html_response)
        try:
            existing_report = TimeSheetsReportStoredFile.objects.get(employee=self.employee)
            existing_report.report_file.delete()
            existing_report.delete()
        except:
            pass
        report_file_object = TimeSheetsReportStoredFile.objects.create(
           employee = self.employee,
           jobs_tracker = self.job_tracker)
        user_name = self.employee.name or 'UnknownName-FascardID'
        user_name = '{}({})'.format(
           user_name,
           str(self.employee.fascard_user_account_id))
        filename = '{}/'.format(user_name)
        filename += "timesheets-report.html" 
        report_file_object.report_file.save(filename, ContentFile(html_binary_data.getvalue()))

    def _append_extra_info(self, values, obj_type):
        temp_memory = {}
        for i in range(0, len(values)):
            slot_fascard_id = values[i][4]
            if not slot_fascard_id in temp_memory:
                try:
                    obj = Slot.objects.get(slot_fascard_id=slot_fascard_id)
                    slot_status = obj.get_bundle_status()
                except:
                    slot_status = 'Unknown'
                temp_memory[slot_fascard_id] = {'status' : slot_status}
            values[i] = values[i] + (temp_memory[slot_fascard_id]['status'], obj_type)
        return values

    def _load_pandas_dataframe(self, list_q_values):
        df = pd.DataFrame(
            list_q_values,
            columns=[
                "Date",
                "Time",
                "Location",
                "Slot#",
                "SlotID",
                "Machine",
                "Employee",
                "BundleStatus",
                "Type"
            ]
        )
        df.sort_values(['Employee', 'Date', 'Time'], inplace=True)
        indexes = ['Employee', 'Date', 'Location', 'Time']
        index = pd.MultiIndex.from_frame(df[indexes],names=indexes)
        df.replace(np.nan, '', regex=True, inplace=True)
        df.index = index
        return df

    def _load_scanning_data(self):
        tx_map = self._build_filters()
        scans_employees = tx_map.get('fascard_user__fascard_user_account_id__in')
        if not scans_employees:
            logger.info("not initial scans_employees")
            tx_based_employees = list(self.queryset.values_list('fascard_user__fascard_user_account_id', flat=True))
            logger.info(f"TX-based employee ids: {tx_based_employees}")
            employees_ids = [e.fascard_user_account_id for e in self.employees]
            logger.info(f"Manually selected employee ids: {employees_ids}")
            scans_employees = list(set(tx_based_employees + employees_ids))
            logger.info(f"All ids: {scans_employees}")
        bundles_queryset = HardwareBundlePairing.objects.filter(
            tech_employee__fascard_user__fascard_user_account_id__in= scans_employees,
            timestamp__date__gte=self.start,
            timestamp__date__lte=self.end,
            slot__isnull=False,
            location__isnull=False,
        )
        q_values = bundles_queryset.values_list(
            'timestamp__date',
            'timestamp',
            'location__display_name',
            'slot__web_display_name',
            'slot__slot_fascard_id',
            'asset_code',
            'tech_employee__fascard_user__name',
        )
        scans_values = list(q_values)
        scans_values = self._append_extra_info(scans_values, 'scan')
        return scans_values

    def _load_transactions_data(self):
        self.queryset = self.queryset.exclude(laundry_room__isnull=True)
        tx_q_values = self.queryset.values_list(
            'local_transaction_date',
            'local_transaction_time',
            'laundry_room__display_name',
            'slot__web_display_name',
            'slot__slot_fascard_id',
            'machine__asset_code',
            'fascard_user__name',
        )
        transactions_values = list(tx_q_values)
        transactions_values = self._append_extra_info(transactions_values, 'transaction')
        return transactions_values

    def generate_dataset(self):
        """
        We have metrics on the date level and on the building level. 
        Date level Metrics:
            -Rooms visited
            -Hours worked from first swipe of the day until the last one
                -Include start and end time
            -Total travel time in between rooms
        -Building level Metrics:
            -Number of dryers started. x out of y.
            -Number of washers started. x out of y.
            -Total time in room
            -Time since previous room.
        """
        self.user_ids = self.queryset.values('fascard_user_id').distinct()
        #self.queryset = self.queryset.order_by('local_transaction_time')
        #TODO: Add extra Bundling status info
        transactions_values = self._load_transactions_data()
        scanning_values = self._load_scanning_data()
        self.pandas_df = self._load_pandas_dataframe(transactions_values+scanning_values)        
        self.dataset = {}
        employees = self.pandas_df.index.get_level_values('Employee').unique()
        for employee_name in employees:
            assert employee_name not in self.dataset
            self.dataset[employee_name] = {}
            employee_dates = self.pandas_df.loc[employee_name].index.get_level_values('Date').unique()
            self._process_employee(employee_name, employee_dates)
        if self.backend_processing:
            self.save_file()
        else:
            self.emailit()