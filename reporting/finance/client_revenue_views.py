import calendar
import os
import logging
from copy import deepcopy
from datetime import datetime, date
from dateutil.relativedelta import relativedelta
from django.db.models import Q
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.utils.decorators import method_decorator
from django.views.generic import View
from django.views.decorators.csrf import  csrf_exempt
from django.forms import formset_factory
from django import forms
from django.core.exceptions import ValidationError, PermissionDenied
from django.utils.translation import gettext as _
from django.core.mail import EmailMessage
from django.template.loader import render_to_string
from django.template.defaultfilters import slugify
from queuehandler.job_creator import ClientRevenueFullReportEnqueuer, ClientRevenueFullJobsTrackerEnqueuer, \
                        ClientRevenueReportEnqueuer, ClientRevenueJobsTrackerEnqueuer
from main import settings
from ..models import BillingGroup, ExpenseType, BillingGroupExpenseTypeMap, \
        ClientRevenueFullReportJobInfo, ClientRevenueFullJobsTracker, ClientRevenueJobsTracker, ClientRevenueReportJobInfo
from queuehandler.utils import Aurora
from rest_framework.response import Response
from rest_framework import permissions, authentication, views, status 
from reporting.threads import ClientNetRentReportThread
from reporting.enums import ClientRentReportMetrics, LocationLevel, MetricType, DurationType
from reporting.finance.forms import BillingGroupSelectionForm, MultipleBillingGroupSelectionForm, ClientRevenueReportForm, CustomDateInput, \
RentReportForm, ExpenseForm, ClientFullLowLevelReportForm
from reporting.finance.clientreport.report import ClientRevenueReport, ClientRevenueFullReport, ClientNetRentReport
from reporting.finance.internal.report import InternalReport
from reporting.models import MetricsCache
from revenue.models import FascardUser
from roommanager.models import LaundryRoom
from .mixins import ClientRevenueMixin

logger = logging.getLogger(__name__)


class BillingGroupSelectorClientRevenueReport(View):

    @method_decorator(login_required)
    def get(self,request):
        request.session['client_report_data'] = {}
        billing_group_form = BillingGroupSelectionForm()

        return render(request,"billing_group_selector.html",{"data_form":billing_group_form})

    @method_decorator(login_required)
    def post(self,request):
        billing_group_form = BillingGroupSelectionForm(request.POST)
        if billing_group_form.is_valid():

            #place inputed data into session
            billing_group = billing_group_form.cleaned_data["billing_group"]
            year = billing_group_form.cleaned_data["year"]
            month = billing_group_form.cleaned_data["month"]
            dt = date(year,month,1)
            request.session['client_report_billing_group_id'] = billing_group.id
            request.session['client_report_year'] = year
            request.session['client_report_month'] = month

            expenses_types = ExpenseType.objects.all().order_by('display_name')
            ExpenseFormSet = formset_factory(ExpenseForm, extra=0)
            initial = []
            for expense_type in expenses_types:
                try:
                    expense_amount =  BillingGroupExpenseTypeMap.objects.get(billing_group=billing_group,expense_type=expense_type).default_amount
                except:
                    expense_amount = 0.0
                initial.append({'expense_amount':expense_amount,'expense_type':expense_type})
            expense_form_set = ExpenseFormSet(initial=initial)
            return render(request,"expenses.html",{'expense_form_set':expense_form_set})
        else:
            return render(request,"billing_group_selector.html",{"data_form":billing_group_form})

class ExpensesClientRevenueReport(View):

    @method_decorator(login_required)
    def post(self,request):
        ExpenseFormSet = formset_factory(ExpenseForm)
        expense_form_set = ExpenseFormSet(request.POST)
        if expense_form_set.is_valid():
            month = request.session['client_report_month']
            year = request.session['client_report_year']
            dt = date(year,month,1)
            billing_group = BillingGroup.objects.get(pk=request.session['client_report_billing_group_id'])
            #expenses = [f.cleaned_data for f in expense_form_set.forms]
            report = ClientRevenueReport(billing_group=billing_group,
                                         #raw_expenses=expenses, #TODO, remove aces collects cash everywhere
                                         start_date=dt
                                         )

            #########
            report_data, errored = report.process()
            msg_body = "See attached report."

            txt = render_to_string("client_revenue_report.html",report_data,request)
            txt = txt.encode(encoding='UTF-8')
            dt = datetime.now().strftime('%y_%m_%d_%H_%M_%S')
            file_name = os.path.join(settings.TEMP_DIR, slugify("Client_Revenue_Report_%s_%s" % (report_data['client_name'],dt)) )
            file_name += '.html'
            with open(file_name,'wb') as f:
                f.write(txt)

            email = EmailMessage(subject='Client Revenue Report', body=msg_body,
                     from_email=settings.DEFAULT_FROM_EMAIL,to=[request.user.email])
            email.attach_file(file_name)
            email.send(fail_silently=False)
            os.remove(file_name)

            return render(request,"client_revenue_report.html",report_data)

        else:
            return render(request,"expenses.html",{'expense_form_set':expense_form_set})


