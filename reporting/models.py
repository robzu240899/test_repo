import logging
from datetime import date
from pyexpat import model
from dateutil.relativedelta import relativedelta
from datetime import datetime
from django.conf import settings
from django.contrib.auth.models import User
from django.core.mail import EmailMessage
from django.db import models
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.core.files.storage import FileSystemStorage
from django.utils import timezone
from storages.backends.s3boto3 import S3Boto3Storage
from reporting import enums
from reporting.work_orders import MeterRaiseWorkOrder
from revenue.models import FascardUser
from roommanager.models import LaundryRoom, EquipmentType, MaintainxZipCodeRoom, Machine
from maintainx.api import MaintainxAPI


logger = logging.getLogger(__name__)
tmp_storage = FileSystemStorage(location=settings.TMP_STORAGE_ROOT)


class StoredFascardToken(models.Model):
    session_token = models.CharField(max_length=300)
    saved_at = models.DateTimeField(auto_now_add=True)


class Client(models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField(max_length=1000, blank=True, null=True)
    address1 = models.CharField(max_length=100, blank=True)
    address2 = models.CharField(max_length=100, blank=True)
    phone = models.CharField(max_length=15, blank=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class Lessee(models.Model):
    name = models.CharField(max_length=100)

    def __str__(self):
        return self.name


'''Represents buildings that are billed as one unit'''
class BillingGroup(models.Model):
    id = models.AutoField(primary_key=True)
    display_name = models.CharField(max_length=200,unique=True)
    schedule_type  = models.CharField(choices=enums.RevenueSplitScheduleType.CHOICES,max_length=1000)
    min_compensation_per_day = models.FloatField(null=True,blank=True)
    aces_collects_cash = models.BooleanField(default = False) #TODO ask Daniel waht default should be
    payment_method = models.CharField(choices=enums.BGSPaymentMethods.CHOICES, max_length=100, default=enums.BGSPaymentMethods.UNKNOWN)
    right_of_first_refusal = models.BooleanField(default = False)
    allow_cashflow_refunds_deduction = models.BooleanField(default = True)
    client = models.ForeignKey(Client, on_delete=models.SET_NULL, null=True)
    additional_insureds = models.CharField(max_length=100, blank=True, null=True)
    vendor_code = models.CharField(max_length=40, blank=True, null=True)
    lessee = models.ForeignKey(Lessee, on_delete=models.SET_NULL, blank=True, null=True)
    operations_start_date = models.DateField(blank=True, null=True)
    max_meter_raises = models.IntegerField(blank=True, null=True)
    lease_term_start = models.DateField(blank=True, null=True)
    lease_term_duration_months = models.IntegerField(blank=True, null=True, help_text='0 for month-to-months')
    lease_term_duration_days = models.IntegerField(blank=True, null=True, help_text='Leave blank for month-to-months')
    lease_term_end = models.DateField(blank=True, null=True)
    lease_term_auto_renew = models.BooleanField(default=False)
    lease_term_auto_renew_length = models.IntegerField(blank=True, null=True, help_text='In Months')
    is_active = models.BooleanField(default=True)
    description = models.TextField(blank=True, null=True)

    class Meta:
        managed = True
        db_table = 'billing_group'
        ordering = ['display_name']

    def __str__(self):
        return self.display_name

    def _calculate_lease_end_date(self, start, duration):
        months = duration[0] if duration[0] else 0
        days = duration[1] if duration[1] else 0
        end_date = start + relativedelta(months=int(months), days=int(days))
        return end_date - relativedelta(days=1) #this step was explicitly required by Daniel

    def save(self, *args, **kwargs):
        done = False
        if self.lease_term_duration_months == 0 and not self.lease_term_duration_days:
            done = True
        if not done and self.lease_term_end is None:
            lease_duration = [self.lease_term_duration_months, self.lease_term_duration_days]
            if not any(lease_duration):
                self.lease_term_end = date(2099,12,1)
            else:
                self.lease_term_end = self._calculate_lease_end_date(self.lease_term_start, lease_duration)
            done = True
        if not done and self.pk:
            ins = BillingGroup.objects.get(id=self.pk)
            if self.lease_term_end != ins.lease_term_end:
                delta = relativedelta(self.lease_term_end, self.lease_term_start)
                self.lease_term_duration_months = (delta.years * 12) + delta.months
                self.lease_term_duration_days = delta.days
            else:
                duration_fields = ('lease_term_duration_months', 'lease_term_duration_days')
                new_duration = [getattr(self, f) for f in duration_fields]
                old_duration = [getattr(ins, f) for f in duration_fields]
                if new_duration != old_duration:
                    self.lease_term_end = self._calculate_lease_end_date(self.lease_term_start, new_duration)
        super(BillingGroup, self).save(*args, **kwargs)

    def get_client_name(self):
        try:
            client_name = self.client.name
        except:
            client_name = None
        return client_name


class Payee(models.Model):
    name = models.CharField(max_length=50)
    percentage_share = models.DecimalField(
        max_digits=4, 
        decimal_places=2, 
        validators=[MinValueValidator(1), MaxValueValidator(100)])
    billing_group = models.ForeignKey(
        BillingGroup,
        verbose_name='BillingGroup',
        on_delete=models.CASCADE,
        null=True)

class MeterRaise(models.Model):
    billing_group = models.ForeignKey(BillingGroup, on_delete=models.CASCADE)
    scheduled_date = models.DateField()
    #NOTE: Decided to use a textfield instead of dollars amount
    #because there are many different cases in which dollars might not be sufficient.
    raise_limit = models.TextField(
        verbose_name='Raise Limit (Dollars amount)',
    )

    def __str__(self):
        return f"Billing Group: {self.billing_group}. Sch. Date: {self.scheduled_date}"

    def save(self, *args, **kwargs):
        new = False
        if not self.pk: new = True
        super(MeterRaise, self).save(*args, **kwargs)
        if new:
            meter_raise = MeterRaise.objects.get(id=self.pk) 
            MeterRaiseWorkOrder._sync_meter_raises_as_work_order(meter_raise)
            MeterRaiseWorkOrder._sync_meter_raises_notifications_as_work_orders(meter_raise)


class UpcomingMeterRaiseNotification(models.Model):
    timestamp = models.DateTimeField(auto_now_add=True)
    meter_raise = models.ForeignKey(MeterRaise, on_delete=models.CASCADE, related_name='notification')
    completed = models.BooleanField(default=False)

    def __str__(self):
        legend = " Not Raised" if self.completed is False else " Raised"
        return str(self.meter_raise) + legend


class AutoRenewHistory(models.Model):
    billing_group = models.ForeignKey(BillingGroup, on_delete=models.CASCADE, related_name='autorenew_history')
    timestamp = models.DateTimeField(auto_now_add=True)
    lease_start_date = models.DateField()
    lease_end_date = models.DateField()
    original = models.BooleanField()


class BillingGroupEmailAddress(models.Model):
    email = models.EmailField()
    billing_group = models.ForeignKey(BillingGroup, on_delete=models.CASCADE)


class ClientEmailAddress(models.Model):
    email = models.EmailField()
    billing_group = models.ForeignKey(Client, on_delete=models.CASCADE)


class LegalStructureChoice(models.Model):
    name = models.CharField(max_length=100)

    def __str__(self):
        return self.name or 'N/A'


class BuildingTypeChoice(models.Model):
    name = models.CharField(max_length=100)

    def __str__(self):
        return self.name or 'N/A'


class LaundryRoomExtension(models.Model):
    id = models.AutoField(primary_key=True)
    laundry_room = models.ForeignKey(LaundryRoom, on_delete=models.CASCADE, unique=True)
    billing_group = models.ForeignKey(BillingGroup, on_delete=models.SET_NULL, null=True,blank=True)
    num_units = models.IntegerField(null=True,blank=True)
    square_feet_residential = models.IntegerField(null=True,blank=True)
    has_elevator = models.NullBooleanField()
    is_outdoors = models.NullBooleanField()
    laundry_in_unit = models.NullBooleanField()
    legal_structure = models.ForeignKey(
        LegalStructureChoice,
        on_delete=models.SET_NULL,
        blank=True,
        null=True
    )
    building_type = models.ForeignKey(
        BuildingTypeChoice,
        on_delete = models.SET_NULL,
        blank = True,
        null = True,
    )

    class Meta:
        managed = True
        db_table = 'laundry_room_extension'
        ordering = ['laundry_room__display_name']


    def __str__(self):
        return (self.laundry_room.display_name + ": Billing Extension")


class RevenueSplitRule(models.Model):
    id = models.AutoField(primary_key=True)
    billing_group = models.ForeignKey('BillingGroup', on_delete=models.CASCADE)
    revenue_split_formula = models.CharField(choices=enums.RevenueSplitFormula.CHOICES,max_length=1000)
    base_rent = models.FloatField(null=True,blank=True, verbose_name="Base rent")
    landloard_split_percent = models.FloatField(null=True,blank=True, verbose_name="Landlord revenue split proportion")
    breakpoint = models.FloatField(null=True,blank=True, verbose_name="Breakpoint | on revenue split deals")
    start_gross_revenue = models.IntegerField(null=True, blank=True, verbose_name="Gross Revenue | rule split effectuation amount")
    end_gross_revenue = models.IntegerField(null=True,blank=True, verbose_name="Gross Revenue | rule split termination amount")
    min_comp_per_day = models.DecimalField(max_digits=10,decimal_places=2,blank=True,null=True, verbose_name="Minimum Compensation per Day")
    start_date = models.DateField(null=True,blank=True, verbose_name="Date | rule split effectuation date")
    end_date = models.DateField(null=True,blank=True, verbose_name="Date | rule split termination date")

    def __str__(self):

        label_chunks = [str(self.billing_group) + " ~~~~ ",
                        str(self.revenue_split_formula),
                        " || base_rent:" + str(self.base_rent),
                        " || breakpoint:" + str(self.breakpoint),
                        " || landlord_share:" + str(self.landloard_split_percent),
                        " || revenue_effectuation:" + str(self.start_gross_revenue),
                        " || revenue_termination:" + str(self.end_gross_revenue),
                        " || date_effectuation:" + str(self.start_date),
                        " || date_termination:" + str(self.end_date)
                        ]

        return "".join(label_chunks)

    class Meta:
        managed = True
        db_table = 'revenue_split_rule'
        ordering = ['billing_group__display_name']


    def get_associated_rules(self):
        '''returns all rules associated with the laundry room or billing group, depending on what is appropriate'''
        rules = RevenueSplitRule.objects.filter(billing_group=self.billing_group)
        rules = [r for r in rules]
        if self not in rules:
            rules.append(self)
        return rules

    def clean(self):
        st = self.billing_group.schedule_type
        if st == enums.RevenueSplitScheduleType.TIME:
            pass
            #self.__clean_time()
            #NOTE: Deprecated in favor of cleaning at the form level in admin.py
        elif st == enums.RevenueSplitScheduleType.GROSS_REVENUE:
            self.__clean_gross_revenue()
        elif st == enums.RevenueSplitScheduleType.CONSTANT:
            self.__clean_constant()
        else:
            txt = "RevenueSplitScheduleType %s not supported" % st
            raise ValidationError((txt))

        if self.revenue_split_formula == enums.RevenueSplitFormula.GENERAL_BREAKPOINT:
            self.__clean_general_breakpoint()
        # elif self.revenue_split_formula == enums.RevenueSplitFormula.NATURAL_BREAKPOINT:
        #     self.__clean_natural_breakpoint()
        elif self.revenue_split_formula == enums.RevenueSplitFormula.PERCENT:
            self.__clean_percent()
        else:
            raise ValidationError(("RevenueSplitFormula not supported"))

    def __clean_general_breakpoint(self):
        if self.base_rent is None:
            raise ValidationError("General breakpoint requires base rent")
        if self.landloard_split_percent is None:
            raise ValidationError("General breakpoint requires landloard split percentage.")
        if self.breakpoint is None:
            raise ValidationError("General breakpoint requires breakpoint")

    def __clean_natural_breakpoint(self):
        if self.base_rent is None:
            raise ValidationError("Natural breakpoint requires base rent")
        if self.landloard_split_percent is None:
            raise ValidationError("Natural breakpoint requires landloard split percentage.")
        if self.breakpoint is not None:
            raise ValidationError("Natural breakpoint's breakpoint must be null")

    def __clean_percent(self):
        if self.base_rent is not None:
            raise ValidationError("Percent rule's min payment must be null")
        if self.landloard_split_percent is None:
            raise ValidationError("Percent rule requires landloard split percent")
        if self.breakpoint is not None:
            raise ValidationError("Percent rule's breakpoint must be null")

    def __clean_time(self):
        """
        Deprecated in favor of cleaning at the form level in admin.py
        """
        if not self.start_date:
           raise ValidationError("Start date must be filled in for time based rules.")
        if self.start_date and self.end_date and self.end_date<self.start_date:
            raise ValidationError(("Start date must be less than end date"))
        associated_rules = [x for x in self.get_associated_rules()]
        associated_rules.sort(key=lambda x: x.start_date)
        num_rules = len(associated_rules)
        for i in range(num_rules):
            #only the last rule can have a null end time
            if i != num_rules-1 and associated_rules[i].end_date is None:
                raise ValidationError(('Only the last revenue rule may have a null end time'))
            #make sure there is no overlap or gaps
            if i > 0:
                if associated_rules[i].start_date != associated_rules[i-1].end_date:
                    raise ValidationError(("Time based rules must have no gaps and not overlap."))
        super(RevenueSplitRule, self).clean()

    def __clean_gross_revenue(self):
        if self.start_gross_revenue is None:
            raise ValidationError(("Start gross revenue may not be null."))
        if self.start_gross_revenue and self.end_gross_revenue and self.start_gross_revenue>=self.end_gross_revenue:
            raise ValidationError(("Start gross revenue must be less than end gross revenue"))
        if self.start_date:
            raise ValidationError("Start date must be null")
        if self.end_date:
            raise ValidationError("End date must be null")

        if self.start_gross_revenue is not None:
            self.start_gross_revenue = int(self.start_gross_revenue)
        if self.end_gross_revenue is not None:
            self.end_gross_revenue = int(self.end_gross_revenue)

        associated_rules = [x for x in self.get_associated_rules()]
        associated_rules.sort(key=lambda x: x.start_gross_revenue)
        num_rules = len(associated_rules)
        for i in range(num_rules):
            #non null end revenue (unless this is the last rule)
            if i != num_rules-1 and associated_rules[i].end_gross_revenue is None:
                raise ValidationError("Only the last revenue rule may have a null end gross revenue value")
            #check no overlap/gaps:
            if i > 0:
                if associated_rules[i-1].end_gross_revenue != associated_rules[i].start_gross_revenue:
                    raise ValidationError("Revenue based rules must have no gaps or overlap")
        super(RevenueSplitRule, self).clean()

    def __clean_constant(self):
        if self.start_gross_revenue is not None:
            raise ValidationError(("Start gross revenue must be null for constant revenue schedules"))
        if self.end_gross_revenue is not None:
            raise ValidationError(("End gross revenue must be null for constant revenue schedules"))
        if self.start_date is not None:
            raise ValidationError(("Start date must be null for constant revenue schedules"))
        if self.end_date is not None:
            raise ValidationError(("End date must be null for constant revenue schedules"))

        associated_rules = self.get_associated_rules()
        if len(associated_rules) > 1:
            raise ValidationError("Constant schedules may have only one revenue split rule")

    def save(self,*args,**kwargs):
        self.clean()
        super(RevenueSplitRule,self).save(*args,**kwargs)

class ExpenseType(models.Model):
    id = models.AutoField(primary_key=True)
    display_name = models.CharField(max_length=100,unique=True)
    description = models.CharField(max_length=1000,null=True,blank=True)
    expense_type = models.CharField(max_length=100,choices=enums.ExpenseType.CHOICES)

    class Meta:
        managed = True
        db_table = 'expense_type'
        ordering = ['display_name']

    def __str__(self):
        return self.display_name

class BillingGroupExpenseTypeMap(models.Model):
    id = models.AutoField(primary_key=True)
    billing_group = models.ForeignKey(BillingGroup, on_delete=models.SET_NULL, null=True)
    expense_type = models.ForeignKey(ExpenseType, on_delete=models.CASCADE)
    default_amount = models.FloatField()
    pass_to_client = models.BooleanField(default=False)

    class Meta:
        managed = True
        db_table = 'billing_group_expense_type_map'
        unique_together = ['billing_group','expense_type']
        ordering = ['billing_group__display_name']

    def __str__(self):
        return "%s %s" % (getattr(self.billing_group, 'display_name', 'None Billingroup'), getattr(self.expense_type, 'display_name', None))


class NonRecurrentExpense(models.Model):
    amount = models.DecimalField(max_digits=6, decimal_places=2)
    expense_type = models.CharField(max_length=100)
    description = models.TextField(max_length=500)
    laundry_room = models.ForeignKey(LaundryRoom, on_delete=models.SET_NULL, null=True, blank=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='created_non_recurrent_expenses')
    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='approved_non_recurrent_expenses')
    pass_to_client_share = models.BooleanField(default=False)
    approved = models.BooleanField(default=False)
    rejected = models.BooleanField(default=False)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        permissions = [
            ('approve_or_reject', "Can approve or reject a Non-recurrent expense")
        ]

    def __str__(self, *args, **kwargs):
        fields = ['expense_type', 'laundry_room']
        if all([(getattr(self, field) is not None and getattr(self, field) != '') for field in fields]):
            return "%s at %s" % tuple([getattr(self, field) for field in fields])
        else:
            return super(NonRecurrentExpense, self).__str__(*args, **kwargs)


class MetricsCache(models.Model):
    id = models.AutoField(primary_key=True)
    metric_type = models.CharField(choices=enums.MetricType.CHOICES,max_length=255,null=True,blank=True)
    start_date = models.DateField(blank=True,null=True)
    duration = models.CharField(choices=enums.DurationType.CHOICES,max_length=255,null=True,blank=True)
    location_id = models.BigIntegerField()
    location_level = models.CharField(choices=enums.LocationLevel.CHOICES,max_length=255,null=True,blank=True)
    result = models.DecimalField(max_digits=12,decimal_places=2,null=True,blank=True)
    calcuation_time = models.DateTimeField(auto_now=True)
    needs_processing = models.BooleanField(default=False)
    ripe_date = models.DateField(blank=True, null=True)

    class Meta:
        managed = True
        db_table = 'metrics_cache'
        unique_together = ['metric_type','start_date','duration','location_level','location_id']
        indexes = [
            models.Index(fields=['start_date', 'location_id', 'duration']),
        ]


class MetricsComputationWatcher(models.Model):
    expected = models.IntegerField()
    scheduled = models.IntegerField(default=0)
    location_level = models.CharField(choices=enums.LocationLevel.CHOICES,max_length=255,null=True,blank=True)
    start_date = models.DateField(blank=True,null=True)
    duration = models.CharField(choices=enums.DurationType.CHOICES,max_length=255,null=True,blank=True)


class PriceHistory(models.Model):
    id = models.AutoField(primary_key=True)
    laundry_room = models.ForeignKey(LaundryRoom, on_delete=models.SET_NULL, null=True)
    price_date = models.DateField()
    machine_type = models.CharField(max_length = 255)
    cycle_type = models.CharField(max_length = 255)
    price = models.DecimalField(decimal_places = 3, max_digits = 10)

    class Meta:
        managed = True
        db_table = 'price_history'
        unique_together = ('laundry_room', 'price_date', 'machine_type', 'cycle_type')

    def __str__(self):
        txt = 'Laundry Room: %s | Date: %s |  Machine Type %s | Cycle Type %s | Price %s' % (self.laundry_room.display_name, self.price_date,
                            self.machine_type, self.cycle_type, self.price)
        return txt

class CustomPriceHistory(models.Model):
    laundry_room = models.ForeignKey(LaundryRoom, on_delete=models.SET_NULL, null=True, related_name='pricing_history')
    equipment_type = models.ForeignKey(EquipmentType, on_delete=models.SET_NULL, null=True)
    detection_date = models.DateField()
    cycle_type = models.CharField(max_length=50)
    price = models.IntegerField()
    timestamp = models.DateTimeField(auto_now_add=True, blank=True, null=True)

    def __str__(self):
        return 'Equipment Type: {} | Cycle Type: {} | Date: {} | Price: {}'.format(
            self.equipment_type,
            self.cycle_type,
            self.detection_date,
            self.price
        )

    def get_price(self):
        """
        Convert price in cents to price in dollars with to decimal numbers
        """
        result = self.price/100.0
        return ("%.2f" % result)

    @property
    def formatted_price(self):
        return self.get_price()

    #Used to differentiate  a real cycle form a placeholder cycle
    #in the pricing history report template
    @property
    def is_placeholder(self):
        return False

    # def save(self):
    #     if not self.pk:
    #         existing_price_history = CustomPriceHistory.objects.filter(
    #             laundry_room=self.laundry_room
    #             equipment_type=self.equipment_type,
    #             cycle_type=self.cycle_type
    #         ).order_by('-detection_date').first()
    #         if existing_price_history:
    #             existing_price_history.is_active = False
    #             existing_price_history.save()
    #     super()

class BaseJobTracker(models.Model):
    jobs_processed = models.IntegerField(blank=True, null=True, default=0)
    full_report_delivered = models.BooleanField(default=False)
    user_requested_email = models.CharField(max_length=200)

    class Meta:
        abstract = True


class PricingPeriod(models.Model):
    laundry_room = models.ForeignKey(LaundryRoom, on_delete=models.SET_NULL, null=True, related_name='pricing_periods')
    start_date = models.DateField()
    end_date = models.DateField(blank=True, null=True)
    timestamp = models.DateTimeField(auto_now_add=True, blank=True, null=True)
    reason = models.CharField(max_length=100, blank=True, null=True)

    def __str__(self):
        return 'Pricing Period for: {} | Start date: {}'.format(
            self.laundry_room,
            self.start_date
        )

class PricingReportJobsTracker(BaseJobTracker):
    """
    Model to track when all the pricing report jobs are done processing
    and to save the final generated file
    """
    full_report_file = models.FileField(blank=True, null=True, storage=S3Boto3Storage(bucket='pricing-change-reports'))
    timestamp = models.DateTimeField(default=timezone.now)

class PricingReportJobInfo(models.Model):
    """
    Save the info required to process the job that generates a pricing report
    """
    laundry_room = models.ForeignKey(LaundryRoom, on_delete=models.SET_NULL, blank=True, null=True, related_name='pricing_reports')
    #report_pickle_file = models.FileField(blank=True, null=True, storage=S3Boto3Storage(bucket='pricing-changes-pickles'))
    report_html_file = models.FileField(blank=True, null=True, storage=S3Boto3Storage(bucket='pricing-changes-singles'))
    job_tracker = models.ForeignKey(PricingReportJobsTracker, on_delete=models.SET_NULL, related_name='jobs_being_tracked', blank=True, null=True)
    months = models.IntegerField(blank=True, null=True)
    colors = models.BooleanField(default=False)
    timestamp = models.DateTimeField(auto_now_add=True)

#previously ClientRevenueJobsTracker
class ClientRevenueFullJobsTracker(BaseJobTracker):
    """
    Model to track the processing of the jobs belonging to a single report.
    When all the reports are done being processed, the tracker will call the
    email and S3 upload functions to deliver the report.

    Part of full low-level client revenue report
    """

    def __str__(self):
        return "ClientReportJobsTracker {}".format(self.id)


class ClientRevenueFullReportJobInfo(models.Model):
    """
    Full low-level client revenue report job info
    """
    month = models.IntegerField()
    year = models.IntegerField()
    billing_group = models.ForeignKey(BillingGroup, on_delete=models.SET_NULL, null=True)
    job_tracker = models.ForeignKey(ClientRevenueFullJobsTracker, on_delete=models.SET_NULL, related_name='jobs_being_tracked', null=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    def get_requestor_email(self):
        if self.job_tracker:
            return self.job_tracker.user_requested_email
        else:
            return None

class ClientRevenueJobsTracker(BaseJobTracker):
    """
    High-level basic revenue report tracker
    """
    def __str__(self):
        return f"ClientRevenueJobs Report tracker: {self.id}"


class ClientRevenueReportJobInfo(models.Model):
    """
    High-level basic revenue report job info
    """
    month = models.IntegerField()
    year = models.IntegerField()
    billing_group = models.ForeignKey(BillingGroup, on_delete=models.SET_NULL, null=True)
    job_tracker = models.ForeignKey(ClientRevenueJobsTracker, on_delete=models.SET_NULL, related_name='jobs_being_tracked', null=True)
    pdf_generation = models.BooleanField(default=False)
    html_generation = models.BooleanField(default=True)
    include_zero_rows = models.BooleanField(default=False)
    fully_processed = models.BooleanField(default=False)
    invoice_amount = models.DecimalField(blank=True, null=True, max_digits=10, decimal_places=2)
    errored = models.BooleanField(default=False)
    error = models.TextField(blank=True, null=True)


class ClientReportFullStoredFile(models.Model):
    """
    Report files generated for full low-level client revenue report
    """
    laundry_room_extension = models.ForeignKey(LaundryRoomExtension, on_delete=models.SET_NULL, null=True)
    report_file = models.FileField(blank=True, null=True, storage=S3Boto3Storage(bucket='tmp-revenue-report-files'))
    report_type = models.CharField(
        max_length=30,
        choices=enums.ClientLowLevelReportType.CHOICES,
        default = enums.ClientLowLevelReportType.TRANSACTIONS
    )
    jobs_tracker = models.ForeignKey(ClientRevenueFullJobsTracker, on_delete=models.SET_NULL, null=True, related_name='generated_files')


class ClientReportBasicStoredFile(models.Model):
    """
    Report files generated for basic high-level client revenue report
    """
    billing_group = models.ForeignKey(BillingGroup, on_delete=models.SET_NULL, null=True)
    report_file = models.FileField(blank=True, null=True, storage=S3Boto3Storage(bucket='tmp-revenue-report-files'))
    file_type = models.CharField(
        max_length=20,
        choices=enums.ClientReportFileType.CHOICES,
        default=enums.ClientReportFileType.HTML
    )
    jobs_tracker = models.ForeignKey(ClientRevenueJobsTracker, on_delete=models.SET_NULL, null=True, related_name='generated_files')
    job_info = models.ForeignKey(ClientRevenueReportJobInfo, on_delete=models.SET_NULL, null=True)

#TODO Could make all jobs tracker inherit from a base model
class TimeSheetsReportJobTracker(BaseJobTracker):

    def __str__(self):
        return f"TimeSheets Report tracker: {self.id}"


class TimeSheetsReportJobInfo(models.Model):
    start_date = models.DateField()
    end_date = models.DateField()
    employee = models.ForeignKey(FascardUser,null=True,blank=True,on_delete=models.SET_NULL)
    job_tracker = models.ForeignKey(TimeSheetsReportJobTracker, on_delete=models.SET_NULL, related_name='jobs_being_tracked', null=True)


class TimeSheetsReportStoredFile(models.Model):
    employee = models.ForeignKey(FascardUser,null=True,blank=True,on_delete=models.SET_NULL)
    report_file = models.FileField(blank=True, null=True, storage=S3Boto3Storage(bucket='timesheets-reports'))
    file_type = models.CharField(
        max_length=20,
        choices=enums.ClientReportFileType.CHOICES,
        default=enums.ClientReportFileType.HTML
    )
    jobs_tracker = models.ForeignKey(TimeSheetsReportJobTracker, on_delete=models.SET_NULL, null=True, related_name='generated_files')


class OutOfOrderReportLog(models.Model):
    successfully_sent = models.BooleanField(default=False)
    timestamp = models.DateTimeField(auto_now_add=True)


class AnomalyDetectionJobTracker(BaseJobTracker):
    timestamp = models.DateTimeField(auto_now_add=True)


class AnomalyDetectionJobInfo(models.Model):
    machine = models.ForeignKey(Machine, on_delete=models.CASCADE)
    msg = models.CharField(max_length=300, blank=True, null=True)
    date_range = models.CharField(max_length=300, blank=True, null=True)
    days_window = models.CharField(max_length=300, blank=True, null=True)
    anomaly_detected = models.BooleanField(default=False)
    timestamp = models.DateTimeField(auto_now_add=True)
    processed = models.BooleanField(default=False)
    job_tracker = models.ForeignKey(AnomalyDetectionJobTracker, related_name='jobs_being_tracked', on_delete=models.CASCADE)
    report_file_graphs = models.FileField(blank=True, null=True,storage=S3Boto3Storage(bucket='anomaly-detection-report-graphs')) #field created to store html graphs on s3 bucket to be accessed on the email report