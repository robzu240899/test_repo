import binascii
import csv
import calendar
import datetime
import decimal
import logging
import pandas as pd
import requests
import time
from api2pdf import Api2Pdf
from collections import namedtuple
from io import BytesIO
from decimal import Decimal
from typing import Dict
from zipfile import ZipFile
from dateutil.relativedelta import relativedelta
from django.core.files.base import ContentFile
from django.db.models import Q
from django.http import HttpResponse
from django.template.loader import get_template
from fascard.api import FascardApi
from main.utils import EmailExceptionClient
from reporting.enums import LocationLevel, MetricType, DurationType, ClientLowLevelReportType
from reporting.finance.internal.report import RefundReport, NonRecurrentExpensesReport
from reporting.metric.calculate import RevenueFunds
from reporting.models import LaundryRoomExtension, ClientReportFullStoredFile, \
ClientReportBasicStoredFile, tmp_storage, ExpenseType, BillingGroupExpenseTypeMap, NonRecurrentExpense, ClientRevenueReportJobInfo
from reporting.helpers import Helpers
from revenue.enums import TransactionType, AddValueSubType
from revenue.models import LaundryTransaction
from reporting.enums import ClientRentReportMetrics, BGSPaymentMethods, ExpenseType as ExpenseTypeEnums
from roommanager.models import LaundryRoom
from .expense_manager import ExpenseManager
from .revenuesplitter import RevenueSplitter
from .metricsfetcher import MetricsFetcher
from .mincomp import MinimumCompensationRule
from .owed import OwedCalculator

logger = logging.getLogger(__name__)

