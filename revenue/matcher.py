import time
import logging
from django.db import connection
from django.db.models import Q 
from datetime import date, timedelta
from revenue.models import FascardUser, LaundryTransaction, FailedTransactionMatch, CheckAttributionMatch
from .filterhelpers import StandardFilters 
from .enums import TransactionType, AddValueSubType


logger = logging.getLogger(__name__)


class WebBasedMatcherAdaptor(object):
    
    @classmethod
    def process(cls,laundry_transaction_id):
        start = time.time()
        WebBasedMatcher(laundry_transaction_id).match()
        end = time.time()
        logger.info(f"Executed WebBasedMatcherAdaptor in {end-start} seconds")


class MatchFilters(object):
    
    @classmethod 
    def add_web_based_filter(cls, qry):
        qry = qry.filter(transaction_type = TransactionType.ADD_VALUE, trans_sub_type = AddValueSubType.CREDIT_ON_WEBSITE)
        return qry
    

class GeneralMatcher():

    @classmethod
    def previous_failed_checker(cls, tx):
        try:
            previous_failed_match = FailedTransactionMatch.objects.filter(transaction_id=tx.pk).first()
            if previous_failed_match:
                previous_failed_match.solved=True
                previous_failed_match.save()
        except:
            pass

    @classmethod
    def get_related_transaction(cls, exclude_queryset=None, data_dict=None):
        if data_dict is None:
            return
        tx = LaundryTransaction.objects.filter(
            **data_dict
        ).exclude(exclude_queryset).order_by('-utc_transaction_time').first()
        return tx

    @classmethod
    def match_and_update(cls, tx, related_tx):
        tx.assigned_laundry_room = related_tx.laundry_room #TODO: update models to reflect this name 
        tx.assigned_local_transaction_time = tx.local_transaction_time #TODO: update models to reflect this name 
        tx.assigned_utc_transaction_time = tx.utc_transaction_time #TODO: update models to reflect this name 
        tx.save()
        cls.previous_failed_checker(tx)

    @classmethod
    def match(cls, tx):
        if tx.utc_transaction_time is None:
            return False

        matched = False
        query_dict = {}
        exclude_queryset = (Q(laundry_room__isnull=True) | Q(id=tx.id))
        related_tx = None
        #Try to get Previous first       
        query_dict['utc_transaction_time__lte'] = tx.utc_transaction_time
        if tx.fascard_user is None:
            query_dict['external_fascard_user_id'] = tx.external_fascard_user_id
        else:
            query_dict['fascard_user'] =  tx.fascard_user
        previous = cls.get_related_transaction(exclude_queryset, query_dict)
        if previous:
            related_tx = previous

        if related_tx is None:
            query_dict.pop('utc_transaction_time__lte')
            query_dict['utc_transaction_time__gte'] = tx.utc_transaction_time
            future = cls.get_related_transaction(exclude_queryset, query_dict)
            if future:
                related_tx = future
        
        if related_tx:
            cls.match_and_update(tx, related_tx)
            matched = True

        return matched


