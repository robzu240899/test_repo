'''
Created on Apr 20, 2017

@author: Thomas
'''
import os
import calendar
import csv
import logging
from collections import namedtuple
from datetime import timedelta
from platform import machine
from uuid import uuid1
from datetime import date
from dateutil.relativedelta import relativedelta
from decimal import Decimal
from tablib import Dataset
from django.db.models import Sum
from django.conf import settings
from main.settings import TEMP_DIR, DEFAULT_FROM_EMAIL
from main.utils import FieldExtractor
from reporting.enums import MetricType
from reporting.helpers import S3Upload
from reporting.models import LaundryRoomExtension, NonRecurrentExpense
from reporting.reliability.outoforder_report import NewBaseReport
from revenue.utils import LocationRefunds
from roommanager.models import LaundryRoom, MachineSlotMap, Machine
from roommanager.enums import MachineType
from revenue.models import RefundAuthorizationRequest, LaundryTransaction
from revenue.enums import RefundChannelChoices, TransactionTypeDisplay, TransactionType, AddValueSubType
from .config import RevenueConfig
from ...enums import LocationLevel, DurationType, InternalDerivedMetricCalcRule
from ...models import MetricsCache, BillingGroup
from ...helpers import Helpers


logger = logging.getLogger(__name__)


class InternalReportSetupException(Exception):
    pass


class RefundReport(NewBaseReport):
    dataset_title = 'Refunds Report'
    refund_request_fields = (
        'approved_by',
        'description',
        'created_by',
        'check_recipient',
        'additional_bonus_amount',
        'get_refund_type_choice_display'
    )
    refund_fields = (
        'amount',
        'timestamp',
        'get_refund_channel_display',
        'fascard_user_account_id',
        'transaction__fascard_user__name',
        'transaction__id',
        'transaction__assigned_laundry_room',
        'transaction__assigned_local_transaction_time',
    )
    dataset_headers = (
        'approver',
        'description',
        'requesitioner',
        'check_recipient',
        'additional_bonus_amount',
        'refund type',
        'amount',
        'refund req. datetime',
        'refund_channel',
        'fascard_user_account_id',
        'transaction__fascard_user__name',
        'transaction__id',
        'transaction__assigned_laundry_room',
        'transaction datetime',
        'transaction__type',
        'payment_method',
        'machine_number',
        'refund_file',
        'loyalty_account'
    )
    
    def extra_fields(self, refund):
        tx = refund.transaction
        tx_type = int(tx.transaction_type)
        tx_sub_type = int(tx.trans_sub_type)
        loyalty_url = ''
        try:
            type_repr = TransactionTypeDisplay.dict_repr[tx_type]
            type_display = type_repr.get('type')
            sub_type_display = type_repr.get('sub_types')[tx_sub_type]
            tx_type_display = f"{type_display} - {sub_type_display}"
        except KeyError:
            tx_type_display = 'Unknown'
        if getattr(tx, 'credit_card_amount') > 0 and getattr(tx, 'last_four'):
            if tx_type == TransactionType.ADD_VALUE and tx_sub_type == AddValueSubType.CREDIT_ON_WEBSITE:
                payment_method = 'Credit Card on Web App'
            else:
                payment_method = 'Direct - Credit Card'
        elif getattr(tx, 'balance_amount') > 0 and getattr(tx, 'loyalty_card_number'):
            payment_method = 'Loyalty Card'
        elif getattr(tx, 'cash_amount') > 0:
            if tx_type == TransactionType.ADD_VALUE and tx_sub_type == AddValueSubType.CASH:
                payment_method = 'Check to Office'
        else:
            payment_method = 'Unknown' 

        if tx.transaction_type == '100':
            machine_number = tx.slot.web_display_name
        else:
            machine_number = ''
        refund_file_url = ''
        if refund.refund_channel == RefundChannelChoices.CHECK:
            if refund.refund_file.storage.bucket_name and refund.refund_file.name:
                s3_handler = S3Upload(None, refund.refund_file.storage.bucket_name, refund.refund_file.name)
                refund_file_url = s3_handler.get_file_link()
        if getattr(tx, 'fascard_user') is not None and tx.fascard_user.fascard_user_account_id:
            loyalty_url = f"https://admin.fascard.com/86/loyaltyaccounts?recid={tx.fascard_user.fascard_user_account_id}"
        return [tx_type_display, payment_method, machine_number, refund_file_url, loyalty_url]

    def run(self, start_date, end_date, laundry_rooms=None):
        if laundry_rooms is None:
            laundry_rooms = LaundryRoom.objects.filter(is_active=True)
        for laundry_room in laundry_rooms:
            refund_requests = LocationRefunds(
                LocationLevel.LAUNDRY_ROOM,
                laundry_room.id,
                start_date,
                end_date
            ).get_refunds()
            for refund_request in refund_requests:
                base_refund_request = FieldExtractor.extract_fields(self.refund_request_fields, refund_request)
                refunds = refund_request.transaction.refunds.all()
                for refund in refunds:
                    row = []
                    row.extend(base_refund_request)
                    row.extend(FieldExtractor.extract_fields(self.refund_fields, refund))
                    row.extend(self.extra_fields(refund))
                    self.dataset.append(row)
        return self.dataset.export('csv')


