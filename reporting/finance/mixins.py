import calendar
import logging
import operator
from collections import OrderedDict
from copy import deepcopy
from datetime import date
from itertools import groupby
from dateutil.relativedelta import relativedelta
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from django.shortcuts import render
from reporting.models import BillingGroup, CustomPriceHistory
from roommanager.models import LaundryRoom
from .forms import ClientRevenueReportForm

logger = logging.getLogger(__name__)


class ClientRevenueMixin(object):

    """
    Create and enqueues job_info_model objects whose execution is tracked by a job_tracker (batch processing).
    See child's attributes for more details.
    """

    def _enqueue(self, start_date, end_date, user_email, cleaned_data) -> str:
        msg = ''
        jobs_tracker = self.tracker_model.objects.create(
                user_requested_email=user_email,
            )
        jobs_buffer = []
        while start_date <= end_date:
            today = date.today()
            start_of_month=date(today.year, today.month, 1)
            end_of_month = date(
                start_of_month.year,
                start_of_month.month,
                calendar.monthrange(*tuple([start_of_month.year, start_of_month.month,]))[1])
            if start_date > start_of_month and start_date <= end_of_month:
                start_date = start_date + relativedelta(months=1)
                continue
            payload = {'month': start_date.month, 'year': start_date.year}
            for f in self.fields:
                try:
                    payload[f] = cleaned_data.get(f)
                except:
                    pass
            objects_tracked = payload.get(self.object_tracked_name)
            assert objects_tracked
            for object_tracked in objects_tracked:
                payload_copy = deepcopy(payload)
                payload_copy.update({'job_tracker': jobs_tracker, self.object_tracked_name: object_tracked})
                logger.info(f"Creating job info object with payload: {payload_copy}")
                try:
                    job_info = self.job_info_model(
                        **payload_copy
                    )
                    job_info.save()
                    #self.enqueuer(job_info.id)
                    jobs_buffer.append(job_info.id)
                    msg=self.success_msg
                    success = True
                except Exception as e:
                    self.failed_message += ' Task enqueuer failed for {}: {} with exception: {}. '.format(
                        self.object_tracked_name,
                        objects_tracked,
                        e
                    )
                    logger.error(self.failed_message)
                    msg = self.failed_message
                    success = False #?
                    raise Exception(e)
            start_date = start_date + relativedelta(months=1)
        try:
            self.jobstracker_enqueuer(jobs_tracker.id)
            logger.info('JobTracker job was enqueued succesfully')
            for job_id in jobs_buffer: self.enqueuer(job_id)
        except Exception as e:
            msg = 'Failed enqueueing the JobsTracker job'
            logger.error(msg)
            raise (e)
        return msg

    @method_decorator(login_required)
    def get(self, request, *args, **kwargs):
        request.session['client_report_data'] = {}
        if hasattr(self, 'form_class'):
            data_form = self.form_class()
        else:
            data_form = ClientRevenueReportForm()
        return render(request,self.template_name,{"data_form":data_form})

    @method_decorator(login_required)
    def post(self,request, *args, **kwargs):
        if hasattr(self, 'form_class'):
            form = self.form_class(request.POST)
        else:
            form = ClientRevenueReportForm(request.POST)
        context = {}
        if form.is_valid():
            ######################################
            #Process as Get Request
            #dt = date(year,month,1)
            # jobs_tracker = ClientRevenueFullJobsTracker.objects.create(
            #     user_requested_email=user_email,
            # )
            # jobs_tracker = ClientRevenueFullJobsTracker.objects.get(id=16)
            # for billing_group in billing_group_objects:
            #     full_revenue_report = ClientRevenueFullReport(
            #         billing_group,
            #         dt,
            #         jobs_tracker
            #     ).create()
            # return full_revenue_report
            #######################################
            #Process via Backend
            start_date = date(
                int(form.cleaned_data.get('start_year')),
                int(form.cleaned_data.get('start_month')),
                1
            )
            end_date = date(
                int(form.cleaned_data.get('end_year')),
                int(form.cleaned_data.get('end_month')),
                1
            )
            try:
                user_email = request.user.email
            except:
                user_email = None
            msg = self._enqueue(start_date, end_date, user_email, form.cleaned_data)
            context['form'] = form
            context['msg'] = msg
            context.update(self.kwargs)
            return render(request,self.template_name,context)
        else:
            return render(request, self.template_name, {"data_form": form})


class PricingChangesDataMixin():


    def get_pricing_data(self, entity):
        """
        returns sorted dict with pricing changes, sorted by date
        entity: either a BillingGroup or a LaundryRoom
        """
        all_changes = {}
        extract_fields = lambda x: [str(getattr(x, field, None)) for field in fields]
        fields = ('equipment_type', 'cycle_type', 'detection_date', 'formatted_price')
        for room_extension in entity.laundryroomextension_set.all():
            pricing_history = room_extension.laundry_room.pricing_history.all()
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
                        if not current.detection_date in all_changes: all_changes[current.detection_date] = []
                        all_changes[current.detection_date].append('| '.join(current_data))
        return OrderedDict(sorted(all_changes.items(), key=operator.itemgetter(0)))