class ClientRevenueReport(object):
    API2_PDF_KEY = '6085a217-d26a-45f4-b3c5-cf68e1b6b9e7'
    REPORT_TEMPLATE_NAME = 'client_revenue_report.html'

    def __init__(self,billing_group,start_date,jobs_tracker=None, pdf_generation=False, html_generation=True, include_zero_rows=False, report_job_info_id=None):
        self.billing_group = billing_group
        self.start_date = start_date
        self.jobs_tracker = jobs_tracker
        self.raw_expenses, self.raw_passed_to_client_expenses = self._get_raw_expenses(self.billing_group)
        self.pdf_generation = pdf_generation
        self.html_generation = html_generation
        self.include_zero_rows = include_zero_rows
        self.api2pdf_client = Api2Pdf(self.API2_PDF_KEY)
        self.report_job_info_id = report_job_info_id
        self.total_applied = Decimal('0.00')
        logger.info(f"Got report job info id: {report_job_info_id}")

    @classmethod
    def _get_raw_expenses(cls, billing_group):
        expenses_types = ExpenseType.objects.all().order_by('display_name')
        raw_basic_expenses = []
        raw_passed_to_client_expenses = []
        for expense_type in expenses_types:
            expense = None
            try:
                expense =  BillingGroupExpenseTypeMap.objects.get(
                    billing_group=billing_group,
                    expense_type=expense_type
                )  
                expense_amount = expense.default_amount
            except:
                expense_amount = 0.0
            if expense and expense.pass_to_client:
                raw_passed_to_client_expenses.append({'expense_amount':expense_amount,'expense_type':expense_type})
            else:
                raw_basic_expenses.append({'expense_amount':expense_amount,'expense_type':expense_type})
        return raw_basic_expenses, raw_passed_to_client_expenses

    def _get_nonrecurrent_expenses(self):
        ExpenseTypeFake = namedtuple('ExpenseTypeFake', ['display_name','expense_type'])
        assert hasattr(self, 'start_date')
        end_date = datetime.date(
            self.start_date.year,
            self.start_date.month,
            calendar.monthrange(*tuple([self.start_date.year, self.start_date.month]))[1]
        )
        basic_expenses = []
        pass_to_client_expenses = []
        for laundry_extension in LaundryRoomExtension.objects.filter(billing_group = self.billing_group):
            laundry_room = laundry_extension.laundry_room
            queryset = NonRecurrentExpense.objects.filter(
                laundry_room = laundry_room,
                approved=True,
                timestamp__date__gte=self.start_date,
                timestamp__date__lte=end_date
            )
            for expense in queryset:
                expense_type_obj = ExpenseTypeFake(display_name=expense.expense_type, expense_type=ExpenseTypeEnums.STANDARD)
                data = {'expense_amount': expense.amount, 'expense_type': expense_type_obj}
                if expense.pass_to_client_share: pass_to_client_expenses.append(data)
                else: basic_expenses.append(data)
        return basic_expenses, pass_to_client_expenses

    def save_report_file(self, billing_group, filename, file_content, file_type):
        """
        Saves the report file for later processing by the jobs tracker
        """
        file_payload = {
            'billing_group' : billing_group,
            'file_type' : file_type,
            #'start_date_associated' : self.start_date
        }
        try:
            existing_report = ClientReportBasicStoredFile.objects.get(**file_payload)
        except:
            existing_report = False
        if existing_report:
            existing_report.report_file.delete()
            existing_report.delete()
        file_payload['jobs_tracker'] = self.jobs_tracker
        if self.report_job_info_id: file_payload['job_info'] = ClientRevenueReportJobInfo.objects.get(id=self.report_job_info_id)
        logger.info(f"creating ClientReportBasicStoredFile with payload: {file_payload}")
        report_file_object = ClientReportBasicStoredFile.objects.create(**file_payload)
        report_file_object.report_file.save(filename, ContentFile(file_content))
        logger.info(f"CREATED ClientReportBasicStoredFile (ID: {report_file_object.id}) with payload: {file_payload}")

    def _init_deductables(self):
        return {
            'expenses' : ['Expenses', 0],
            'total_refunds' : ['Total Refunds', 0],
            'client_share_premincomp' : ['Client Share Pre-min', 0],
            'prorating' : ['Prorating', False],
            'min_comp_applied' : ['Min Comp. Applied', False],
            'client_share_post_mincomp' : ['Client Share Post Min Comp', 0],
            'direct_client_expenses' : ['Direct Client Expenses', 0]
        }

    def _get_min_comp_rule(self, revenue_share, split_rule, days_in_effect):
        sub_client_share_premin = revenue_share.get('client_sub_share')
        sub_aces_share_premin = revenue_share.get('aces_sub_share')
        return MinimumCompensationRule(
            self.billing_group,
            split_rule,
            sub_aces_share_premin,
            sub_client_share_premin,
            days_in_effect
        )

    def _get_payees_share(self, client_share):
        payees_share = {}
        cents = decimal.Decimal('.01')
        #Split client share amoing client (billing_group) payees
        for payee in self.billing_group.payee_set.all():
            client_share_tmp = client_share.quantize(cents, decimal.ROUND_HALF_UP)
            value = (client_share_tmp / 100) * payee.percentage_share
            payees_share[payee.name] = value
        return payees_share

    def _compute_expenses(self, bg_metrics):
        assert hasattr(self, 'raw_expenses')
        expense_manager = ExpenseManager(self.raw_expenses, bg_metrics)
        expense_manager.process()
        return expense_manager.line_items, expense_manager.total

    def _get_revenue_split_data(self, splitter, deductables):
        revenue_shares = splitter.split_revenue()
        client_share_premin = sum([revenue_share.get('client_sub_share') for revenue_share in revenue_shares])
        aces_share_premin = sum([revenue_share.get('aces_sub_share') for revenue_share in revenue_shares])
        deductables['client_share_premincomp'][1] = client_share_premin
        client_share = Decimal('0.00')
        aces_share = Decimal('0.00')
        #shortfall = Decimal('0.00') #Default in case minimum compensation is not applied
        total_mincomp_rules_applied = Decimal('0')
        applied_min_comp_rules_map = []
        for revenue_share in revenue_shares:
            days_in_effect = revenue_share.get('days_in_effect')
            split_rule = revenue_share.get('split_rule')
            if not days_in_effect:
                days_in_effect = self.number_days
                if splitter.prorate:
                    days_in_effect = splitter.operations_days
                    self.start_date = splitter.operations_start
                    deductables['prorating'][1] = True
            min_comp_rule = self._get_min_comp_rule(revenue_share, split_rule, days_in_effect)
            min_comp_rule.calculate()
            if min_comp_rule.rule_applied:
                applied_rule_per_day = split_rule.min_comp_per_day or self.billing_group.min_compensation_per_day
                total_applied = Decimal(applied_rule_per_day) * Decimal(days_in_effect)
                applied_min_comp_rules_map.append({
                    'applied_rule_per_day' : applied_rule_per_day,
                    'days_in_effect' : days_in_effect,
                    'total': total_applied,
                    'resulting_client_share' : min_comp_rule.client_share_after_mincomp,
                    #'shortfall' : shortfall,
                    }
                )
                total_mincomp_rules_applied += total_applied
            client_share += min_comp_rule.client_share_after_mincomp
            aces_share += min_comp_rule.aces_share_after_mincomp
        if any(applied_min_comp_rules_map):
            is_mincomp_applied = True
            deductables['min_comp_applied'][1] = is_mincomp_applied
            #shortfall = total_applied - (client_share + aces_share)
        else:
            is_mincomp_applied = False
            #shortfall = Decimal('0.00')
        data = {
            'total_mincomp_rules_applied' : total_mincomp_rules_applied,
            'min_comp_per_day': applied_min_comp_rules_map,
            'client_share_premincomp': client_share_premin,
            'aces_share_premincomp': aces_share_premin,
            'aces_share': aces_share,
            'is_mincomp_applied': is_mincomp_applied,
            'client_share': client_share,
            #'shortfall': shortfall,
        }
        deductables['client_share_post_mincomp'][1] = client_share
        if deductables: data['deductables'] = deductables
        return data
      
    def process(self):
        #basic setup
        error = False
        if not self.billing_group.laundryroomextension_set.all():
            #raise Exception(f"The Billing Group {self.billing_group} is missing laundry room extensions")
            error = True
            return {}, f"The Billing Group {self.billing_group} is missing laundry room extensions"
        self.aces_collects_cash = self.billing_group.aces_collects_cash  #TODO: model change
        self.client_name = self.billing_group.display_name
        self.end_date = self.start_date + relativedelta(months=1)
        self.number_days = (self.end_date-self.start_date).days
        #Get gross revenue metrics.  NB Init takes care of all the calulations
        fetcher = MetricsFetcher(self.billing_group, self.start_date)
        laundry_room_gross_metrics = fetcher.laundry_room_data
        billing_group_gross_metrics = fetcher.totals
        deductables = self._init_deductables()
        #calculate expenses
        basic_nonrecurrent_expenses, pass_to_client_nonrecurrent_expenses = self._get_nonrecurrent_expenses()
        self.raw_expenses = self.raw_expenses + basic_nonrecurrent_expenses
        expense_line_items, expense_totals = self._compute_expenses(billing_group_gross_metrics['revenue_credit'])
        deductables['expenses'][1] = expense_totals
        #Calculate Net Revenue
        net = billing_group_gross_metrics['revenue'] - expense_totals #refunds already deducted in MetricsFetcher class

        #if self.billing_group.allow_cashflow_refunds_deduction:
            #total_refunds = Decimal('0.0')
            #for room in laundry_room_gross_metrics:
            #    total_refunds +=  laundry_room_gross_metrics[room]['total_refunds']
            #net = net - total_refunds
        total_refunds = billing_group_gross_metrics['total_refunds']
        deductables['total_refunds'][1] = total_refunds
        #Calculate Revenue Split
        splitter = RevenueSplitter(self.billing_group, net, self.start_date, billing_group_gross_metrics['previous_revenue'])
        revenue_data = self._get_revenue_split_data(splitter, deductables)
        payees_share = self._get_payees_share(revenue_data.get('client_share'))
        #How much is owed
        owed_amount, owed_text = OwedCalculator(
            revenue_data.get('client_share'),
            revenue_data.get('aces_share'),
            self.aces_collects_cash,
            billing_group_gross_metrics['revenue_cash'],
            self.client_name
        ).calculate()
        #Who collected the cash
        if self.aces_collects_cash: cash_collector = 'Aces'
        else: cash_collector = self.client_name
        #Subtract expenses passed to client
        total_non_recurrent = Decimal(sum([expense.get('expense_amount') for expense in pass_to_client_nonrecurrent_expenses]))
        nonrecurrent_expense_line_items = [(expense.get('expense_type').display_name, expense.get('expense_amount')) for expense in pass_to_client_nonrecurrent_expenses]
        total_recurrent = Decimal(sum([expense.get('expense_amount') for expense in self.raw_passed_to_client_expenses])) 
        owed_amount = owed_amount - (total_non_recurrent+total_recurrent)
        #format data
        display_end_date = self.end_date - relativedelta(days=1)
        crc32_hash = binascii.crc32(f"{self.billing_group.id},{self.start_date}".encode("utf-8"))
        lessee = getattr(self.billing_group.lessee, 'name', None) or 'ACES LAUNDRY SERVICES LLC'
        data = {
            'lessee' : lessee,
            'client_name': self.client_name,
            'vendor_code': self.billing_group.vendor_code,
            'invoice_number' : '%08X' % crc32_hash,
            'start_date':self.start_date.strftime('%b %d, %Y'),
            'end_date':display_end_date.strftime('%b %d, %Y'),
            'laundry_room_gross': laundry_room_gross_metrics,
            'billing_group_gross': billing_group_gross_metrics,
            'expense_line_items': expense_line_items,
            'nonrecurrent_expenses_passed_to_client': total_non_recurrent,
            'nonrecurrent_expenses_line_items' : nonrecurrent_expense_line_items,
            'recurrent_expenses_passed_to_client': total_recurrent,
            'expense_totals': expense_totals,
            'total_refunds': total_refunds,
            'net': net,
            'payees_share': payees_share,
            'aces_owes_client': owed_amount,
            'client_owes_aces': owed_amount*-1,
            'owed_text': owed_text,
            'cash_collector': cash_collector,
            'aces_collects_cash': self.billing_group.aces_collects_cash,
            }
        if splitter.prorate:
            data.update(
                {
                    'prorate':splitter.prorate, 
                    'prorate_factor': f"{splitter.operations_days}/{splitter.days_in_month}",
                    'base_rent' : splitter.base_rent
                }
            )
        if revenue_data: data.update(revenue_data)        
        return data, error

    def _get_filename(self, file_type, file_data):
        filename = ''
        try: largest_loc_fascard_id = max([ext.laundry_room.fascard_code for ext in self.billing_group.laundryroomextension_set.all() if ext.laundry_room])
        except: largest_loc_fascard_id = 0
        largest_loc_fascard_id = str(largest_loc_fascard_id)
        largest_laundry_room_fascard_code = max(LaundryRoom.objects.all().values_list('fascard_code', flat=True))
        largest_loc_fascard_id = largest_loc_fascard_id.zfill(len(str(largest_laundry_room_fascard_code)))
        filename += "{}/{}-{:02d}/{}-{} client revenue report - {}.{}".format(
            self.billing_group,
            self.start_date.year,
            self.start_date.month,
            largest_loc_fascard_id,
            self.start_date.strftime("%Y-%m").upper(),
            self.billing_group,
            file_type
        )
        if file_data['aces_owes_client'] > 0:
            prepend_dir = 'Aces Owes Client'
            if self.billing_group.payment_method != BGSPaymentMethods.UNKNOWN:
                prepend_dir += f'/{self.billing_group.payment_method}'
        elif file_data['client_owes_aces'] > 0:
            prepend_dir = 'Client Owes Aces'
        else:
            prepend_dir = 'No Money Owed'
        filename = '/'.join([prepend_dir, filename])
        return filename

    def _accounts_payable_tracking(self, report_job_info_id, invoice_amount):
        report_job_info = ClientRevenueReportJobInfo.objects.get(id=report_job_info_id)
        report_job_info.fully_processed = True
        report_job_info.invoice_amount = invoice_amount
        report_job_info.save()

    def _generate_pdf(self, binary_data, html_response):
        api_response = self.api2pdf_client.HeadlessChrome.convert_from_html(str(html_response, 'utf-8'))
        pdf_url = api_response.result.get('pdf')
        if pdf_url:
            r = requests.get(pdf_url, stream=True)
            temp_result = BytesIO()
            chunk_size = 2000 #bytes
            for chunk in r.iter_content(chunk_size):
                temp_result.write(chunk)
            binary_data['pdf'] = temp_result.getvalue()
        else:
            logger.info('API2PDF Failed creating PDF Client revenue report file for BG: {}'.format(self.billing_group))            
        #css = CSS(string='@page { size: Letter; margin: 0in 0.44in 0.2in 0.44in;}')
        #binary_data['pdf'] = HTML(string=str(html_response, 'utf-8')).write_pdf(stylesheets=[css])            
        logger.info("Successfully generated a PDF")
        return binary_data

    def _track_error(self, error_str):
        job_info = ClientRevenueReportJobInfo.objects.get(id=self.report_job_info_id)
        job_info.errored = True
        job_info.error = error_str
        job_info.save()

    def create(self):
        try: data, error = self.process()
        except Exception as e: error = f"Report for billing group {self.billing_group} failed with exception {e}"
        if error:
            self._track_error(error)
            return "Success"
        data['include_zero_rows'] = self.include_zero_rows
        template = get_template(self.REPORT_TEMPLATE_NAME)
        html_response = template.render(data).encode(encoding='UTF-8')
        html_binary_data = BytesIO(html_response)
        binary_data = {'html' : html_binary_data.getvalue()}
        if self.pdf_generation: binary_data = self._generate_pdf(binary_data, html_response)
        if not self.html_generation: binary_data.pop('html')
        for file_type in binary_data.keys():
            filename = ''
            filename = self._get_filename(file_type, data)
            try:
                self.save_report_file(
                    self.billing_group, 
                    filename, 
                    binary_data.get(file_type),
                    file_type
                )
                if self.report_job_info_id: self._accounts_payable_tracking(self.report_job_info_id, data['aces_owes_client'])
            except Exception as e:
                err = 'Saving file: {} failed with exception: {}'.format(filename, e)
                logger.info(err)
                raise Exception(e)
        return "Success"