class RefundMetricReport():
    basic_headers = (
        'Client Name',
    )

    def __init__(self):
        self.dataset = Dataset()
        self.dataset.title = 'Refunds Metrics Report'

    def set_headers(self, dates):
        headers = list(self.basic_headers)
        headers.extend(dates)
        self.dataset.headers = headers         

    def run(self, start_date, end_date, laundry_rooms=None):
        offset = 0
        dates = list()
        while start_date + relativedelta(months=offset) < end_date:
            dates.append(start_date+relativedelta(months=offset))
            offset +=1
        self.set_headers(dates)
        for laundry_room in laundry_rooms:
            row = [laundry_room.display_name]
            for dt in dates:
                room_revenue = MetricsCache.objects.filter(
                    location_id=laundry_room.id,
                    location_level=LocationLevel.LAUNDRY_ROOM,
                    metric_type=MetricType.REVENUE_FUNDS,
                    duration=DurationType.MONTH,
                    start_date=dt
                ).values('result').aggregate(result=Sum('result'))
                room_revenue_result = room_revenue.get('result')
                if room_revenue_result is None:
                    room_revenue_result = Decimal('0.0')
                end_of_month = date(dt.year, dt.month, calendar.monthrange(*tuple([dt.year, dt.month]))[1])
                q = refund_requests = LocationRefunds(
                   LocationLevel.LAUNDRY_ROOM,
                   laundry_room.id,
                   start_date,
                   end_date
                ).get_refunds()
                #extra filter
                q = q.filter(refund_channel__in=[RefundChannelChoices.AUTHORIZE, RefundChannelChoices.CHECK])
                refunds_amounts = q.values('refund_amount').aggregate(result=Sum('refund_amount'))
                refunds_amount_result = refunds_amounts.get('result')
                if refunds_amount_result is None:
                    refunds_amount_result = Decimal('0.0')
                val = room_revenue_result - refunds_amount_result
                row.append(val)
            self.dataset.append(row)
        return self.dataset.export('csv')


class NonRecurrentExpensesReport(NewBaseReport):
    dataset_title = 'Non-Recurrent Expenses Report'
    dataset_headers = (
        'laundry_room',
        'description',
        'amount',
        'created_by',
        'approved_by',
        'timestamp'
    )

    def run(self, room, start_date, end_date):
        queryset = NonRecurrentExpense.objects.filter(
            approved = True,
            laundry_room = room,
            timestamp__date__gte = start_date,
            timestamp__date__lte = end_date,
        )
        for expense in queryset:
            row = [getattr(expense, field) for field in self.dataset_headers]
            self.dataset.append(row)
        return self.dataset.export('csv')


class LocationManager():

    Location = namedtuple('Location', ['id','display_columns'])
    display_columns = None

    def __init__(self, billing_group_ids, laundry_room_ids, active_only, sort_parameter, start_date, end_date):
        self.billing_group_ids = billing_group_ids
        self.laundry_room_ids = laundry_room_ids
        self.active_only = active_only
        self.sort_parameter = sort_parameter
        self.start_date = start_date
        self.end_date = end_date

    def set_locations(self):
        raise NotImplementedError()

class BillingGroupManager(LocationManager):

    display_columns = ['Billing Group', 'Client Name']

    def set_locations(self):
        if self.billing_group_ids:
            billing_groups = BillingGroup.objects.filter(pk__in=self.billing_group_ids)
        else:
            billing_groups = BillingGroup.objects.all()
        if self.active_only:
            billing_groups = billing_groups.filter(is_active=True)
        self.locations = [self.Location(b.id,[b.display_name, b.get_client_name()]) for b in billing_groups]

