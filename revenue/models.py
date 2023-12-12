import time
import logging
from datetime import datetime, timedelta
from decimal import Decimal
from django.db.models import Sum
from django.conf import settings
from django.contrib.auth.models import User
from django.core.mail import EmailMessage
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.template.loader import render_to_string
from storages.backends.s3boto3 import S3Boto3Storage
from roommanager.models import LaundryRoom,Slot,Machine,LaundryGroup
from roommanager.enums import MachineType
from upkeep.enums import WorkOrderStatus
from revenue import enums
from .refund import FascardRefund, CheckRefund, AuthorizeDotNetRefund, WipeBonus, AdditionalBonus


logger = logging.getLogger(__name__)


class FascardUser(models.Model):  
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=1000,null=True,blank=True)
    addr_1 = models.CharField(max_length=1000,null=True,blank=True)
    addr_2 = models.CharField(max_length=1000,null=True,blank=True)
    city = models.CharField(max_length=200,null=True,blank=True)
    state = models.CharField(max_length=200,null=True,blank=True)
    zip = models.CharField(max_length=200,null=True,blank=True)
    mobile_phone = models.CharField(max_length=200,null=True,blank=True)
    office_phone = models.CharField(max_length=200,null=True,blank=True)
    email_address = models.CharField(max_length=1000,null=True,blank=True)
    comments = models.CharField(max_length=1000,null=True,blank=True)
    language = models.CharField(max_length=200,null=True,blank=True)
    notify_cycle_complete = models.CharField(max_length=200,null=True,blank=True)
    fascard_creation_date = models.DateTimeField(null=True,blank=True)
    fascard_last_activity_date = models.DateTimeField(null=True,blank=True)
    balance = models.FloatField(null=True,blank=True)
    bonus = models.FloatField(null=True,blank=True)
    discount = models.FloatField(null=True,blank=True)
    free_starts = models.FloatField(null=True,blank=True)
    status = models.CharField(max_length=200,null=True,blank=True)
    is_employee = models.NullBooleanField()
    loyalty_points = models.FloatField(null=True,blank=True)
    ballance_spent = models.FloatField(null=True,blank=True)
    bonus_spent = models.FloatField(null=True,blank=True)
    free_starts_spent = models.FloatField(null=True,blank=True)
    reload_method = models.FloatField(null=True,blank=True)
    reload_balance = models.FloatField(null=True,blank=True)
    reload_bonus = models.FloatField(null=True,blank=True)
    cash_spent = models.FloatField(null=True,blank=True)
    credit_card_spent = models.FloatField(null=True,blank=True)
    user_group_id = models.IntegerField(null=True,blank=True)
    last_location_id = models.IntegerField(null=True,blank=True)
    xxx_caution_fascard_user_id = models.IntegerField(null=True,blank=True)
    fascard_user_account_id = models.IntegerField()
    laundry_group = models.ForeignKey(LaundryGroup, on_delete=models.SET_NULL, null=True)
    coupons = models.CharField(max_length=200,null=True,blank=True)

    class Meta:
        managed = True
        unique_together = ('laundry_group','fascard_user_account_id')
        db_table = 'fascard_user'
        
    @classmethod
    def get_name_from_fascardid(cls, employee_id):
        try:
            ins = FascardUser.objects.get(xxx_caution_fascard_user_id=employee_id)
            name = getattr(ins, 'name', None)
        except:
            name = None
        return name

    def __str__(self):
        return self.name if self.name is not None else ''

    @property
    def fascard_url(self):
        return 'https://admin.fascard.com/86/loyaltyaccounts?recid={}&page=1'.format(self.fascard_user_account_id)