class ClientNetRentReport():
    dataset_title = 'Client Rent Report'
    dataset_headers = (
        'Client Name',
        'Billing Group',
        'Rent Paid'
    )
    extension_fields = (
        'building_type',
        'legal_structure',
        'has_elevator',
        'is_outdoors',
        'laundry_in_unit'
    )

    def __init__(self, billing_groups, start_date, end_date, metric):
        super(ClientNetRentReport, self).__init__()
        self.billing_groups = billing_groups
        self.start_date = start_date
        self.end_date = end_date
        self.metric_type = metric

    def _generate_csv(self):
        file_name = 'RentReport_{}.csv'.format(datetime.datetime.now())
        with open(file_name,'w', encoding="utf-8") as f:
            writer = csv.writer(f)
            for row in self.data:
                writer.writerow(row)
        return file_name

    def totals_append(self, i, val):
        assert hasattr(self, 'totals')
        try:
            self.totals[i]
        except IndexError:
            self.totals.insert(i, 0)
        self.totals[i] = self.totals[i] + val

    def extract_metric(self, report_data: Dict):
        client_share = report_data.get('client_share_premincomp')
        if report_data.get('is_mincomp_applied'):
            client_share = report_data.get('client_share')
        net = report_data.get('net')
        if self.metric_type == ClientRentReportMetrics.CLIENT_SHARE:
            metric = client_share
        elif self.metric_type == ClientRentReportMetrics.RENT_PERCENTAGE_REVENUE:
            if client_share > 0 and net > 0:
                metric = (client_share * 100) / net
            else:
                metric = Decimal('0.0')
        elif self.metric_type == ClientRentReportMetrics.ACESNET_AFTER_RENT:
            metric = net - client_share
        elif self.metric_type == ClientRentReportMetrics.ACESNET_PERCENTAGE_REVENUE:
            aces_net = net - client_share
            if aces_net > 0 and net > 0:
                metric = (aces_net / net) * 100
            else:
                metric = Decimal('0.0')
        return metric

    def run(self):
        owed = 0
        self.data = [['Client Name', 'Billing Group']]
        self.totals = []
        start_date = self.start_date
        end_date = self.end_date
        self.nets = []
        self.aces_nets = []
        self.client_shares = []
        self.total_units = 0
        self.total_washers = 0
        self.total_dryers = 0
        for billing_group in self.billing_groups:
            bg_client = billing_group.client
            bg_client_name = getattr(bg_client, 'name', None)
            row = [bg_client_name, getattr(billing_group, 'display_name', None)]
            start_date = self.start_date
            end_date = self.end_date
            i = 0
            while start_date <= end_date:
                if start_date not in self.data[0]:
                    self.data[0].append(start_date)
                ins = ClientRevenueReport(billing_group, start_date)
                report_data, errors = ins.process()
                metric = self.extract_metric(report_data)
                if not metric: metric = 0
                owed += metric
                row.append('%.2f' % metric)
                client_share = report_data.get('client_share_premincomp')
                if report_data.get('is_mincomp_applied'):
                    client_share = report_data.get('client_share')
                net = report_data.get('net')
                if self.metric_type == ClientRentReportMetrics.RENT_PERCENTAGE_REVENUE:
                    try:
                        self.nets[i]
                    except IndexError:
                        self.nets.insert(i, 0)
                    try:
                        self.client_shares[i]
                    except IndexError:
                        self.client_shares.insert(i, 0)
                    self.nets[i] += net
                    self.client_shares[i] += client_share
                elif self.metric_type == ClientRentReportMetrics.ACESNET_PERCENTAGE_REVENUE:
                    try:
                        self.nets[i]
                    except IndexError:
                        self.nets.insert(i, 0)
                    try:
                        self.aces_nets[i]
                    except IndexError:
                        self.aces_nets.insert(i, 0)
                    self.aces_nets[i] += net - client_share
                    self.nets[i] += net
                else:
                    self.totals_append(i, metric)
                start_date = start_date + relativedelta(months=1)
                i+=1
            #extra bg data
            extra_data = Helpers.get_billing_group_concatenated_data(billing_group)
            self.total_units += extra_data[0]
            self.total_washers += extra_data[1]
            self.total_dryers += extra_data[2]
            row.extend(extra_data)
            self.data.append(row)
        self.data[0].extend(Helpers.get_billinggroup_extra_headers())
        title = ClientRentReportMetrics.CHOICES_DICT.get(self.metric_type)
        self.data.insert(0, [title])
        totals_row = ['', 'Total']
        if self.metric_type == ClientRentReportMetrics.RENT_PERCENTAGE_REVENUE:
            assert len(self.nets) == len(self.client_shares)
            totals_row.extend(['%.2f' % ((total_client_share/total_net)*100) for total_net, total_client_share in zip(self.nets, self.client_shares)])
        elif self.metric_type == ClientRentReportMetrics.ACESNET_PERCENTAGE_REVENUE:
            assert len(self.nets) == len(self.aces_nets)
            totals_row.extend(['%.2f' % ((total_aces_share/total_net)*100) for total_net, total_aces_share in zip(self.nets, self.aces_nets)])
        else:
            totals_row.extend(['%.2f' % val for val in self.totals])
        totals_row.extend([self.total_units, self.total_washers, self.total_dryers])
        self.data.append(totals_row)
        return self._generate_csv()