class ClientRevenueReportView(ClientRevenueMixin, View):
    """
        Basic Client Revenue report used for rent statements
    """
    tracker_model = ClientRevenueJobsTracker
    job_info_model = ClientRevenueReportJobInfo
    enqueuer = ClientRevenueReportEnqueuer.enqueue_report
    jobstracker_enqueuer = ClientRevenueJobsTrackerEnqueuer.enqueue_job_tracker
    form_class = ClientRevenueReportForm
    fields = (
        'billing_group',
        #'year',
        #'month',
        'pdf_generation',
        'html_generation',
        'include_zero_rows'
    )
    success_msg = "The Task is being processed. Please check your inbox in a few minutes"
    failed_message = 'Some billing groups could not be added to queue processor'
    template_name = 'billing_group_selector.html'
    object_tracked_name = 'billing_group'


class ClientRevenueFullReportView(ClientRevenueMixin, View):
    """
        Low level comprehensive revenue report
    """
    tracker_model = ClientRevenueFullJobsTracker
    job_info_model = ClientRevenueFullReportJobInfo
    enqueuer = ClientRevenueFullReportEnqueuer.enqueue_report
    jobstracker_enqueuer = ClientRevenueFullJobsTrackerEnqueuer.enqueue_job_tracker
    form_class = ClientFullLowLevelReportForm
    fields = (
        'billing_group',
        #'year',
        #'month',
    )
    success_msg = "The Task is being processed. Please check your inbox in a few minutes"
    failed_message = 'Some billing groups could not be added to queue processor'
    template_name = 'billing_group_selector.html'
    object_tracked_name = 'billing_group'


class ClientRentReportView(View):
    """
    View to generate Rent Paid to Client Reports
    """
    form_class = RentReportForm
    template_name = "billing_group_selector.html"

    @method_decorator(login_required)
    def get(self, request):
        if request.user.user_profile.user_type != 'executive':
            raise PermissionDenied
        form = self.form_class()
        return render(request,self.template_name,{"data_form":form})

    def post(self, request, *args, **kwargs):
        form = self.form_class(request.POST)
        if form.is_valid():
            billing_groups = form.cleaned_data.get('billing_group')
            start_year = form.cleaned_data.get('start_year')
            start_month = form.cleaned_data.get('start_month')
            end_year = form.cleaned_data.get('end_year')
            end_month = form.cleaned_data.get('end_month')
            metric = form.cleaned_data.get('metric')

            thread_processor = ClientNetRentReportThread(
                email = request.user.email,
                billing_groups = billing_groups,
                start_year = start_year,
                start_month = start_month,
                end_year = end_year,
                end_month = end_month,
                metric = metric
            )
            thread_processor.start()
            response = HttpResponse("The report will be sent to yout email address")
            return response
            #Direct Download Processing
            # rent_report = ClientNetRentReport(
            #     billing_groups,
            #     date(int(start_year), int(start_month), 1),
            #     date(int(end_year), int(end_month), 1),
            #     metric
            # ).run()
            # with open(rent_report) as f:
            #     report_content = f.read()
            # response = HttpResponse(report_content, content_type='text/csv')
            # tm = datetime.now()
            # tm = tm.strftime('%Y_%m_%d_%H_%M_%S')
            # response['Content-Disposition'] = 'attachment; filename=RentReport_{}.csv'.format(tm)
            # os.remove(rent_report)
        else:
            return render(request,self.template_name,{"data_form":form})