class LaundryTransaction(models.Model):
    id = models.AutoField(primary_key=True)
    external_fascard_id = models.CharField(unique=True,max_length=65)
    fascard_record_id = models.CharField(max_length=68)
    fascard_code = models.IntegerField(null=True,blank=True) #Location fascard ID?
    laundry_room = models.ForeignKey(LaundryRoom, on_delete=models.SET_NULL, null=True,blank=True)
    slot = models.ForeignKey(Slot, on_delete=models.SET_NULL, null=True,blank=True)
    machine = models.ForeignKey(Machine, on_delete=models.SET_NULL, null=True,blank=True)
    web_display_name = models.CharField(max_length=100,null=True,blank=True)
    first_name = models.CharField(max_length=100, null=True)
    last_name = models.CharField(max_length=100, null=True)
    local_transaction_date = models.DateField(blank=True,null=True)
    utc_transaction_date = models.DateField(blank=True,null=True)
    transaction_type = models.CharField(max_length=100, blank=True)
    credit_card_amount = models.DecimalField(max_digits=10,decimal_places=2,blank=True,null=True)
    cash_amount = models.DecimalField(max_digits=10,decimal_places=2,blank=True,null=True)
    balance_amount = models.DecimalField(max_digits=10,decimal_places=2,blank=True,null=True)
    last_four = models.CharField(max_length=4,null=True, blank=True)
    card_number = models.CharField(max_length=10,null=True,blank=True)
    card_type = models.IntegerField(null=True,blank=True)
    utc_transaction_time = models.DateTimeField(blank=True,null=True)
    local_transaction_time = models.DateTimeField(blank=True,null=True)
    external_fascard_user_id = models.IntegerField(null=True,blank=True) #TODO check if employee_user_id is still needed
    fascard_user = models.ForeignKey(FascardUser,null=True,blank=True, on_delete=models.SET_NULL)
    dirty_name = models.CharField(max_length=200,null=True,blank=True)
    loyalty_card_number = models.CharField(max_length=255,null=True,blank=True)
    authorizedotnet_id = models.CharField(max_length=255,null=True,blank=True)
    additional_info = models.CharField(max_length=255,null=True,blank=True)
    root_transaction_id = models.CharField(max_length=255,null=True,blank=True)
    bonus_amount = models.DecimalField(max_digits=10,decimal_places=2,blank=True,null=True)
    new_balance = models.DecimalField(max_digits=10,decimal_places=2,blank=True,null=True)
    new_bonus = models.DecimalField(max_digits=10,decimal_places=2,blank=True,null=True)
    new_free_starts = models.DecimalField(max_digits=10,decimal_places=2,blank=True,null=True)
    new_loyalty_points = models.DecimalField(max_digits=10,decimal_places=2,blank=True,null=True)
    loyalty_points = models.DecimalField(max_digits=10,decimal_places=2,blank=True,null=True)
    employee_user_id = models.CharField(max_length=255,null=True,blank=True)
    trans_sub_type = models.CharField(max_length=255,null=True,blank=True)
    free_starts = models.DecimalField(max_digits=10,decimal_places=2,blank=True,null=True)
    unfunded_amount = models.DecimalField(max_digits=10,decimal_places=2,blank=True,null=True)
    sys_config_id = models.CharField(max_length=255,null=True,blank=True)
    assigned_laundry_room = models.ForeignKey(LaundryRoom, on_delete=models.SET_NULL, null=True, blank=True, related_name='assigned_room')  #Holds what we say the laundry room is, different primarily for web based transactions
    assigned_utc_transaction_time = models.DateTimeField(blank=True,null=True)     #Holds what we say the utc transaction time is, different primarily for web based transactions
    assigned_local_transaction_time = models.DateTimeField(blank=True,null=True)   #Holds what we say the local transaction time, different primarily for web based transactions
    is_refunded = models.BooleanField(default=False)
    fake = models.BooleanField(default=False)
  
    class Meta:
        managed = True
        db_table = 'laundry_transaction'
        indexes = [
            models.Index(fields=['local_transaction_date', 'local_transaction_time', 'fascard_record_id']),
        ]

    def __str__(self):
        return f"Transaction. Fascard ID {self.fascard_record_id}"

    @property
    def employee_adding_funds(self):
        return FascardUser.get_name_from_fascardid(self.employee_user_id)

    def get_total_refunds(self):
        total_refunds = self.refunds.all().aggregate(total=Sum('amount')).get('total')
        total_refunds = total_refunds or Decimal('0.0')
        return total_refunds

    def get_trans_type_verbose(self):
        if self.transaction_type:
            return enums.TransactionType.MAP.get(int(self.transaction_type), 'Unknown')
        else:
            return 'Unknown'

    def get_trans_subtype_verbose(self):
        if self.trans_sub_type:
            return enums.AddValueSubType.MAP.get(int(self.trans_sub_type), 'Unknown')
        else:
            return 'Unknown'

    def update_meter(self, asset):
        meter = getattr(asset, 'meter', None)
        if not meter:
            return
        try:
            meter.transactions_counter +=1
            meter.save()
        except Exception as e:
            logger.error(
                "Could not update transanctions meter for {} id {}. Exception: {}".format(
                    asset.__class__.__name__,
                    asset.id,
                    e
                )
            ) 

    def save(self, *args, **kwargs):
        if not self.pk:
            new = True
        else:
            new = False
        super(LaundryTransaction, self).save(*args, **kwargs)
        if new and int(self.transaction_type)==100:
            if self.machine:
                self.update_meter(self.machine)
                try:
                    if self.machine.machine_type == MachineType.DRYER and self.laundry_room:
                        meter = getattr(self.laundry_room, 'meter', None)
                        if meter:
                            meter.dryers_start_counter += 1
                            meter.save()
                except Exception as e:
                    logger.info("Failed updating dryer starts counter on tx with id: {} - {}".format(
                        self.id, e)
                    )
            if self.slot:
                self.update_meter(self.slot.get_current_card_reader())


