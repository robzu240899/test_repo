import threading
import os
from datetime import date, datetime, timedelta
from dateutil.relativedelta import relativedelta
from django.http import HttpResponse, HttpResponseForbidden
from django.views import View
from django import forms
from django.db.models import Q
from django.shortcuts import render
from django.core.exceptions import ValidationError, PermissionDenied
from django.utils.translation import gettext as _
from django.contrib.auth.decorators import login_required
from django.contrib.humanize.templatetags import humanize
from django.utils.decorators import method_decorator
from django.core.mail import EmailMessage
from queuehandler.job_creator import TimeSheetsReportJobEnqueuer, TimeSheetsReportTrackerEnqueuer
from main.settings import DEFAULT_FROM_EMAIL
from roommanager.models import LaundryRoom
from reporting.enums import RefundReportType
from reporting.finance.internal.report import InternalReport, InternalReportSetupException, RefundReport, RefundMetricReport
from reporting.finance.internal.pricing_report import PricingReport
from reporting.finance.internal.lease_abstract import LeaseAbstractReport
from reporting.finance.internal.transactions_report import TransactionReport, TransactionsTimeSheet
from reporting.models import BillingGroup,  TimeSheetsReportJobTracker, TimeSheetsReportJobInfo
from reports.enums import TimeUnits
from revenue.models import FascardUser
from ..enums import MetricType, LocationLevel, DurationType, TransactionReportType, SortParameters
from .mixins import ClientRevenueMixin


class CustomDateInput(forms.widgets.TextInput):
    input_type = 'date'
    #input_formats=['%Y-%m-%d']

class PriceHistoryForm(forms.Form):
    start_date = forms.DateField(widget=CustomDateInput)
    final_date = forms.DateField(widget=CustomDateInput)
    buildings = forms.ModelMultipleChoiceField(queryset=LaundryRoom.objects.all(),required=False)
    seperate_buildings = forms.BooleanField(required=False)

class PriceHistoryView(View):

    TEMPLATE_NAME = 'pricing_report.html'

    @method_decorator(login_required)
    def get(self,request):
        msg = ""
        form = PriceHistoryForm()
        return render(request,self.TEMPLATE_NAME,
                                      {'msg':msg,'revenue_form':form})

    @method_decorator(login_required)
    def post(self,request):
        form = PriceHistoryForm(request.POST)
        if not form.is_valid():
            msg = "Please correct errors in the form."
        else:
            start_date = form.cleaned_data.get('start_date')
            final_date = form.cleaned_data.get('final_date')
            laundry_room_ids = form.cleaned_data.get('buildings')
            seperate_buildings = form.cleaned_data.get('seperate_buildings')
            csv_name = PricingReport(start_date, final_date, laundry_room_ids, seperate_buildings).generate_csv()
            email = EmailMessage(subject = 'Pricing History Report', body = "Pricing History report is attached", from_email=DEFAULT_FROM_EMAIL,
                           to=[request.user.email])
            with open(csv_name) as f:
                attachment_name = 'pricing_history_report_%s_%s.csv' % (start_date,final_date)
                email.attach(attachment_name, f.read(), 'text/csv')
                email.send(fail_silently=False)
            os.remove(csv_name)
            msg = "Pricing history report sent to %s" % request.user.email
        return render(request, self.TEMPLATE_NAME,
                                      {'msg':msg,'revenue_form':form})