class LaundryRoomManager(LocationManager):

    display_columns = ['Fascard Code', 'Laundry Room', 'Client Name']

    def set_locations(self):
        if self.laundry_room_ids:
            laundry_rooms = LaundryRoom.objects.filter(pk__in=self.laundry_room_ids)
        elif self.billing_group_ids:
            laundry_rooms = LaundryRoom.objects.filter(laundryroomextension__billing_group_id__in=self.billing_group_ids)
        else:
            laundry_rooms = LaundryRoom.objects.all()
        if self.active_only:
            laundry_rooms = laundry_rooms.filter(is_active=True)
        if self.sort_parameter:
            laundry_rooms = laundry_rooms.order_by(self.sort_parameter)
        #self.locations = [self.Location(l.id,[l.display_name, l.get_client_name()]) for l in laundry_rooms]
        self.locations = []
        for l in laundry_rooms:
            extension = l.laundryroomextension_set.all().first()
            try:
                client_name = extension.billing_group.get_client_name()
            except:
                client_name = None
            self.locations.append(self.Location(l.id,[l.fascard_code, l.display_name, client_name]))

class MachineManager(LocationManager):

    display_columns = ['Laundry Room', 'Machine Type', 'Fascard Mach #', 'Fascard machId', 'Asset Code', 'Description', 'URL']

    def set_locations(self):
        if self.laundry_room_ids:
            maps = MachineSlotMap.objects.filter(slot__laundry_room_id__in=self.laundry_room_ids).select_related('machine')
        elif self.billing_group_ids:
            maps = MachineSlotMap.objects.filter(slot__laundry_room__laundryroomextension__billing_group__in=self.billing_group_ids).select_related('machine')
        else:
            maps = MachineSlotMap.objects.filter(is_active=True).select_related('machine')
        maps = maps.exclude(end_time__lt=self.start_date)
        if self.active_only:
            maps = maps.filter(is_active=True, slot__is_active=True)
        self.locations = list()
        dashboard_url = settings.MAIN_DOMAIN
        admin_path = '/admin/roommanager/machine/{}/change/'
        #unique_machine_asset_codes = maps.values('machine__asset_code').distinct()
        machines = [mp.machine for mp in maps]
        machine_memory = []
        for machine in machines:
            if not machine: continue
            if machine.asset_code:
                if machine.asset_code in machine_memory: continue
                machine_memory.append(machine.asset_code)
            url = dashboard_url + admin_path.format(machine.id)
            associated_maps = maps.filter(machine=machine)
            slots = [mp.slot for mp in associated_maps]
            web_display_name = ' & '.join([slot.web_display_name for slot in slots])
            slot_ids_display = ' & '.join([slot.slot_fascard_id for slot in slots])
            descriptions = []
            for slot in slots:
                if getattr(slot, 'custom_description'): descriptions.append(getattr(slot, 'custom_description'))
            description = ' & '.join(descriptions)
            fields = [
                slots[0].laundry_room.display_name,
                machine.get_full_name(),
                #self._get_equipment_text(mp), 
                #mp.slot.web_display_name,
                web_display_name,
                slot_ids_display,
                machine.asset_code,
                description,
                url,
            ]
            loc = self.Location(machine.id, fields)
            self.locations.append(loc)
        # for mp in maps:
        #     if mp.machine.asset_code in maps_memory: continue
        #     maps_memory[mp.machine.asset_code] = mp
        #     url = dashboard_url + admin_path.format(mp.machine.id)
        #     fields = [
        #         mp.slot.laundry_room.display_name, 
        #         self._get_equipment_text(mp), 
        #         mp.slot.web_display_name, 
        #         mp.slot.slot_fascard_id, 
        #         mp.machine.asset_code,
        #         mp.machine.machine_description,
        #         url
        #     ]
        #     loc = self.Location(mp.machine.id, fields)
        #     self.locations.append(loc)
        # self.locations = [
        #    self.Location(mp.machine.id,
        #            [mp.slot.laundry_room.display_name, self._get_equipment_text(mp), mp.slot.web_display_name, mp.slot.slot_fascard_id, mp.machine.asset_code]) for mp in maps]


    def _get_equipment_text(self, msmap):
        try:
            return msmap.machine.get_full_name()
        except AttributeError as e:
            return "Equipment Type Not Specified"