class RefundAuthorizationRequest(models.Model):
    approved = models.BooleanField(default=False)
    rejected = models.BooleanField(default=False)
    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True,blank=True)
    approval_time = models.DateTimeField(blank=True, null=True)
    aggregator_param = models.CharField(max_length=100, blank=True, null=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True,blank=True, related_name='created_by')
    description = models.TextField(max_length=500, blank=True, null=True)
    external_fascard_user_id = models.IntegerField(blank=True, null=True)
    fascard_user = models.ForeignKey(FascardUser, on_delete=models.SET_NULL, blank=True, null=True)
    transaction = models.ForeignKey(LaundryTransaction,on_delete=models.SET_NULL, null=True,blank=True)
    refund_channel = models.IntegerField(choices=enums.RefundChannelChoices.CHOICES,max_length=255)
    refund_type_choice = models.CharField(choices=enums.RefundTypeChoices.CHOICES, default=enums.RefundTypeChoices.TRANSACTION, max_length=255)
    refund_amount = models.DecimalField(max_digits=6, decimal_places=2)
    wait_for_settlement = models.BooleanField(default=False)
    check_recipient = models.CharField(max_length=50, blank=True, null=True)
    check_recipient_address = models.CharField(max_length=50, blank=True, null=True)
    wipe_bonus_amount = models.BooleanField(default=False)
    charge_damage_to_landlord = models.BooleanField(default=False)
    force_charge_landlord_choice = models.BooleanField(default=False)
    additional_bonus_amount = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=0,
        blank=True,
        null=True,
        validators = [MaxValueValidator(Decimal("100.00")), MinValueValidator(Decimal("0.00"))]
    )
    work_order_status = models.CharField(max_length=30, blank=True, null=True, choices=WorkOrderStatus.CHOICES)
    cashout_type = models.CharField(max_length=30, choices=enums.FascardBalanceType.CHOICES, blank=True, null=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return "${} refund for transaction fascard ID: {}".format(
            self.refund_amount,
            self.transaction.fascard_record_id)

    def wipe_bonus(self, refund_obj):
        tx = refund_obj.transaction
        bonus_amount = tx.bonus_amount
        if bonus_amount and bonus_amount > 0:
            try:
                WipeBonus().wipe_bonus(tx)
            except:
                logger.info("Failed wiping bonus amount: {} for user with fascard id: {}")

    def _add_additional_bonus(self):
        try:
            response = AdditionalBonus(self).add()
        except Exception as e:
            logger.error("Failed Adding Additional Funds to refund request with id: {}".format(self.id))
            raise Exception(e)

    def _get_capture_transaction(self):
        transaction = self.transaction
        assert transaction.last_four
        name = transaction.dirty_name
        six_hours_later = transaction.local_transaction_time + timedelta(hours=6)
        #we adjust the lower bound for the query in order to account for the edge cases
        #when a tx of type 20 comes in a few seconds earlier than the tx of type 2
        adjusted_lower_bound = transaction.local_transaction_time - timedelta(seconds=120)
        filter_payload = {
            'last_four' : transaction.last_four,
            'local_transaction_time__gte' : adjusted_lower_bound,
            'local_transaction_time__lte' : six_hours_later,
            'transaction_type' : '20',
            'credit_card_amount__gte' : self.refund_amount
        }
        parent_tx = LaundryTransaction.objects.filter(**filter_payload).first()
        return parent_tx

    def complete(self):
        extra_data = {}
        self.err_msg = None
        refund_obj = getattr(self, 'refund_object', None)
        if refund_obj and refund_obj.refund_completed:
            return (True, '', {})
        if int(self.refund_channel) == enums.RefundChannelChoices.FASCARD_ADJUST:
            refund_obj = FascardRefund().refund(self)
        elif int(self.refund_channel) == enums.RefundChannelChoices.CHECK:
            refund_manager = CheckRefund()
            refund_obj = refund_manager.refund(self)
            extra_data = {'checks' : refund_manager.zip_file_content}
        elif int(self.refund_channel) == enums.RefundChannelChoices.AUTHORIZE:
            refund_obj = AuthorizeDotNetRefund().refund(self)
        else:
            raise Exception('Unknown Refund Type')
        if self.wipe_bonus_amount:
            self.wipe_bonus(refund_obj)
        if self.additional_bonus_amount:
            time.sleep(30)
            self._add_additional_bonus()
        return (refund_obj, self.err_msg, extra_data)

    def _fetch_to_list(self):
        to = []
        if self.created_by and self.created_by.email:
            to.append(self.created_by.email)
        if self.approved_by and self.approved_by.email:
            to.append(self.approved_by.email)
        return to


    def send_email_notification(self, notification_types: list):
        content_type = None
        context = {'obj' : self}
        admin_url = "{}/admin/revenue/refundauthorizationrequest/{}/change/".format(settings.MAIN_DOMAIN,self.pk)
        notifications_db = {
            'new' : {
                'subject' : 'New Refund Authorization Request',
                'extra_context' : {'admin_url' : admin_url},
                'to' : list(set(self._fetch_to_list() + settings.DEFAULT_TO_EMAILS))
            },
            'approved' : {
                'subject' : 'Refund Authorization Request *Approved*',
                'to' : self._fetch_to_list(),
            },
            'rejected' : {
                'subject' : 'Refund Authorization Request *Rejected*',
                'to' : self._fetch_to_list(),
            },
            'completed' : {
                'subject' : 'Refund Completed Successfully',
                'to' : self._fetch_to_list(),
                'extra_context' : {'admin_url' : admin_url, 'completed' : True},
            }
        }

        email_payload = {'subject' : [], 'to': [], }
        for notification_type in notification_types:
            assert notification_type in notifications_db.keys()
            email_payload['subject'].append(notifications_db[notification_type]['subject'])
            email_payload['to'] += notifications_db[notification_type]['to']
            if 'extra_context' in notifications_db[notification_type]:
                for k,v in notifications_db[notification_type]['extra_context'].items():
                    if not k in context: context[k] = v
        email_payload['subject'] = '. '.join(email_payload['subject'])
        email_payload['to'] = list(set(email_payload['to']))
        body = render_to_string("refund_authorization_notification.html", context)
        message = EmailMessage(subject=email_payload['subject'], body=body, from_email=settings.DEFAULT_FROM_EMAIL, to=email_payload['to'])
        if hasattr(self, 'extra_data') and "checks" in self.extra_data:
            zip_file_name = 'RenderedRefundChecks-{}'.format(datetime.now())
            message.attach('{}.zip'.format(zip_file_name), self.extra_data.get("checks"))
        message.content_subtype = "html"
        message.send(fail_silently=False)

    #TODO: make atomic
    def save(self, *args, **kwargs):
        its_new = False
        notify_action = False
        refund_completed = False
        self.extra_data = {}
        if self.pk:
            ins = RefundAuthorizationRequest.objects.get(id=self.pk)
            if self.approved and not ins.approved:
                notify_action = True
                if not self.wait_for_settlement:
                    #Process via SQS credit card refunds that can be immediately refunded
                    if int(self.refund_channel) == enums.RefundChannelChoices.AUTHORIZE:
                        #enqueue job
                        from queuehandler.job_creator import RefundsEnqueuer
                        RefundsEnqueuer.enqueue_refund_request(self.pk)
                    else:
                        refund_obj, msg, self.extra_data = self.complete()
                        if refund_obj:
                            self.approval_time = datetime.now()
                            if refund_obj.refund_completed:
                                refund_completed = True
                        else:
                            raise Exception('Unsuccessful refund aproval: {}'.format(msg))
            elif self.rejected and not ins.rejected:
                notify_action = True
        else:
            fascard_user = None
            if self.external_fascard_user_id:
                try:
                    fascard_user = FascardUser.objects.filter(
                        fascard_user_account_id=self.external_fascard_user_id).first()
                except:
                    fascard_user = None
            its_new = True
            self.fascard_user = fascard_user
        super(RefundAuthorizationRequest, self).save(*args, **kwargs)
        try:
            if its_new: self.send_email_notification(['new'])
            if notify_action:
                if self.rejected:
                    self.send_email_notification(['rejected'])
                elif self.approved:
                    notifications = ['approved']
                    if refund_completed:
                        notifications.append('completed')
                    self.send_email_notification(notifications)
        except Exception as e:
            if self.pk:
                logger.info(f'Refund Auth Request with pk: {self.pk} was approved but email notification failed. {e}', exc_info=True)
        return True


class Refund(models.Model):
    id = models.AutoField(primary_key=True)
    amount = models.DecimalField(max_digits=10,decimal_places=2,blank=True,null=True)
    refund_channel = models.IntegerField(choices=enums.RefundChannelChoices.CHOICES,max_length=255)
    timestamp = models.DateTimeField(auto_now_add=True,null=True,blank=True)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True,blank=True)
    fascard_user_account_id = models.IntegerField(null=True,blank=True)
    transaction = models.ForeignKey(LaundryTransaction, on_delete=models.SET_NULL, null=True,blank=True,related_name='refunds')
    refund_file = models.FileField(blank=True, null=True, storage=S3Boto3Storage(bucket='refunds-files'))
    authorization_request = models.OneToOneField(RefundAuthorizationRequest, related_name='refund_object', on_delete=models.SET_NULL, null=True,blank=True)
    refund_completed = models.BooleanField(default=False)

    class Meta:
        managed = True
        db_table = 'refund'


