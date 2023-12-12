'''
Created on Apr 22, 2017

@author: Thomas
'''
import logging
from django import forms
from django.http import HttpResponse
from django.views import View
from django.shortcuts import render
from django import forms
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.utils.decorators import method_decorator
from queuehandler.job_creator import ReportCreator, MetricsCreator, RevenueCreator
from queuehandler.queue import QueueInspector
from queuehandler.nightly_run import NightlyRunEnums, TiedRunManager
from queuehandler.views import NightlyRunEnqueue
from queuehandler.utils import Aurora
from roommanager.models import Slot
from roommanager.signals import _sync_slot_label
from reporting.enums import LocationLevel, DurationType
from revenue.threads import OndemandTransactionReingest

logger = logging.getLogger(__name__)

class MenuView(View):

    def get(self,request):
        logger.info("Testing logging.")
        return render(request,'menu.html')


class CustomDateInput(forms.widgets.TextInput):
    input_type = 'date'


class DateRangeForm(forms.Form):
    start_date = forms.DateField(widget=CustomDateInput)
    end_date = forms.DateField(widget=CustomDateInput)


class MetricsRecalcForm(DateRangeForm):
    location_level = forms.ChoiceField(label='Location Grouping',required=True,choices=LocationLevel.CHOICES)
    duration_type = forms.ChoiceField(label='Duration Type',required=True,choices=DurationType.CHOICES)
    database_instances = forms.ChoiceField(choices=[(x,x) for x in [2,4,8,16,32,64]])


class RecalculationView(View):
    def get(self,request):
        if hasattr(self, 'form_class'):
            form = self.form_class()
        else:
            form = DateRangeForm()
        return render(request, 'recalcuation.html', {'form':form,'msg':self.initial_msg, 'title':self.title})

    def _set_kwargs(self, form):
        start_date = form.cleaned_data.get('start_date')
        end_date = form.cleaned_data.get('end_date')
        self.kwargs = {'start_date':start_date, 'end_date':end_date}
        if hasattr(self, 'extra_fields'):
            for f in self.extra_fields:
                self.kwargs[f] = form.cleaned_data.get(f)

    def post(self,request):
        if hasattr(self, 'form_class'):
            form = self.form_class(request.POST)
        else:
            form = DateRangeForm(request.POST)
        if not form.is_valid():
            msg = "Please correct errors in the form."
        else:
            if 'database_instances' in form.cleaned_data:
                Aurora.increase_aurora_capacity(
                    int(form.cleaned_data.get('database_instances')),
                    sleep_time = 30)
            self._set_kwargs(form)
            self.processor(**self.kwargs)
            msg = self.success_msg
        return render(request, 'recalcuation.html', {'form':form,'msg':msg,'title':self.title})


class MetricsRecaculationView(RecalculationView):
    title = 'Metrics Recalculation.'
    initial_msg = 'It may take several minutes to register the jobs.  Once this is finished, you will receive a message here.  After that, please wait 2 hours for jobs to process.'
    success_msg = "Registration Success. Please wait 2 hours for processing"
    processor = MetricsCreator.metrics_recalc
    form_class = MetricsRecalcForm
    extra_fields = ('location_level','duration_type')


class RevenueRescrapeView(RecalculationView):

    title = 'Revenue Rescrape'
    initial_msg = 'It may take several minutes to register the jobs.  Once this is finished, you will receive a message here.  After that, please wait 2 hours for jobs to process.'
    success_msg = "Registration Success. Please wait 1 hours for processing"
    processor = RevenueCreator.create_revenue_scrape_jobs


class RevenueMatchView(RecalculationView):

    title = 'Revenue Match'
    initial_msg = 'It may take several minutes to register the jobs.  Once this is finished, you will receive a message here.  After that, please wait 2 hours for jobs to process.'
    success_msg = "Registration Success. Please wait forms1 hours for processing"
    processor = RevenueCreator.match_transactions

    def _set_kwargs(self, form):
        self.kwargs = {}


class ManualOOOView(View):

    def get(self,request):
        num_in_queue = QueueInspector().get_number_messages_in_queue()
        if num_in_queue == 0:
            ReportCreator.create_ooo_report_job()
            return render(request,'menu.html',
                          context={'msg':"Out of order report added to the queue.  The email will be sent out shortly."})
        else:
            return render(request,'menu.html',
                          context={'msg':"Other jobs are being processed.  Please wait until these are finished."})

class ManualUpkeepReportView(View):

    def get(self,request):
        num_in_queue = QueueInspector().get_number_messages_in_queue()
        if num_in_queue == 0:
            ReportCreator.create_upkeep_report_job()
            return render(request,'menu.html',
                          context={'msg':"Daily Upkeep report added to the queue.  The email will be sent out shortly."})
        else:
            return render(request,'menu.html',
                          context={'msg':"Other jobs are being processed.  Please wait until these are finished."})


class TransactionReingestForm(forms.Form):
    start_from_id = forms.IntegerField(required=True)
    end_at_id = forms.IntegerField(required=False)


class ManualReingestTransactionsView(View):
    form_class = TransactionReingestForm

    @method_decorator(login_required)
    def get(self,request, *args, **kwargs):
        form = self.form_class()
        return render(request, "tx_reingest.html", {"form": form})

    @method_decorator(login_required)
    def post(self, request, *args, **kwargs):
        form = self.form_class(request.POST)
        if form.is_valid():
            start_from_id = form.cleaned_data.get('start_from_id')
            end_at_id = form.cleaned_data.get('end_at_id')
            thread_processor = OndemandTransactionReingest(start_from_id, end_at_id).start()
            response = HttpResponse("Transaction Ingest Running")
            return response
        else:
            raise forms.ValidationError("Form is invalid: {}".format(form.errors))


class ManualNightlyRunForm(forms.Form):
    steps = forms.MultipleChoiceField(choices=NightlyRunEnums.CHOICES)

class ManualNightlyRun(View, LoginRequiredMixin):
    form_class = ManualNightlyRunForm

    def post(self, request, *args, **kwargs):
        form = self.form_class(self.request.POST)
        if form.is_valid():
            steps = form.cleaned_data.get('steps')
            payload = {'jobname':'nightlyrun','stepstorun':','.join(steps)}
            user = request.user
            notify_email = None
            if user and hasattr(user, 'email'): notify_email = user.email
            if notify_email: payload['notify'] = notify_email
            NightlyRunEnqueue._enqueue(**payload)
            response = HttpResponse("Jobs Enqueued")
            return response
            #d = {'jobname':'nightlyrun', 'stepstorun':','.join(steps)}
            #NightlyRunEnqueue._enqueue(**d)
            #_enqueue(cls, )

    def get(self, request, *args, **kwargs):
        form = self.form_class()
        return render(request, 'manual_nightly_run.html', {'form':form})


class ManualSlotsFascardSync(View, LoginRequiredMixin):
    def get(self, request, *args, **kwargs):
        failed = []
        for slot in Slot.objects.filter(laundry_room__is_active=True):
            try:
                _sync_slot_label(slot)
            except:
                failed.append(slot)
        final_msg = 'Slots synced to fascard.'
        if failed:
            final_msg = ' '.join([final_msg, 'Failed syncing: '])
            final_msg += ','.join(failed)
        return render(request,'menu.html', context={'msg':final_msg})

