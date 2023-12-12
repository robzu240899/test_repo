import logging
from django import forms
from datetime import date
from dateutil.relativedelta import relativedelta
from django.db import models
from django.forms import ValidationError
from reporting.enums import DurationType, LocationLevel, MetricType, ClientRentReportMetrics, TransactionReportType, SortParameters
from reporting.models import BillingGroup
from revenue.models import FascardUser
from roommanager.models import LaundryRoom
from .enums import TimeUnits
from .processors import InternalReportProcessor, ClientRevenueReportProcessor, ClientFullRevenueReportProcessor, \
RentPaidProcessor, TransactionsReportProcessor
from .utils import EventBridgeHandler


logger = logging.getLogger(__name__)


# class ReportType():
#     INTERNAL_REPORT = 'internal_report'
#     CLIENT_REPORT = 'client_report'
#     CLIENT_FULL_LOWLEVEL_REPORT = 'client_full_lowlevel_report'

#     CHOICES = (
#         (INTERNAL_REPORT, INTERNAL_REPORT),
#         (CLIENT_REPORT, CLIENT_REPORT),
#         (CLIENT_FULL_LOWLEVEL_REPORT, CLIENT_FULL_LOWLEVEL_REPORT),
#     )

#     choices_map = {
#         INTERNAL_REPORT : InternalReportConfig,
#     }


class EventRule(models.Model):
    name = models.CharField(max_length=150)
    arn = models.TextField()
    target_id = models.CharField(max_length=100, null=True, blank=True)
    description = models.CharField(max_length=100, null=True, blank=True)


class JobProcessingMixin():
    def process_as_job(self):
        raise NotImplementedError

    def fetch_job_dates(self):
        #fetch start and end dates based on relative date
        end_date = date.today() + relativedelta(days=1)
        start_date = end_date - relativedelta(**{self.time_units: self.time_units_lookback})
        return start_date, end_date
        pass

    def _handle_updates(self, *args, **kwargs):
        if self.pk: print ("exists")


class AbstractConfig(models.Model):
    time_units_lookback = models.IntegerField(default=1)
    time_units = models.CharField(max_length=30, choices=TimeUnits.CHOICES, default=TimeUnits.MONTHS)
    event_rule = models.OneToOneField(EventRule, on_delete=models.CASCADE, blank=True, null=True)
    email = models.CharField(max_length=100)
    cron_expression = models.CharField(max_length=20, help_text='Cron expression must be UTC, 6 fields long / No seconds needed')

    def save(self, *args, **kwargs):
        logger.info("Save method invoked")
        msg = ''
        success = True
        self._handle_updates(*args, **kwargs)
        if self.pk:
            instance = self.__class__.objects.get(id=self.pk)
            logger.info(f"Current cron expr: {instance.cron_expression}. New cron expr: {self.cron_expression}")
            if self.cron_expression != instance.cron_expression:
                logger.info(f"Updating {self.event_rule.name} from {instance.cron_expression} to {self.cron_expression}")
                description = instance.event_rule.description or ''
                response, msg, success = EventBridgeHandler()._create_event_rule(
                    self.event_rule.name, 
                    description,
                    self.cron_expression) #_create_event_rule creates or updates the rule
        if success: super().save(*args, **kwargs)
        else: raise forms.ValidationError(msg)

    class Meta:
        abstract = True


class InternalReportConfig(JobProcessingMixin, AbstractConfig):
    """
        saves config for an internal revenue report
    """
    time_grouping = models.CharField(max_length=20, choices=DurationType.CHOICES)
    location_grouping = models.CharField(max_length=20, choices=LocationLevel.CHOICES)
    revenue_rule = models.CharField(max_length=50, choices=MetricType.CHOICES)
    rooms = models.ManyToManyField(
        LaundryRoom,
        related_name='rooms',
        blank=True,
    )
    include_all_rooms = models.BooleanField(default=False)
    billing_groups = models.ManyToManyField(
        BillingGroup,
        blank=True,
    )
    include_all_billing_groups = models.BooleanField(default=False)
    active_only = models.BooleanField(default=False)
    exclude_zero_rows = models.BooleanField(default=False)
    sort_by = models.CharField(max_length=20, choices=SortParameters.CHOICES)
    email = models.CharField(max_length=100)

    def process_as_job(self):
        start_date, end_date = self.fetch_job_dates()
        rooms_ids = [room.id for room in self.rooms.all()]
        bgs_ids = [bg.id for bg in self.billing_groups.all()]
        if self.include_all_rooms:
            rooms_ids = [room.id for room in LaundryRoom.objects.all()]
            bgs_ids = []
        if self.include_all_billing_groups:
            bgs_ids = [bg.id for bg in BillingGroup.objects.all()]
            rooms_ids = []
        internal_report_payload = {
            'metric_type' : self.revenue_rule,
            'duration_type' : self.time_grouping,
            'start_date' : start_date,
            'end_date' : end_date,
            'location_level' : self.location_grouping,
            'laundry_room_ids' : rooms_ids,
            'billing_group_ids' : bgs_ids,
            'active_only' : self.active_only,
            'exclude_zero_rows' : self.exclude_zero_rows,
            'email' : self.email,
            'delivery_method': 'email',
            'sort_parameter': self.sort_by
        }
        InternalReportProcessor.process(internal_report_payload)