class RevenueForm(forms.Form):
    start_date = forms.DateField(widget=CustomDateInput)
    end_date = forms.DateField(widget=CustomDateInput)
    time_level = forms.ChoiceField(label='Time Grouping',required=True,choices=DurationType.CHOICES)
    location_level = forms.ChoiceField(label='Location Grouping',required=True,choices=LocationLevel.CHOICES)
    revenue_rule = forms.ChoiceField(label='Revenue Rule',required=True,choices=MetricType.CHOICES)
    buildings = forms.ModelMultipleChoiceField(queryset=LaundryRoom.objects.all(),required=False)
    billing_groups = forms.ModelMultipleChoiceField(queryset=BillingGroup.objects.all(),required=False)
    active_only = forms.BooleanField(required=False)
    exclude_zero_rows = forms.BooleanField(required=False)
    sort_parameter = forms.ChoiceField(label='Sort by (only for rooms)', required=False, choices=SortParameters.CHOICES)
    delivery_method = forms.ChoiceField(required=True, choices=(('download', 'Direct Download'), ('email','Email')))

    def clean(self):
        cleaned_data=super(RevenueForm, self).clean()
        buildings = cleaned_data['buildings']
        billing_groups = cleaned_data['billing_groups']
        if cleaned_data['location_level'] == LocationLevel.BILLING_GROUP and buildings:
            raise ValidationError(_("Can't filter on laundry rooms when the location level is Billing Group"))
        if billing_groups and buildings:
            raise ValidationError(_("May not select both buildings and billing groups"))
        start_date = cleaned_data['start_date']
        end_date = cleaned_data['end_date']
        duration_type = cleaned_data['time_level']
        if duration_type == DurationType.MONTH:
            cleaned_data['start_date'] = date(start_date.year,start_date.month,1)
            cleaned_data['end_date'] = date(end_date.year,end_date.month,1) + relativedelta(months=1)
        elif duration_type == DurationType.YEAR:
            cleaned_data['start_date'] = date(start_date.year,1,1)
            cleaned_data['end_date'] = date(end_date.year,1,1) + relativedelta(years=1)
        elif duration_type == DurationType.DAY:
            cleaned_data['end_date'] = end_date + timedelta(days=1)
        return cleaned_data


class InternalReportThreadProcessor(threading.Thread):

    def __init__(self, internal_report_payload, *args, **kwargs):
        self.internal_report_payload = internal_report_payload
        super(InternalReportThreadProcessor, self).__init__(*args, **kwargs)

    def run(self):
        response = InternalReport.run(**self.internal_report_payload)
        return True


class InternalReportView(View):

    TEMPLATE_NAME = 'internal_report.html'


    @method_decorator(login_required)
    def get(self,request):
        msg = ""
        form = RevenueForm()
        return render(request,self.TEMPLATE_NAME,
                                      {'msg':msg,'revenue_form':form})


    @method_decorator(login_required)
    def post(self,request):

        form = RevenueForm(request.POST)
        if not form.is_valid():
            msg = "Please correct errors in the form."
        else:
            location_level = form.cleaned_data.get('location_level')
            duration_type = form.cleaned_data.get('time_level')
            start_date = form.cleaned_data.get('start_date')
            end_date = form.cleaned_data.get('end_date')  #NB: the front end should be inclusive.  We add 1 to the end date in the form clean.
            metric_type = form.cleaned_data.get('revenue_rule')
            active_only = form.cleaned_data.get('active_only')
            exclude_zero_rows = form.cleaned_data.get('exclude_zero_rows')
            buildings = form.cleaned_data.get('buildings')
            billing_groups = form.cleaned_data.get('billing_groups')
            delivery_method = form.cleaned_data.get('delivery_method')

            if active_only is None:
                active_only = False
            if buildings:
                laundry_room_ids = [b.id for b in buildings]
            else:
                laundry_room_ids = []
            if billing_groups:
                billing_group_ids = [bg.id for bg in billing_groups]
            else:
                billing_group_ids = []

            kwargs = {}
            if location_level == LocationLevel.LAUNDRY_ROOM:
                sort_by= form.cleaned_data.get('sort_parameter')
                if sort_by != SortParameters.ALPHABETICAL:
                    kwargs.update({'sort_parameter':sort_by})

            internal_report_payload = {
                'metric_type' : metric_type,
                'duration_type' : duration_type,
                'start_date' : start_date,
                'end_date' : end_date,
                'location_level' : location_level,
                'laundry_room_ids' : laundry_room_ids,
                'billing_group_ids' : billing_group_ids,
                'active_only' : active_only,
                'exclude_zero_rows' : exclude_zero_rows,
                'email' : request.user.email,
                'delivery_method': delivery_method,
            }
            internal_report_payload.update(**kwargs)


            try:
                msg = 'Report sent'
                if delivery_method == 'download':
                    response = InternalReport.run(**internal_report_payload)
                elif delivery_method == 'email':
                    InternalReportThreadProcessor(internal_report_payload).start()
                    msg = 'The report will be delivered via email'
                else:
                    response = InternalReport.run(**internal_report_payload)
            except InternalReportSetupException as e:
                msg = str(e)

            if delivery_method == 'download' and response:
                file_name = response
                with open(file_name) as f:
                    report_content = f.read()
                    response_content = HttpResponse(report_content, content_type='text/csv')
                    attachment_name = 'reveue_report_%s_%s.csv' % (start_date,metric_type)
                    response_content['Content-Disposition'] = 'attachment; filename={}'.format(attachment_name)
                    os.remove(file_name)
                    return response_content
        return render(request,self.TEMPLATE_NAME,
                                      {'msg':msg,'revenue_form':form})

