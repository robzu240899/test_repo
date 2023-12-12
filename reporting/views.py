"""

Created by @juan_eljach

Views to handle the new Pricing Report integration with Fascard API
"""
import logging
import threading
from datetime import datetime
from django import forms
from django.conf import settings
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse, HttpResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404
from django.template.response import TemplateResponse
from django.views import View
from rest_framework import permissions, authentication, views, status, response
from queuehandler.job_creator import PricingChangesJobCreator, PricingDataFetchTaskCreator, \
         PricingJobsTrackerJobCreator, TimeUsageReportEnqueuer
from reporting.enums import LocationLevel, REVENUE_DATA_GRANULARITY
from reporting.finance.internal.pricing_report import CustomPricingHistoryReport, PricingPeriodMetricsHandler
from reporting.finance.internal.usage_report import TimeUsageReport
from roommanager.models import LaundryRoom, EquipmentType
from .models import PricingPeriod, PricingReportJobInfo, PricingReportJobsTracker
from .threads import PricingReportEnqueuerThread


logger = logging.getLogger(__name__)


class CustomPriceHistoryForm(forms.Form):
    #periods_to_lookback = forms.IntegerField(min_value=0, max_value=5)
    months_to_lookback = forms.IntegerField(min_value=1)
    laundry_rooms = forms.ModelMultipleChoiceField(
        queryset=LaundryRoom.objects.filter(is_active=True),
        required=False,
        widget=forms.SelectMultiple(attrs={'class': "room-selector"}),
    )
    colors = forms.BooleanField(label='Color for chart lines', required=False)


class CustomPricingReportView(View):
    form_class = CustomPriceHistoryForm
    template_name = 'pricing_history_report_queued.html'

    def get(self, request, *args, **kwargs):
        form = self.form_class()
        return TemplateResponse(request, self.template_name, {'form': form})

    def post(self, request, *args, **kwargs):
        context = {}
        form = self.form_class(request.POST)
        if form.is_valid():
            rolling_mean_periods = form.cleaned_data.get('rolling_mean_periods')
            laundry_rooms_ids = form.cleaned_data.get('laundry_rooms')
            pricinghistory_report_generator = CustomPricingHistoryReport(
                 rolling_mean_periods, laundry_rooms_ids[0].id)
            response_payload = pricinghistory_report_generator.generate_response()
            context["queryset"] = response_payload
        context['form'] = form
        context.update(self.kwargs)
        return TemplateResponse(request, self.template_name, context)


class OnDemandPricingReportView(LoginRequiredMixin, View):
    login_url = "/admin/login/"
    form_class = CustomPriceHistoryForm
    processor = PricingChangesJobCreator.create_report
    jobstracker_enqueuer = PricingJobsTrackerJobCreator.enqueue_job_tracker
    template_name = 'pricing_history_report_job.html'
    success_msg = "Registration Success. Please wait a few hours for processing"

    def get(self, request, *args, **kwargs):
        form = self.form_class()
        return TemplateResponse(request, self.template_name, {'form': form})

    def post(self, request, *args, **kwargs):
        context = {}
        form = self.form_class(request.POST)
        if form.is_valid():
            laundry_rooms_objects = form.cleaned_data.get('laundry_rooms')
            months = form.cleaned_data.get('months_to_lookback')
            colors = form.cleaned_data.get('colors')
            try: user_email = request.user.email
            except: user_email = None

            #Call Thread
            thread_processor = PricingReportEnqueuerThread(
                laundry_rooms_objects,
                user_email,
                months,
                colors,
            )
            thread_processor.start()
            msg = "The jobs are being enqueued"
            #Create tracker object
            # try:
            #     report_jobs_tracker = PricingReportJobsTracker.objects.create(
            #         user_requested_email = user_email
            #     )
            # except Exception as e:
            #     raise Exception("Failed creating JobTracker with Exception: {}".format(e))
            # for laundry_room in laundry_rooms_objects:
            #     try:
            #         job_info = PricingReportJobInfo(
            #             rolling_mean_periods=rolling_mean_periods,
            #             laundry_room=laundry_room,
            #             job_tracker=report_jobs_tracker
            #         )
            #         job_info.save()
            #         self.processor(job_info)
            #         msg=self.success_msg
            #     except Exception as e:
            #         msg = "On-demand job creation failed with Exception: e {}".format(e)
            # try:
            #     self.jobstracker_enqueuer(report_jobs_tracker)
            #     logger.info('JobTracker job was enqueued succesfully')
            # except Exception as e:
            #     logger.error('Failed enqueueing the JobsTracker job. Exception: {}'.format(e))
            #     raise Exception(e)
        else:
            msg = form.errors
        context['form'] = form
        context['msg'] = msg
        context.update(self.kwargs)
        return TemplateResponse(request, self.template_name, context)