class InternalReport():

    @classmethod
    def run(cls,metric_type,duration_type,start_date,end_date,
               location_level,laundry_room_ids,billing_group_ids,
               active_only,exclude_zero_rows,email,sort_parameter=None, delivery_method=None):
        data = cls._calc_data(metric_type,duration_type,start_date,end_date,
               location_level,laundry_room_ids,billing_group_ids,
               active_only,exclude_zero_rows,sort_parameter)
        if not delivery_method: delivery_method = 'email'
        r = cls._send_report(data,metric_type,start_date,email, delivery_method=delivery_method)
        return r


    @classmethod
    def _calc_data(cls,metric_type,duration_type,start_date,end_date,
               location_level,laundry_room_ids,billing_group_ids,
               active_only,exclude_zero_rows, sort_parameter):
        #Get location data in standardized form.  Also apply location filters
        params = [billing_group_ids, laundry_room_ids, active_only, sort_parameter, start_date, end_date]
        if location_level == LocationLevel.BILLING_GROUP: location_manager = BillingGroupManager(*params)
        elif location_level == LocationLevel.LAUNDRY_ROOM: location_manager = LaundryRoomManager(*params)
        elif location_level == LocationLevel.MACHINE: location_manager= MachineManager(*params)
        else: raise Exception("Unknown or unimplemented LocationLevel in InternalReport")
        location_manager.set_locations()
        #Get a list of dates we'll use in the report NB: a month has a date YYYY-MM-01. Year YYYY-01-01
        dates = []
        if duration_type == DurationType.DAY:
            dateformat = '%m/%d/%Y'
            for offset in range((end_date-start_date).days):
                dates.append(start_date+timedelta(days=offset))
        elif duration_type == DurationType.MONTH:
            dateformat = '%m/%Y'
            offset = 0
            while start_date + relativedelta(months=offset) < end_date:
                dates.append(start_date+relativedelta(months=offset))
                offset +=1
        elif duration_type == DurationType.YEAR:
            dateformat = '%Y'
            offset = 0
            while start_date + relativedelta(years=offset) < end_date:
                dates.append(start_date+relativedelta(years=offset))
                offset += 1
        else:
            raise InternalReportSetupException("Invalid/Unimplemented DurationType in internal report")
        data = []

        transactions_query = None
        #setup calculation headers
        if location_level == LocationLevel.LAUNDRY_ROOM:
            calculation_headers = []
            calculation_headers.append("Number Washers")
            calculation_headers.append("Number Dryers")
            calculation_headers.append("Transactions")
            #calculation_headers.append("Washer Pricing")
            #calculation_headers.append("Dryer Pricing")
            for metric_instruction in RevenueConfig.CALCULATED_METRICS:
                calculation_headers.append(metric_instruction.metric_name)
        elif location_level == LocationLevel.BILLING_GROUP:
            calculation_headers = Helpers.get_billinggroup_extra_headers()
        elif location_level == LocationLevel.MACHINE:
            calculation_headers = []
            calculation_headers.append("Transactions")
        else:
            calculation_headers = []
        #setup for date totals
        date_totals = {d:Decimal('0.00') for d in dates}
        #Get the revenue data and derived metrics
        for location in location_manager.locations:
            row = []
            base_metrics_query = MetricsCache.objects.filter(location_id=location.id,
                location_level=location_level,
                duration=duration_type,start_date__in=dates
            )
            metrics_qry = base_metrics_query.filter(metric_type=metric_type)
            if location_level == LocationLevel.MACHINE:
                metrics_result_total = metrics_qry.aggregate(total_sum=Sum('result'))
                try:
                    total_for_machine = metrics_result_total.get('total_sum')
                    if not total_for_machine: continue
                    if not total_for_machine > 0:
                        machine = Machine.objects.get(id=location.id)
                        if machine.placeholder: continue #exclude machines that are placeholders with zero revenue
                except Exception as e:
                    logger.info(f"Exception. metrics_result_total: {metrics_result_total}. MachineID: {location.id}")
                    raise Exception(e)
            transactions_query = base_metrics_query.filter(metric_type=MetricType.TRANSACTIONS_COUNT).values('result')
            transaction_count = transactions_query.aggregate(total_count=Sum('result')).get('total_count') or 0
            transaction_count = int(transaction_count)
            metrics = {m.start_date:m.result for m in metrics_qry}
            for dt in dates:
                try:
                    result = metrics[dt]
                    row.append(result)
                    date_totals[dt] += result or 0
                except KeyError:
                    row.append(None)
            total = sum([x for x in row if x])
            if exclude_zero_rows and not total:
                continue
            if location_level == LocationLevel.LAUNDRY_ROOM:
                room = LaundryRoom.objects.get(id=location.id)
                washers, dryers = Helpers.get_number_of_pockets(room)
                row.append(washers)
                row.append(dryers)
                row.append(transaction_count)
                #TODO: "Washer Pricing"
                #TODO: "Dryer Pricing"
                laundry_room_extension = LaundryRoomExtension.objects.filter(laundry_room_id=location.id).first()
                if not laundry_room_extension:
                    for metric_instruction in RevenueConfig.CALCULATED_METRICS:
                        row.append("Data Not Available: LaundryRoomExtension not set up.")
                else:
                    for metric_instruction in RevenueConfig.CALCULATED_METRICS:
                        data_point = getattr(laundry_room_extension,metric_instruction.column_name)
                        if data_point is None:
                            row.append('Unknown')
                        elif metric_instruction.calc_type == InternalDerivedMetricCalcRule.BOOLEAN:
                            if data_point == False:
                                row.append('No')
                            elif data_point == True:
                                row.append('Yes')
                        elif metric_instruction.calc_type == InternalDerivedMetricCalcRule.PLAIN:
                            row.append(data_point)
                        elif metric_instruction.calc_type == InternalDerivedMetricCalcRule.DIVIDE_BY_REVENUE:
                            try:
                                row.append(Decimal(metric_instruction.multiplier*total/Decimal(str(data_point))))
                            except ZeroDivisionError:
                                row.append('N/A')
            elif location_level == LocationLevel.BILLING_GROUP:
                bg = BillingGroup.objects.get(id=location.id)
                row.extend(Helpers.get_billing_group_concatenated_data(bg))
            elif location_level == LocationLevel.MACHINE:
                row.append(transaction_count)
            row.insert(0,total)
            row = location.display_columns + row
            data.append(row)

        headers = location_manager.display_columns + ['Total'] + [d.strftime(dateformat) for d in dates] + calculation_headers
        data.insert(0,headers)

        #Add total row
        grand_total = sum(date_totals.values())
        totals_row = ['Totals',grand_total]
        for _ in range(len(location_manager.display_columns)-1): totals_row.insert(1,'')  #Pads the totals row to account for the location name headers
        for dt in dates:
            totals_row.append(date_totals[dt])
        data.append(totals_row)

        for i in range(1,len(data)):
            for j in range(len(location.display_columns),len(dates)+2):
                data[i][j] = cls.to_dollars(data[i][j])

        return data

    @classmethod
    def _send_report(cls,data,metric_type,start_date,recipients, delivery_method='email'):
        subject = "Revenue Report for %s %s" % (start_date,metric_type)
        uid = str(uuid1())
        file_name = 'reveue_report_%s_%s_%s.csv' % (start_date,metric_type,uid)
        file_name = os.path.join(TEMP_DIR,file_name)
        data.insert(0,['-----'])
        data.insert(0,['Revenue Type',metric_type])
        data.insert(0,['Revenue Report'])
        with open(file_name,'w', encoding="utf-8") as f:
            writer = csv.writer(f)
            for row in data:    
                writer.writerow(row)
                #writer.writerow([str(s.encode("utf-8")) if type(s) == str else s for s in row])
            if metric_type == MetricType.FASCARD_REVENUE_FUNDS:
                writer.writerow(["NOTE: The metric includes Coin transactions"])
            f.close()
        if delivery_method == 'email':
            from django.core.mail import EmailMessage
            msg = EmailMessage(
                subject=subject,
                body="Revenue report is attached",
                from_email=DEFAULT_FROM_EMAIL,
                to=recipients.split(',')
            )
            with open(file_name) as f:
                attachment_name = 'reveue_report_%s_%s.csv' % (start_date,metric_type)
                msg.attach(attachment_name, f.read(), 'text/csv')
                msg.send(fail_silently=False)
                os.remove(file_name)
        elif delivery_method == 'download':
            return file_name

    @classmethod
    def to_dollars(cls,number):
        try:
            return "$" + "{:,}".format(number)
        except:
            return None