class ClientRevenueReportConfig(JobProcessingMixin, AbstractConfig):
    billing_groups = models.ManyToManyField(
        BillingGroup,
        blank=True,
    )
    pdf_generation = models.BooleanField(default=False)
    html_generation = models.BooleanField(default=False)
    include_zero_rows = models.BooleanField(default=False)
    include_inactive_billing_groups = models.BooleanField(default=False)

    # def save(self, *args, **kwargs):
    #     self._handle_updates(*args, **kwargs)

    def process_as_job(self):
        logger.info(f"Processing ClientRevenueReportConfig ({self.pk})")
        start_date, end_date = self.fetch_job_dates()
        bgs = self.billing_groups.all()
        if not bgs:
            if self.include_inactive_billing_groups: bgs = BillingGroup.objects.all()
            else: bgs = BillingGroup.objects.filter(is_active=True)
        payload = {
            'start_date' : start_date,
            'end_date' : end_date,
            'billing_group' : bgs,
            'pdf_generation' : self.pdf_generation,
            'html_generation' : self.html_generation,
            'include_zero_rows' : self.include_zero_rows,
            'email' : self.email
        }
        ClientRevenueReportProcessor().process(payload)


class ClientFullRevenueReportConfig(JobProcessingMixin, AbstractConfig):
    billing_groups = models.ManyToManyField(
        BillingGroup,
        blank=True,
    )
    include_zero_rows = models.BooleanField(default=False)

    # def save(self, *args, **kwargs):
    #     self._handle_updates(*args, **kwargs)

    def process_as_job(self):
        logger.info(f"Processing ClientFullRevenueReportConfig ({self.pk})")
        start_date, end_date = self.fetch_job_dates()
        bgs = self.billing_groups.all()
        if not bgs: bgs = BillingGroup.objects.all()
        payload = {
            'start_date' : start_date,
            'end_date' : end_date,
            'billing_group' : bgs,
            'email' : self.email
        }
        ClientFullRevenueReportProcessor().process(payload)


class RentPaidReportConfig(JobProcessingMixin, AbstractConfig):
    billing_groups = models.ManyToManyField(
        BillingGroup,
        blank=True,
    )
    metric = models.CharField(max_length=50, choices=ClientRentReportMetrics.CHOICES)

    # def save(self, *args, **kwargs):
    #     self._handle_updates(*args, **kwargs)

    def process_as_job(self):
        start_date, end_date = self.fetch_job_dates()
        bgs = self.billing_groups.all()
        if not bgs: bgs = BillingGroup.objects.all()
        payload = {
            'billing_groups' : bgs,
            'email' : self.email,
            'metric': self.metric,
            'start_year' : start_date.year,
            'start_month' : start_date.month,
            'end_year' :  end_date.year,
            'end_month' : end_date.month
        }
        RentPaidProcessor().process(payload)


class TransactionReportConfig(JobProcessingMixin, AbstractConfig):
    employees = models.ManyToManyField(
        FascardUser,
        blank=True
    )
    report_type = models.CharField(
        max_length=100,
        choices=TransactionReportType.CHOICES
    )
    last_activity_lookback = models.IntegerField(blank=True, null=True)
    last_activity_lookback_time_units = models.CharField(max_length=30, choices=TimeUnits.CHOICES, blank=True, null=True)

    # def save(self, *args, **kwargs):
    #     self._handle_updates(*args, **kwargs)

    def process_as_job(self):
        start_date, end_date = self.fetch_job_dates()        
        
        current_employees = self.employees.all()
        if current_employees:
            employees = current_employees
        else:            
            employees = FascardUser.objects.filter(is_employee = True)
            if self.last_activity_lookback_time_units and self.last_activity_lookback:
                activity_end_date = date.today() + relativedelta(days=1)
                activity_start_date = activity_end_date - relativedelta(**{self.last_activity_lookback_time_units: self.last_activity_lookback})
                employees = employees.filter(
                    fascard_last_activity_date__gte = activity_start_date,
                    fascard_last_activity_date__lte = activity_end_date
                )
        payload = {
            'start_date' : start_date,
            'end_date' : end_date,
            'email' : self.email,
            'employees' : employees,
            'report_type' : self.report_type,
        }
        TransactionsReportProcessor().process(payload)