class FailedLaundryTransactionIngest(models.Model):
    id = models.AutoField(primary_key=True)
    external_fascard_id = models.CharField(null=True,blank=True,max_length=255)
    timestamp = models.DateTimeField(auto_now_add=True)
    row = models.TextField()
    error_message = models.TextField(null=True,blank=True)
    resolved = models.BooleanField(default=False)
    
    class Meta:
        managed = True
        db_table = 'failed_laundry_transaction_ingest'   
    
class FailedTransactionMatch(models.Model):
    transaction = models.ForeignKey(LaundryTransaction, on_delete=models.SET_NULL, null=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    solved = models.BooleanField(default=False)
    comment = models.TextField(blank=True, null=True)

    def __str__(self):
        return "Transaction Date: {}. Failed Match date: {}".format(
            self.transaction.utc_transaction_time,
            self.timestamp)


class CheckAttributionMatch(models.Model):
    external_fascard_id = models.CharField(unique=True,max_length=65) #Transaction Fascard ID
    comment = models.TextField(blank=True, null=True)
    employee = models.ForeignKey(FascardUser, null=True, blank=True, on_delete=models.SET_NULL)
    

class TransactionGaps(models.Model):
    transaction_ids = models.TextField(max_length=1000)
    number_of_records = models.IntegerField()
    timestamp = models.DateTimeField(auto_now_add=True)
    fully_processed = models.BooleanField(default=False)


class TransactionsPool(models.Model):
    """
        Used to keep track of the most currently ingested transactions that can be used
        to compute metrics on a given day.
    """
    transaction_ids = models.FileField(
        blank=True,
        null=True,
        storage=S3Boto3Storage(bucket='transaction-ids-pool')
    )
    number_of_records = models.IntegerField()
    processed_transactions_counter = models.IntegerField(default=0)
    timestamp = models.DateTimeField(auto_now_add=True)
    fully_processed = models.BooleanField(default=False)

    def save(self, *args, **kwargs):
        if self.pk:
            if self.processed_transactions_counter == self.number_of_records:
                self.fully_processed = True
        super(TransactionsPool, self).save(*args, **kwargs)


class AuthorizeCustomerProfile(models.Model):
    loyalty_card_number = models.CharField(max_length=50)
    fascard_user = models.ForeignKey(FascardUser, null=True, blank=True, on_delete=models.SET_NULL)
    authorize_customer_id = models.CharField(max_length=50)
    timestamp = models.DateTimeField(auto_now_add=True, blank=True, null=True)


class eCheckSubscription(models.Model):
    customer_profile = models.ForeignKey(AuthorizeCustomerProfile, null=True, blank=True, on_delete=models.SET_NULL)
    balance_minimum_treshold = models.DecimalField(max_digits=6, decimal_places=2)
    balance_recharge = models.DecimalField(max_digits=6, decimal_places=2)
    confirmed = models.BooleanField(default=False)
    #authorize_payment_profile_id = 

#TODO
#Need to have logic to cancel a customer's subscription?.
#Need to filter out somehow subscriptions that are no longer active so we dont charge those users anymore.
#Should this be an interface? Should they have access to their active subscriptions?
#

class TxLastIDLog(models.Model):
    timestamp = models.DateTimeField(auto_now_add=True)
    last_id = models.CharField(max_length=30)