class LeaseAbstractReportView(View):

    @method_decorator(login_required)
    def get(self, request):
        if request.user.user_profile.user_type != 'executive':
            raise PermissionDenied
        lease_report = LeaseAbstractReport().generate()
        response = HttpResponse(lease_report, content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename=lease-report.csv'
        return response


class CustomModelChoiceField(forms.ModelMultipleChoiceField):
    def label_from_instance(self, obj):
        string_rep = str(obj)
        if obj.fascard_last_activity_date: string_rep += f" ------ (LastActivity: {humanize.naturaltime(obj.fascard_last_activity_date)})"
        return string_rep


class TransactionReportForm(forms.Form):
    start_date = forms.DateField(widget=CustomDateInput)
    end_date = forms.DateField(widget=CustomDateInput)
    employee = CustomModelChoiceField(
        queryset=FascardUser.objects.filter(is_employee=True).order_by('-fascard_last_activity_date'), 
        required=False)
    report_type  = forms.ChoiceField(label='Report Type',required=True, choices=TransactionReportType.CHOICES)
    last_activity_lookback = forms.IntegerField(required=False)
    last_activity_lookback_time_units = forms.ChoiceField(choices=TimeUnits.CHOICES, required=False)

    def clean(self):
        last_activity_lookback = self.cleaned_data.get('last_activity_lookback')
        last_activity_lookback_time_units = self.cleaned_data.get('last_activity_lookback_time_units')
        employee = self.cleaned_data.get('employee')
        if (last_activity_lookback and last_activity_lookback_time_units and employee):
            self.add_error('employee', "May not select both Employees and Activty Lookback at the same time")
            #raise forms.ValidationError("May not select both Employees and Activty Lookback at the same time")


import threading
from django.core.mail import EmailMessage
class ReportThreadProcessor(threading.Thread):

    def __init__(self, user_email, payload, *args, **kwargs):
        self.payload = payload
        self.report_type = payload.get('tx_type')
        self.user_email=user_email
        super(ReportThreadProcessor, self).__init__(*args, **kwargs)

    def run(self) -> None:
        now = datetime.now()
        if self.report_type == 'employee_timesheet':
            self.payload['user_email'] = self.user_email
            report = TransactionsTimeSheet(**self.payload)
        else:
            report = TransactionReport(**self.payload)
        final_dataset = report.get()
        if not final_dataset: return
        subject = "{} report is attached".format(self.report_type)
        msg = EmailMessage(
            subject=subject,
            body=subject,
            from_email=DEFAULT_FROM_EMAIL,
            to=self.user_email.split(',')
        )
        attachment_name = 'transactions_report_%s_%s.csv' % (now,self.report_type)
        msg.attach(attachment_name, final_dataset, 'text/csv')
        msg.send(fail_silently=False)


class TimeSheetsReportViewProcessor(ClientRevenueMixin):
    # fields = ("Fields returned from the form")
    tracker_model = TimeSheetsReportJobTracker
    job_info_model = TimeSheetsReportJobInfo
    enqueuer = TimeSheetsReportJobEnqueuer.enqueue_report
    jobstracker_enqueuer = TimeSheetsReportTrackerEnqueuer.enqueue_job_tracker
    success_msg = "The Task is being processed. Please check your inbox in a few minutes"
    failed_message = 'Some users could not be added to queue processor'
    template_name = 'transaction_report_template.html'
    object_tracked_name = 'employee'
    fields = (
        'start_date',
        'end_date',
        'employee'
    )


class TransactionReportView(View):

    def _fetch_extra_filters(self, report_type, employees):
        extra_filters = None
        custom_query = None
        employees_ids = [e.fascard_user_account_id for e in employees]
        if report_type == 'customer_admin_ajusts' and len(employees_ids) > 0:
                extra_filters = {'employee_user_id__in' : [e.xxx_caution_fascard_user_id for e in employees]}
        elif len(employees_ids) > 0:
            if report_type in ['employee_activity', 'employee_timesheet']:
                custom_query = [
                    Q(fascard_user__fascard_user_account_id__in=employees_ids) | Q(external_fascard_user_id__in=employees_ids)
                ]
            else:
                extra_filters = {
                    'fascard_user__fascard_user_account_id__in' : employees_ids,
                    'external_fascard_user_id__in' : employees_ids
                }
        return extra_filters, custom_query


    @method_decorator(login_required)
    def get(self,request, *args, **kwargs):
        form = TransactionReportForm()
        return render(request, "transaction_report_template.html", {"form": form})

    @method_decorator(login_required)
    def post(self, request, *args, **kwargs):
        form = TransactionReportForm(request.POST)
        user_email = request.user.email
        if form.is_valid():
            if not user_email:
                return HttpResponse("Error. No email to send report to for user: {}".format(request.user))
            employees = form.cleaned_data.get('employee')
            last_activity_lookback_time_units = form.cleaned_data.get('last_activity_lookback_time_units')
            last_activity_lookback = form.cleaned_data.get('last_activity_lookback')
            if not employees and (last_activity_lookback_time_units and last_activity_lookback is not None):
                activity_end_date = date.today() + relativedelta(days=1)
                activity_start_date = activity_end_date - relativedelta(**{last_activity_lookback_time_units: last_activity_lookback})
                employees = FascardUser.objects.filter(
                    is_employee = True,
                    fascard_last_activity_date__gte = activity_start_date,
                    fascard_last_activity_date__lte = activity_end_date
                )
            report_type = form.cleaned_data.get('report_type')
            #extra_filters, custom_query = self._fetch_extra_filters(report_type, employees)
            #if report_type == 'employee_timesheet':
            #    msg = TimeSheetsReportViewProcessor()._enqueue(form, request)
            #else:
            payload = {
                'start' : form.cleaned_data.get('start_date'),
                'end' : form.cleaned_data.get('end_date'),
                'tx_type' : report_type,
                'employees' : employees
                #'extra_data' : extra_filters,
                #'custom_query' : custom_query,
            }
            thread_processor = ReportThreadProcessor(user_email, payload).start()
            msg = "The report will be emailed to: {}".format(user_email)
            response = HttpResponse(msg)
            return response
        return render(request, "transaction_report_template.html", {"form": form})

        
class RefundsReportForm(forms.Form):
    start_date = forms.DateField(widget=CustomDateInput)
    end_date = forms.DateField(widget=CustomDateInput)
    laundry_rooms = forms.ModelMultipleChoiceField(
        queryset=LaundryRoom.objects.all(),
        required=False,
        help_text='Leave Blank to Include all locations')
    report_type = forms.ChoiceField(choices=RefundReportType.CHOICES)


class RefundsReportView(View):
    form_class = RefundsReportForm
    template_name = 'refunds_report.html'

    @method_decorator(login_required)
    def get(self,request, *args, **kwargs):
        form = self.form_class()
        return render(request, self.template_name, {"form": form})

    @method_decorator(login_required)
    def post(self, request, *args, **kwargs):
        form = self.form_class(request.POST)
        if form.is_valid():
            start_date = form.cleaned_data.get('start_date')
            end_date = form.cleaned_data.get('end_date')
            params = [start_date, end_date]
            rooms = form.cleaned_data.get('laundry_rooms')
            report_type = form.cleaned_data.get('report_type')
            if rooms:
                params.append(rooms)
            if report_type == RefundReportType.REFUND_BASIC_REPORT:
                processor = RefundReport
                base_name = 'RefundsReport'
            else:
                processor = RefundMetricReport
                base_name = 'RefundsMetricReport'
            csv = processor().run(*params)
            response = HttpResponse(csv, content_type='text/csv')
            tm = datetime.now()
            tm = tm.strftime('%Y_%m_%d_%H_%M_%S')
            response['Content-Disposition'] = 'attachment; filename={}_{}.csv'.format(base_name,tm)
            return response