class PricingChangesTaskView(views.APIView):
    processor = PricingDataFetchTaskCreator.enqueue_data_fetch
    permission_classes = [permissions.IsAuthenticated]
    authentication_classes = [authentication.BasicAuthentication]

    def post(self, request):
        laundry_group_id = getattr(request.data, "laundry_group_id", 1)
        try:
            self.processor(laundry_group_id)
            return response.Response(status=status.HTTP_200_OK)
        except Exception as e:
            return response.Response(status=status.HTTP_500_INTERNAL_SERVER_ERROR)

def ajax_plot(request):
    if request.method == 'GET':
        lri = request.GET.get('laundry_room', None)
        pp = request.GET.get('pricing_period', None)
        if lri and pp:
            laundry_room = get_object_or_404(LaundryRoom, pk=lri)
            pricing_period = get_object_or_404(PricingPeriod, pk=pp)
            pricing_start_date = getattr(pricing_period, 'start_date', None)
            pricing_end_date = getattr(pricing_period, 'end_date', None)
            if not pricing_end_date:
                pricing_end_date = datetime.today().date()
            location_level = LocationLevel.LAUNDRY_ROOM
            metrics_handler = PricingPeriodMetricsHandler(
                laundry_room,
                pricing_start_date,
                pricing_end_date,
                location_level
            )
            data = metrics_handler.get_all_metrics()
            return JsonResponse(data)
    else:
        data = {
            'errMessage': 'Method is not GET'
        }
        return JsonResponse(data)


class TimeUsageForm(forms.Form):
    days = forms.IntegerField(min_value=1, help_text="(Size of random sample)")
    months_to_lookback = forms.IntegerField(min_value=1)
    laundry_rooms = forms.ModelMultipleChoiceField(
        queryset=LaundryRoom.objects.filter(is_active=True),
        required=False,
        widget=forms.SelectMultiple(attrs={'class': "room-selector"}),
    )


class TimeUsageReportThreadProcessor(threading.Thread):

    def __init__(self, user_email, days, months, rooms, *args, **kwargs):
        self.user_email = user_email
        self.days = days
        self.months = months
        self.rooms = rooms
        super(TimeUsageReportThreadProcessor, self).__init__(*args, **kwargs)

    def run(self):
        TimeUsageReport.run_job(self.user_email, self.days, self.months, self.rooms)


class TimeUsageReportView(LoginRequiredMixin, View):
    login_url = "/admin/login/"
    #enqueuer = TimeUsageReportEnqueuer.enqueue_report
    form_class = TimeUsageForm
    template_name = "time_usage.html"

    def get(self, request, *args, **kwargs):
        form = self.form_class()
        return TemplateResponse(request, self.template_name, {'form': form})

    def post(self, request, *args, **kwargs):
        form = self.form_class(request.POST)
        if form.is_valid():
            days = form.cleaned_data.get("days")
            months = form.cleaned_data.get("months_to_lookback")
            rooms = form.cleaned_data.get("laundry_rooms")
            try:
                user_email = request.user.email
            except:
                raise HttpResponseBadRequest()
            #self.enqueuer(user_email, days, months, rooms)
            thread_processor = TimeUsageReportThreadProcessor(
                user_email,
                days,
                months,
                rooms
            ).start()
            return HttpResponse("Job Scheduled. Report will be sent to email address")
        else:
            return TemplateResponse(request, self.template_name, {'form': form})