class WebBasedMatcher(object):
    
    def __init__(self,laundry_transaction_id):
        self.tx = LaundryTransaction.objects.get(pk = laundry_transaction_id)

    def previous_failed_checker(self, tx):
        try:
            previous_failed_match = FailedTransactionMatch.objects.filter(transaction_id=tx.pk).first()
            if previous_failed_match:
                previous_failed_match.solved=True
                previous_failed_match.save()
        except:
            pass
    
    def match(self):
        q = Q(laundry_room__isnull=True) | Q(fake=True) | StandardFilters.WEB_VALUE_ADD_Q
        if self.tx.utc_transaction_time:
            #TODO: ADD VALIDATION WHEN A USER DOES NOT EXISTS
            if self.tx.fascard_user is not None:
                previous_matched_tx = LaundryTransaction.objects.filter(
                    fascard_user = self.tx.fascard_user,
                    utc_transaction_time__lte = self.tx.utc_transaction_time
                    ).exclude(q).order_by('-utc_transaction_time').first()
            else:
                previous_matched_tx = LaundryTransaction.objects.filter(
                    external_fascard_user_id = self.tx.external_fascard_user_id,
                    utc_transaction_time__lte = self.tx.utc_transaction_time
                    ).exclude(q).order_by('-utc_transaction_time').first()
            if previous_matched_tx:
                self.tx.assigned_laundry_room = previous_matched_tx.laundry_room #TODO: update models to reflect this name 
                self.tx.assigned_local_transaction_time = self.tx.local_transaction_time #TODO: update models to reflect this name 
                self.tx.assigned_utc_transaction_time = self.tx.utc_transaction_time #TODO: update models to reflect this name 
                self.tx.save()
                self.previous_failed_checker(self.tx)
            else:
                if self.tx.fascard_user is not None:
                    future_matched_tx = LaundryTransaction.objects.filter(
                        fascard_user = self.tx.fascard_user,
                        utc_transaction_time__gte = self.tx.utc_transaction_time
                        ).exclude(q).order_by('utc_transaction_time').first()
                else:
                    future_matched_tx = LaundryTransaction.objects.filter(
                        external_fascard_user_id = self.tx.external_fascard_user_id,
                        utc_transaction_time__gte = self.tx.utc_transaction_time
                        ).exclude(q).order_by('utc_transaction_time').first()

                if future_matched_tx:
                    self.tx.assigned_laundry_room = future_matched_tx.laundry_room 
                    self.tx.assigned_local_transaction_time = self.tx.local_transaction_time 
                    self.tx.assigned_utc_transaction_time = self.tx.utc_transaction_time 
                    self.tx.save()
                    self.previous_failed_checker(self.tx)
                else:
                    FailedTransactionMatch.objects.create(transaction=self.tx)
        else:
            pass
            
class StandardMatcher(object):
    
    @classmethod 
    def match_all(cls):
        """
        Updates assigned_* variables
        """
        sql = '''
           UPDATE laundry_transaction
           SET assigned_laundry_room_id = laundry_room_id, assigned_local_transaction_time = local_transaction_time, assigned_utc_transaction_time = utc_transaction_time
           WHERE assigned_laundry_room_id is null AND NOT (transaction_type = %s AND trans_sub_type = %s)
        ''' % (TransactionType.ADD_VALUE, AddValueSubType.CREDIT_ON_WEBSITE)
        with connection.cursor() as cursor:
            cursor.execute(sql)

    @classmethod
    def match_tx(cls, tx):
        sql = '''
           UPDATE laundry_transaction
           SET assigned_laundry_room_id = laundry_room_id, assigned_local_transaction_time = local_transaction_time, assigned_utc_transaction_time = utc_transaction_time
           WHERE id = %s AND assigned_laundry_room_id is null AND NOT (transaction_type = %s AND trans_sub_type = %s)
        ''' % (tx.id, TransactionType.ADD_VALUE, AddValueSubType.CREDIT_ON_WEBSITE)
        with connection.cursor() as cursor:
            cursor.execute(sql)
            
            
class CheckAttributionMatcher(object):

    @classmethod
    def match(cls, start_date=None, end_date=None, queryset=None):
        if end_date is None:
            end_date = date.today()
        if start_date is None:
            start_date = end_date - timedelta(days=15)

        check_matches = list(CheckAttributionMatch.objects.all().values_list('external_fascard_id', flat=True))
        
        if queryset is None:
            queryset = LaundryTransaction.objects.filter(
                transaction_type = TransactionType.ADD_VALUE,
                trans_sub_type = AddValueSubType.CASH,
                utc_transaction_time__gte=start_date,
                utc_transaction_time__lte=end_date
            )

        queryset = queryset.exclude(external_fascard_id__in=check_matches)

        for tx in queryset:
            matched = GeneralMatcher().match(tx)
            if matched:
                try:
                    employee = FascardUser.objects.get(xxx_caution_fascard_user_id=tx.employee_user_id)
                except:
                    employee = None
                CheckAttributionMatch.objects.create(
                    external_fascard_id=tx.external_fascard_id,
                    comment='Check Re-Attribution',
                    employee = employee
                )
            else:
                FailedTransactionMatch(transaction=tx)


#TODO: Make sure this work and re attribute checks, then include them 
# in the low-level report and handle effects on metrics.

#NOTE: employee_user_id points to JUanyta
#NOTE: useraccountid 

            
#NOTE: employee_user_id FK to user_id on UserAccount spreadsheet.

            
            