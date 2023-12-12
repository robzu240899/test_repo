import os
import logging
import threading
from typing import Sequence
from datetime import date
from django.core.mail import EmailMessage
from django.conf import settings
from django.template.loader import render_to_string
from queuehandler.job_creator import PricingChangesJobCreator, PricingJobsTrackerJobCreator
from queuehandler.utils import Aurora
from reporting.finance.clientreport.report import ClientNetRentReport
from revenue.models import LaundryTransaction
from .models import PricingPeriod, PricingReportJobInfo, PricingReportJobsTracker


logger = logging.getLogger(__name__)


class PricingReportEnqueuerThread(threading.Thread):

    def __init__(self, rooms, requester_mail, months, colors, *args, **kwargs):
        self.rooms = rooms
        self.email = requester_mail
        self.months = months
        self.colors = colors
        self.jobstracker_enqueuer = PricingJobsTrackerJobCreator.enqueue_job_tracker
        self.processor = PricingChangesJobCreator.create_report
        super(PricingReportEnqueuerThread, self).__init__(**kwargs)

    def run(self):
        try:
            report_jobs_tracker = PricingReportJobsTracker.objects.create(
                user_requested_email = self.email
            )
        except Exception as e:
            raise Exception("Failed creating JobTracker with Exception: {}".format(e))

        #Increase Aurora Capacity
        #Aurora.increase_aurora_capacity(n=4, sleep_time=120)
        Aurora.modify_aurora_cluster_min_capacity(min_capacity=64)

        for laundry_room in self.rooms:
            try:
                job_info = PricingReportJobInfo(
                    laundry_room=laundry_room,
                    months = self.months,
                    colors =  self.colors,
                    job_tracker=report_jobs_tracker
                )
                job_info.save()
                self.processor(job_info)
                msg=self.success_msg
            except Exception as e:
                msg = "On-demand job creation failed with Exception: e {}".format(e)
        try:
            self.jobstracker_enqueuer(report_jobs_tracker)
            logger.info('JobTracker job was enqueued succesfully')
        except Exception as e:
            logger.error('Failed enqueueing the JobsTracker job. Exception: {}'.format(e))
            raise Exception(e)


class ClientNetRentReportThread(threading.Thread):

    required_fields = (
        'email',
        'billing_groups',
        'start_year',
        'start_month',
        'end_year',
        'end_month',
        'metric'
    )

    def __init__(self, *args, **kwargs):
        for k,v in kwargs.items():
            if k in self.required_fields:
                setattr(self, k, v)
        assert all([hasattr(self, field) for field in self.required_fields])
        super(ClientNetRentReportThread, self).__init__()

    def run(self):
        rent_report = ClientNetRentReport(
            self.billing_groups,
            date(int(self.start_year), int(self.start_month), 1),
            date(int(self.end_year), int(self.end_month), 1),
            self.metric
        ).run()
        with open(rent_report) as f:
            report_content = f.read()
        email = EmailMessage(
            'Client Net Rent Report - {}'.format(self.metric),
            'Please see attached',
            settings.DEFAULT_FROM_EMAIL,
            self.email.split(',')
        )
        if rent_report:
            email.attach_file(rent_report)
        email.send(fail_silently=False)
        os.remove(rent_report)
        return True


class FirstTransactionThreadReport(threading.Thread):

    def __init__(self, rooms_queryset, filter_field: str, lookback : int, email : str) -> None:
        self.rooms = rooms_queryset
        self.filter_field = filter_field
        self.lookback = lookback
        self.results = dict()
        self.email = email
        super(FirstTransactionThreadReport, self).__init__()

    def _send_report(self):
        rendered = render_to_string(
            'first_transaction_report.html',
            {"room_results" : self.results}
        )
        email = EmailMessage(
            'First Transaction Report',
            rendered,
            settings.DEFAULT_FROM_EMAIL,
            self.email.split(',')
        )
        email.content_subtype = "html"
        email.send(fail_silently=False)
        return True

    def run(self):
        for room in self.rooms:
            filter_payload = {self.filter_field : room}
            q = LaundryTransaction.objects.filter(
                **filter_payload
            ).order_by('utc_transaction_time')[:self.lookback]
            self.results[room] = q
        if self.results: self._send_report()
        return True