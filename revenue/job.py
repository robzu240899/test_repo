import logging
import pytz
import time
from datetime import date, datetime, timedelta
from dateutil.relativedelta import relativedelta
from django.db import transaction
from django.db.models import Q
from django.db.models.fields.files import FieldFile
from fascard.api import FascardApi
from reporting.enums import LocationLevel
from reporting.metric.job import MetricsJobProcessor
from revenue.ingest import *
from revenue.enums import RefundChannelChoices
#from .authorize import AuthorizeManager
from .models import LaundryTransaction, RefundAuthorizationRequest, TransactionGaps, TransactionsPool, FascardUser


logger = logging.getLogger(__name__)

class TransactionsMetricsCompute():

    @classmethod
    def run(cls, tracker_model) -> bool:
        if isinstance(tracker_model.transaction_ids, FieldFile):
            bytes_obj = tracker_model.transaction_ids.read()
            ids_list = bytes_obj.decode('utf-8')
        else:
            ids_list = tracker_model.transaction_ids

        tx_ids = ids_list.split(',')
        success_counter = 0
        for tx_id in tx_ids:
            tx = LaundryTransaction.objects.get(external_fascard_id=tx_id)
            
            if tx.assigned_laundry_room is None:
                logger.error(
                    'Cannnot re-compute metrix for transaction with id: {}. Assigned Laundry Room is None'.format(
                        tx_id,
                    )
                )
                return False
            else:
                room = tx.assigned_laundry_room
            
            location_levels = {
                'room_level': {
                    'location_id':room.id, 
                    'location_level': LocationLevel.LAUNDRY_ROOM
                },
                'machine_level' : {
                    'location_id' : tx.machine_id,
                    'location_level' : LocationLevel.MACHINE
                }
            }

            try:
                billing_group = room.laundryroomextension_set.all().last().billing_group
                location_levels['billing_group'] = {
                    'location_id': billing_group.id, 
                    'location_level': LocationLevel.BILLING_GROUP
                }
            except:
                pass

            tx_date = tx.local_transaction_time.date()
            for location_level, data in location_levels.items():
                try:
                    MetricsJobProcessor.create_metric(
                    start_date=(tx_date - timedelta(days=1)),
                    end_date=(tx_date + timedelta(days=1)),
                    **data,
                    )
                except Exception as e:
                    print (e)
                    logger.error(
                        'Failed re-computing metrics for transaction with gap and id: {}. Error: {}'.format(
                            tx_id,
                            e
                        )
                    )
            success_counter += 1
        if success_counter == len(tx_ids):
            tracker_model.fully_processed = True
            tracker_model.save()
            tracker_model.refresh_from_db()
            logger.info("Finished closing gaps in Metrics due to transactions gaps")
        return tracker_model.fully_processed


class TransactionsGapFiller(TransactionsMetricsCompute):
    model = TransactionGaps

    @classmethod
    def run_job(cls):
        q = cls.model.objects.filter(fully_processed=False)
        for tracker in q:
            cls.run(tracker)

class TransactionsPoolProcessor(TransactionsMetricsCompute):
    model = TransactionsPool

    @classmethod
    def run_job(cls):
        q = cls.model.objects.filter(fully_processed=False)
        for tracker in q:
            cls.run(tracker)


class BaseRefundQueueProcessor():

    @classmethod
    def _process(cls, refund_request):
        refunded, msg, data = refund_request.complete()
        if refunded:
            refund_request.wait_for_settlement = False
            refund_request.save()
            logger.info(
                "Successfully proccessed refund_request from queue processor {}".format(
                    refund_request.id
                )
            )
            refund_request.send_email_notification(['completed'])
        else:
            logger.error('Failed refunding refund_request with ID: {}. {}'.format(
                refund_request.id,
                msg
            ))


class CompleteAuthorizeRefunds(BaseRefundQueueProcessor):
    """
    Job to process refund requests that contain transactions that have not benn
    settled by Authorize
    """

    @classmethod
    def run(cls):
        #UTC Nightly run runtime: 23:45
        pytz_timezone = pytz.timezone('America/New_York') #Greatest city in the world
        current_time = datetime.now().astimezone(pytz_timezone)
        if current_time.hour == 23:
            tomorrow = current_time.date() + relativedelta(days=1)
            tomorrow_midnight = datetime.combine(tomorrow, datetime.min.time())
            delta = (tomorrow_midnight - current_time.replace(tzinfo=None)).seconds
            if delta < 1000:
                time.sleep(delta)
        q = RefundAuthorizationRequest.objects.filter(approved=True, wait_for_settlement=True)
        #the query below covers the case when credit card refund jobs eligible for immediate refunding that were 
        #enqueued and sent to sqs failed. We reprocess them here
        wait_for_settlement_query = Q(approved=True, wait_for_settlement=True)
        extra_cc_refund_query = (
            Q(
                approved=True,
                wait_for_settlement=False,
                refund_channel=RefundChannelChoices.AUTHORIZE,
                refund_object__isnull=True
            )
        )
        final_query = RefundAuthorizationRequest.objects.filter(Q(wait_for_settlement_query | extra_cc_refund_query))
        for refund_request in final_query:
            #youngest = refund_request.transactions.all().order_by('assigned_utc_transaction_time')
            with transaction.atomic():
                cls._process(refund_request)


class CompleteEnqueuedCreditCardRefund(BaseRefundQueueProcessor):

    @classmethod
    def run(cls, request_id):
        refund_request = RefundAuthorizationRequest.objects.get(id=request_id)
        if not refund_request.approved: return
        cls._process(refund_request)


class eCheckReload():

    def __init__(self):
        self.fascard_sync = FascardUserAccountSync(1)
        self.authorize_manager = AuthorizeManager()

    def check_user(self, subscription: FascardUser) -> bool:
        fascard_user = subscription.customer_profile.fascard_user
        self.fascard_sync.sync_users(
            update=True,
            start_from_id=(int(fascard_user.fascard_user_account_id)-1),
            end_at_id = int(fascard_user.fascard_user_account_id)
            )
        fascard_user.refresh_from_db()
        if fascard_user.balance < subscription.balance_minimum_treshold:
            try:
                self.authorize_manager.echeck_recharge_customer_profile(
                    subscription.customer_profile.authorize_customer_id,
                    subscription.balance_recharge
                )
            except Exception as e:
                logger.error(
                    f"Failed to reload balance for user: {fascard_user}. FascardUserID: {fascard_user.fascard_user_account_id}",
                    exc_info=True
                )
                return False
            return True
        return False

    @classmethod
    def run_as_job(cls):
        echeck_manager = eCheckReload()
        subscriptions  = eCheckSubscription.objects.all()
        for subscription in subscriptions:
            echeck_manager.check_subscription(subscription)
        #TODO
        #NOTE: This is somehow wrong. Since an user may have multiple subscriptions
        #you may end up charging him as many times as she has subscriptions.
        #Instead, what you wanna do is charge only based on that user's latest subscription
        return True