class RevenueFundsCustom(RevenueFunds):
    read_fields = (
        'assigned_local_transaction_time',
        'trans_sub_type',
        'cash_amount',
        'credit_card_amount',
        'balance_amount',
        'bonus_amount',
        'transaction_type',
        'loyalty_card_number',
        'external_fascard_user_id',
        'card_number',
        'dirty_name',
        'slot__web_display_name',
    )
    custom_filters = [~Q(cash_amount=0) | 
        ~Q(credit_card_amount=0) |
        (~Q(balance_amount=0) & Q(transaction_type=100)) |
        (~Q(bonus_amount=0) & Q(transaction_type=100))
    ]

    def process(self):
        self.qryset=LaundryTransaction.objects.all()
        for standard_filter in self.standard_filters:
            self.qryset = self.qryset.filter(standard_filter)
        for transaction_type_filter in self.transaction_type_filters:
            self.qryset = self.qryset.filter(transaction_type_filter)
        for custom_filter in self.custom_filters:
            self.qryset = self.qryset.filter(custom_filter)
        self.qryset = self.time_manager.apply_time_filter(self.qryset)
        self.qryset = self.location_manager.apply_location_filter(self.qryset)
        self.qryset = self.qryset.values(*self.read_fields)
        return self.qryset


class ClientRevenueFullReport():
    """
    A class to create a comprehensive low-level client revenue report.

    Attributes:
        dataframe_fields (tuple): A map to rename django model fields to readable strings
                                  and include only the listed fields in the final dataframe to be exported

        value_add_map (dict): A map for converting transaction types, which are stored as integers, to readable strings.

    Constructor Attributes:
        end_date (datetime): defaults to one month after the starting date

        number_days (int): total days in date range of the report.    

    Parameters:
        start_date (datetime): the starting date for the report

        billing_group (reporting.models.BillingGroup): The reports for a client are created on a per-billing-group basis.
        Every billing group may has multiple laundry rooms attached to it.

        jobs_tracker (reporting.models.ClientRevenueFullJobsTracker): For easier processing, a requested report is splitted into
        multiple small jobs, one for every billing group. The JobsTracker keeps track of them until all the small jobs are
        finished processing


    """
    location_type = LocationLevel.LAUNDRY_ROOM
    dataframe_fields = (
        ('assigned_local_transaction_time','Date & Time'),
        ('transaction_type','Transaction Type'),
        ('cash_amount','Cash Amount'),
        ('credit_card_amount','Credit Card Amount'),
        ('check_amount','Check Amount'),
        ('balance_amount', 'Balance Amount'),
        ('bonus_amount', 'Bonus Amount'),
        ('credit_card_info','Credit Card Info'),
        ('loyalty_card_number','Loyalty Card'),
        ('external_fascard_user_id','Account ID'),
        ('slot__web_display_name', 'Machine No'),
        ('name','Account Name')
    )
    value_add_map = {
        0:'Credit Card in Room',
        1:'Credit Card Via Web & App',
        2:'Via Check',
        3:'Auto Reload' #throw error
    }

    def __init__(self, billing_group, start_date, jobs_tracker, requestor_email=None, **kwargs):
        self.start_date = start_date
        self.end_report_date = self.start_date + relativedelta(months=1)
        self.billing_group = billing_group
        self.jobs_tracker = jobs_tracker
        self.number_days = (self.end_report_date-self.start_date).days
        self.requestor_email = requestor_email
        for k,v in kwargs.items(): setattr(self, k, v)

    def clean_records(self, records, laundry_group):
        """
        Calls all the data cleaning functions for each record in parameter records

        Parameters:
            records (list): A list of all the records to process for the report being generated.
            
            laundry_group (roommanager.models.LaundryGroup): the laundry group to which the 
            laundry room in the transaction record belongs

        Returns:
            records_list (list): A list with all the records cleaned for further processing in pandas Dataframe

        """
        records_list = []
        for record in records:
            #if int(record['external_fascard_user_id']) != 0:
            #    record = self.add_person_name(record, laundry_group)
            #else:
            record['name'] = ''
            records_list.append(record)
        records_list = list(map(self.format_date, iter(records_list)))
        records_list = list(map(self.add_check_amount, iter(records_list)))
        records_list = list(map(self.replace_transactiontype_label, iter(records_list)))
        records_list = list(map(self.merge_creditcard_info, iter(records_list)))
        return records_list

    def add_person_name(self, record, laundry_group):
        """
        Retrieve info from the API of the person who owns the loyalty account and modifies
        the current record to add the person's name

        Parameters:
            record (dict): current transanction record being processed.
            
            laundry_group (roomanager.LaundryGroup): the laundry group to which the 
            laundry room in the transaction record belongs

        Returns:

            record(dict): The record dict with the person's name, if existing, added to it.

        """
        record['name'] = ''
        try:
            user = record.fascard_user
            if user: record['name'] = record.fascard_user.name
        except:
            pass
        return record

    def add_check_amount(self, record):
        """
        Detects whether the current transaction was paid with a check, gets the check value from cash_amount, add it
        to a new item in the dict with key check_amount and sets cash_amount to zero.
        
        Parameters:
            record (dict): current transanction record being processed.

        Returns:

            record(dict): The record dict with the item check_amount, if that's the case, added to it.

        """
        transaction_type = int(record['transaction_type'])
        trans_sub_type = int(record['trans_sub_type'])
        record['check_amount'] = 0
        if transaction_type == TransactionType.ADD_VALUE and trans_sub_type == AddValueSubType.CASH:
            check_amount = record['cash_amount']
            record['check_amount'] = check_amount
            record['cash_amount'] = 0
        return record

    def replace_transactiontype_label(self, record):
        """
        Maps transaction type number to a readable string. Uses attribute valued_add_map

        Parameters:
            record (dict): current transanction record being processed.

        Returns:
            record (dict): returns the record dictionary with the value of key transaction_type changedto
            a readable string

        """
        transaction_type = int(record['transaction_type'])
        trans_sub_type = int(record['trans_sub_type'])
        if transaction_type == TransactionType.ADD_VALUE:
            if trans_sub_type == 0 and record['cash_amount'] > 0:
                label = 'Added Value - Cash at Kiosk'
            else:
                label = 'Added Value - {}'.format(self.value_add_map[trans_sub_type])
        elif transaction_type == TransactionType.VEND:
            label = 'Started Machine'
        record['transaction_type'] = label
        return record

    def merge_creditcard_info(self, record):
        """
        Merges the items with keys card_number and dirty_name in record into a single item named credit_card_info

        Parameters:
            record (dict): current transanction record being processed.

        Returns:
            record (dict): returns the record dictionary with a new item with key credit_card_info 

        """
        label = '{} {}'.format(record.get('card_number'), record.get('dirty_name'))
        record['credit_card_info'] = label
        return record

    def format_date(self, record):
        """
        Applies custom date format to the value of key assigned_local_transaction_time in the record

        Parameters:
            record (dict): current transanction record being processed.

        """
        current_date = record['assigned_local_transaction_time']
        record['assigned_local_transaction_time'] = current_date.strftime("%Y-%m-%d %I:%M %p")
        return record

    def get_filename(self, report_name, laundry_room):
        filename = ''
        #if self.billing_group.client:
        #    filename += '{}/'.format(self.billing_group.client)
        filename += "{}/{}-{:02d}/{} {} -- {}.csv".format(
            self.billing_group,
            self.start_date.year,
            self.start_date.month,
            self.start_date.strftime("%Y-%m").upper(),
            report_name,
            laundry_room
        )
        return filename

    def save_report_file(self, laundry_extension, filename, csv_string, report_type):
        """
        Saves the report as a CSV file outputted by pandas using the custom Model ClientReportFullStoredFile.
        """
        # try:
        #     existing_report = ClientReportFullStoredFile.objects.get(
        #         laundry_room_extension = laundry_extension,
        #         report_type = report_type)
        # except:
        #     existing_report = False
        # if existing_report:
        #     existing_report.report_file.delete()
        #     existing_report.delete()
        report_file_object = ClientReportFullStoredFile.objects.create(
            laundry_room_extension = laundry_extension,
            report_type=report_type,
            jobs_tracker=self.jobs_tracker)
        report_file_object.report_file.save(filename, ContentFile(bytes(csv_string.encode("utf-8"))))

    def refunded_transactions(self, room_ext):
        room = room_ext.laundry_room
        filename = self.get_filename('refunded transactions', room)
        csv_string = RefundReport().run(
            start_date=self.start_date,
            end_date=self.end_report_date,
            laundry_rooms = [room],
        )
        try:
            self.save_report_file(
                room_ext,
                filename,
                csv_string,
                ClientLowLevelReportType.REFUNDS
            )
            logger.info("File Saved in S3 with name: {}".format(filename))
        except Exception as e:
            err = 'Saving file: {} failed with exception: {}'.format(filename, e)
            logger.info(err)
            raise Exception(e)

    def nonrecurrent_expenses(self, room_ext):
        room = room_ext.laundry_room
        csv_string = NonRecurrentExpensesReport().run(room, self.start_date, self.end_report_date)
        filename = self.get_filename('non-recurrent expenses', room)
        try:
            self.save_report_file(
                room_ext,
                filename,
                csv_string,
                ClientLowLevelReportType.NON_RECURRENT_EXPENSES
            )
            logger.info("File Saved in S3 with name: {}".format(filename))
        except Exception as e:
            err = 'Saving file: {} failed with exception: {}'.format(filename, e)
            logger.info(err)
            raise Exception(e)

    def _handle_failure(self, room_ext: LaundryRoomExtension, exception: Exception):
        """
        If report generation fails we call this method to generate a txt file with the exception. This file fakes the existence
        of an actual report and allows the entire batch to keep moving and eventually send a zip file with reports that were processed
        successfully and txt files for those that failed.
        """
        try:
            subject = f"Failed creating a full low-level report for {room_ext}"
            error = f"There was an error processing {room_ext}: {exception}"
            email = EmailExceptionClient(**{'subject': subject, 'to': self.requestor_email, 'body': error})
            email.send()
        except Exception as e:
            logger.error(e)
            pass
        filename = self.get_filename('ERROR', room_ext.laundry_room)
        try:
            self.save_report_file(
                room_ext,
                filename,
                f"There was an error processing {room_ext}: {exception}",
                ClientLowLevelReportType.ERROR
            )
            logger.info("File Saved in S3 with name: {}".format(filename))
        except Exception as e:
            err = 'Saving file: {} failed with exception: {}'.format(filename, e)
            logger.info(err)
            raise Exception(e)


    def _fetch_revenue_data(self, laundry_room, laundry_group):
        days_left = self.number_days
        laundry_room_data_array = []
        next_start_date = self.start_date
        for day in range(days_left):
            daily_revenue_funds = RevenueFundsCustom(
                location_type = self.location_type,
                location_id = laundry_room.id,
                duration = DurationType.DAY,
                start_date=next_start_date
            ).process()
            daily_revenue_funds = self.clean_records(daily_revenue_funds, laundry_group)
            laundry_room_data_array.extend(list(daily_revenue_funds))
            next_start_date = next_start_date + relativedelta(days=1)
        return laundry_room_data_array

    def _create_report(self, laundry_extension):
        logger.info("Running low-level report for Laundry Extension: {}".format(laundry_extension))
        start = time.time()
        laundry_room = laundry_extension.laundry_room
        laundry_group = laundry_room.laundry_group
        laundry_room_data_array = self._fetch_revenue_data(laundry_room, laundry_group)
        end = time.time()
        logger.info(f"Fetching revenue data for Laundry Extension {laundry_extension} took: {end-start} seconds")
        if len(laundry_room_data_array) > 0:
            start = time.time()
            laundry_room_df = pd.DataFrame(laundry_room_data_array)
            sum_row = {
                col: laundry_room_df[col].sum()
                for col in ['cash_amount','credit_card_amount', 'check_amount', 'balance_amount', 'bonus_amount']
            }
            sum_df = pd.DataFrame(sum_row, index=["Total"])
            laundry_room_df = laundry_room_df.append(sum_df, sort=False)
            laundry_room_df = laundry_room_df[[x[0] for x in self.dataframe_fields]] #re-order dataframe
            laundry_room_df.loc[laundry_room_df['external_fascard_user_id'] == 0, 'external_fascard_user_id'] = ''
            laundry_room_df['cash_amount'] = laundry_room_df['cash_amount'].map('${:,.2f}'.format)
            laundry_room_df['credit_card_amount'] = laundry_room_df['credit_card_amount'].map('${:,.2f}'.format)
            laundry_room_df['check_amount'] = laundry_room_df['check_amount'].map('${:,.2f}'.format)
            laundry_room_df['balance_amount'] = laundry_room_df['balance_amount'].map('${:,.2f}'.format)
            laundry_room_df['bonus_amount'] = laundry_room_df['bonus_amount'].map('${:,.2f}'.format)
            columns_dict = {}
            g = lambda field: columns_dict.update({field[0]:field[1]})
            for field in self.dataframe_fields:
                g(field)
            laundry_room_df = laundry_room_df.rename(columns=columns_dict)
            laundry_room_df = laundry_room_df.set_index('Date & Time')
            laundry_room_df.index = laundry_room_df.index.fillna('Total')
            filename = self.get_filename('transactions report', laundry_room)
            csv_string = laundry_room_df.to_csv(encoding='utf-8')
            end = time.time()
            logger.info(f"Processinf file data for Laundry Extension {laundry_extension} took: {end-start} seconds")
            try:
                self.save_report_file(
                    laundry_extension,
                    filename,
                    csv_string,
                    ClientLowLevelReportType.TRANSACTIONS
                )
                logger.info("File Saved in S3 with name: {}".format(filename))
                print ("File Saved in S3 with name: {}".format(filename))
            except Exception as e:
                err = 'Saving file: {} failed with exception: {}'.format(filename, e)
                logger.info(err)
                raise Exception(e)
        else:
            err = '{} has no revenue data: {}'.format(laundry_extension, laundry_room_data_array)
            logger.info(err)
        #Add refunded transactions report for the final zip file
        start = time.time()
        self.refunded_transactions(laundry_extension)
        end = time.time()
        logger.info(f"Processing refunded_transactions for Laundry Extension {laundry_extension} took: {end-start} seconds")
        #Add non-recurrent expenses report for the final zip file
        start = time.time()
        self.nonrecurrent_expenses(laundry_extension)
        end = time.time()
        logger.info(f"Processing nonrecurrent_expenses for Laundry Extension {laundry_extension} took: {end-start} seconds")


    def create(self):
        days_left = self.number_days
        total_start = time.time()
        for laundry_extension in LaundryRoomExtension.objects.filter(billing_group=self.billing_group):
            try:
                self._create_report(laundry_extension)
            except Exception as e:
                subject = f'Failed creating low-level report for laundry room ext: {laundry_extension}'
                body_str = f'An exception ocurred while processing the full low-level report: {e}'
                self._handle_failure(laundry_extension, e)
        total_end = time.time()
        logger.info(f"Billing group {self.billing_group} total exec time {total_end - total_start}")
        return "Success"
        #in_memory.seek(0)
        #return in_memory.read()
        #response = HttpResponse(content_type="application/zip")
        #response["Content-Disposition"] = "attachment; filename=reportfiles.zip"
        #in_memory.seek(0)
        #response.write(in_memory.read())
        #return response

            #hallar la forma de agregar todos los records al DF


            #Use dates as Index
        #call LaundryTransaction table for credit card transaction (Type 100)
        #Type 2 transactions:
        #class LaundryTransaction table for cash at kiosk. Subtype: 0
        #class LaundryTransaction table for website value add. Subtype: 1
        #Remember that even though the value adds are attributed to the laundry room
        #they do not show up like that in Fascard's report