class MonthlyAutoReportView(views.APIView):
    permission_classes = [permissions.IsAuthenticated]
    authentication_classes = [authentication.BasicAuthentication]

    def post(self, request, *args, **kwargs):
        try:
            report = MonthlyAutoReport().run()
            return Response(status=status.HTTP_201_CREATED)
        except Exception as e:
            raise Exception(e)
            return Response(status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class MonthlyAutoReport():
    # DEFAULT_EMAIL = 'suricatadev@gmail.com' #TODO: Ask Daniel to create an email list
    # FULL_LOW_LEVEL_REPORT_EMAIL = 'lowlevelreport@aceslaundry.com'
    # CLIENT_REVENUE_REPORT_EMAIL = 'revenuereport@aceslaundry.com'
    # REVENUE_REPORT_EMAIL = 'daniel@aptsny.com'
    # RENT_REPORT_EMAIL = 'daniel@aptsny.com'
    DEFAULT_EMAIL = 'daniel@aptsny.com' #TODO: Ask Daniel to create an email list
    FULL_LOW_LEVEL_REPORT_EMAIL = 'client-low-level-report@aceslaundry.com'
    CLIENT_REVENUE_REPORT_EMAIL = 'client-revenue-report-monthly@aceslaundry.com '
    RENT_REPORT_EMAIL = 'executive_revenue_reports@aceslaundry.com'
    INTERNAL_REVENUE_REPORT_LIST = 'executive_revenue_reports@aceslaundry.com'
    TRANSACTIONS_REPORT_EMAIL = 'employee-transactions-report@aceslaundry.com'
    TRANSACTIONS_CHECK_DEPOSITS = 'check-reconciliation-report@aceslaundry.com'

    def _metric_sanity_check(self, start_date):
        start_date = date(
            start_date.year,
            start_date.month,
            1
        )
        rooms_metrics = MetricsCache.objects.filter(
            start_date=start_date,
            duration=DurationType.MONTH,
            location_level=LocationLevel.LAUNDRY_ROOM,
            metric_type=MetricType.FASCARD_REVENUE_FUNDS
            )
        rooms_agg = rooms_metrics.values('result').aggregate(total=Sum('result'))
        bgs_metrics = MetricsCache.objects.filter(
            start_date=start_date,
            duration=DurationType.MONTH,
            location_level=LocationLevel.BILLING_GROUP,
            metric_type=MetricType.FASCARD_REVENUE_FUNDS
        )
        bgs_agg = bgs_metrics.values('result').aggregate(total=Sum('result'))
        return rooms_agg.get('result') == bgs_agg.get('result')

    def run(self):
        from reporting.finance.internal_report_views import ReportThreadProcessor
        today = date.today()
        #assert today.day == 1
        month_ago = today - relativedelta(months=1)
        sanity_check = self._metric_sanity_check(month_ago)
        logger.info(f"Monthly report sanity check successful: {sanity_check}")
        Aurora.increase_aurora_capacity(64, sleep_time=120)
        #Enqueue Full Low Level Report
        full_revenue_view  = ClientRevenueFullReportView()
        full_revenue_jobs_tracker = full_revenue_view.tracker_model.objects.create(
                user_requested_email=self.FULL_LOW_LEVEL_REPORT_EMAIL,
            )
        full_revenue_base_payload = {
            'year': month_ago.year,
            'month': month_ago.month,
            'job_tracker' : full_revenue_jobs_tracker
        }
        client_revenue_report_view = ClientRevenueReportView()
        client_revenue_report_jobs_tracker = client_revenue_report_view.tracker_model.objects.create(
                user_requested_email=self.CLIENT_REVENUE_REPORT_EMAIL,
            )
        client_revenue_report_base_payload = {
            'year': month_ago.year,
            'month': month_ago.month,
            'job_tracker' : client_revenue_report_jobs_tracker,
            'pdf_generation' : True
        }
        reports_via_queue = (
            (client_revenue_report_base_payload, client_revenue_report_view),
            (full_revenue_base_payload, full_revenue_view),
        )

        for report in reports_via_queue:
            payload = report[0]
            report_view = report[1]
            jobs_tracker = payload.get('job_tracker')

            for billing_group in BillingGroup.objects.filter(is_active=True):
                payload_copy = deepcopy(payload)
                payload_copy['billing_group'] = billing_group
                try:
                    job_info = report_view.job_info_model(**payload_copy)
                    job_info.save()
                    report_view.enqueuer(job_info.id)
                    msg=report_view.success_msg
                    success = True
                except Exception as e:
                    report_view.failed_message += ' Task enqueuer failed for BillingGroup:{} with exception: {}. '.format(billing_group, e)
                    msg = self.failed_message
                    success = False #?
                    raise Exception(e)

            try:
                report_view.jobstracker_enqueuer(jobs_tracker.id)
                logger.info('JobTracker job was enqueued succesfully')
            except Exception as e:
                logger.error('Failed enqueueing the JobsTracker job')
                raise (e)
        #Internal Revenue Report
        trailing_thirteen_month = month_ago - relativedelta(months=13)
        laundry_rooms_ids = LaundryRoom.objects.all().values_list('id', flat=True)
        try:
            file_name_response = InternalReport.run(
                metric_type=MetricType.REVENUE_FUNDS,
                duration_type=DurationType.MONTH,
                start_date = trailing_thirteen_month,
                end_date = month_ago,
                location_level = LocationLevel.LAUNDRY_ROOM,
                laundry_room_ids = list(laundry_rooms_ids),
                billing_group_ids = [],
                active_only = False,
                exclude_zero_rows = False,
                email = self.INTERNAL_REVENUE_REPORT_LIST,
                delivery_method = 'email',
                **kwargs
            )
        except Exception as e:
            err_msg = 'Failed Running Internal Revenue Report in AutoReport: {}'.format(e)
            logger.error(err_msg)

        #Non-enqueable reports - Rent Reports
        rent_reports = (
            ClientRentReportMetrics.ACESNET_AFTER_RENT,
            ClientRentReportMetrics.RENT_PERCENTAGE_REVENUE,
        )
        for rent_report in rent_reports:
            thread_processor = ClientNetRentReportThread(
                email = self.RENT_REPORT_EMAIL,
                billing_groups = BillingGroup.objects.filter(is_active=True),
                start_year = trailing_thirteen_month.year,
                start_month = trailing_thirteen_month.month,
                end_year = month_ago.year,
                end_month = month_ago.month,
                metric = rent_report
            )
            thread_processor.start()
        #Transactions Reports
        end_of_month = date(
            month_ago.year,
            month_ago.month,
            calendar.monthrange(*tuple([month_ago.year, month_ago.month,]))[1])
        employees = FascardUser.objects.filter(is_employee=True).order_by('name')
        employees_ids = [e.fascard_user_account_id for e in employees]
        employee_activity_payload = {
            'start' : month_ago,
            'end' : end_of_month,
            'tx_type' : 'employee_activity', #i,e machine starts by employee
            'extra_data' : None,
            'custom_query' : [
                Q(fascard_user__fascard_user_account_id__in=employees_ids) | Q(external_fascard_user_id__in=employees_ids)
            ]
        }
        customer_admin_adjusts_payload = {
            'start' : month_ago,
            'end' : end_of_month,
            'tx_type' : 'customer_admin_ajusts',
            'extra_data' : {'employee_user_id__in' : [e.xxx_caution_fascard_user_id for e in employees]},
        }
        check_deposits_payload = {
            'start' : month_ago,
            'end' : end_of_month,
            'tx_type' : 'checks_deposits',
        }
        try:
            ReportThreadProcessor(self.TRANSACTIONS_REPORT_EMAIL, employee_activity_payload).start()
        except Exception as e:
            err_msg = 'Failed processing Transactions Report Employee--Machines starts in AutoReport: {}'.format(e)
            logger.error(err_msg)
        try:
            ReportThreadProcessor(self.TRANSACTIONS_REPORT_EMAIL, customer_admin_adjusts_payload).start()
        except Exception as e:
            err_msg = 'Failed processing Transactions Report Employee--admin adjusts in AutoReport: {}'.format(e)
            logger.error(err_msg)
        try:
            ReportThreadProcessor(self.TRANSACTIONS_CHECK_DEPOSITS, check_deposits_payload).start()
        except Exception as e:
            err_msg = 'Failed processing Transactions Report Check-Deposits in AutoReport: {}'.format(e)
            logger.error(err_msg)
        return True
