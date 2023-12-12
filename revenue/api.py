import itertools
import operator
from datetime import datetime, timedelta
from django.db.models import Q, Sum
from django.db import transaction as django_transaction
from rest_framework import status
from rest_framework.decorators import api_view, authentication_classes,\
    permission_classes
from rest_framework.response import Response
from rest_framework import generics
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from revenue.serializers import LaundryTransactionSerializer
from revenue.models import LaundryTransaction, Refund
from revenue.refund import RefundFactory
from revenue import enums


class TransactionList(APIView):


    def post(self, request, format=None):
        queryset = LaundryTransaction.objects.all()
        if request.data.get('laundry_room', None):
            queryset = queryset.filter(laundry_room=request.data.get('laundry_room')['id'])
        if request.data.get('machine', None):
            queryset = queryset.filter(machine=request.data.get('machine')['id'])
        if request.data.get('slot', None):
            queryset = queryset.filter(slot=request.data.get('slot')['id'])
        if request.data.get('start_time', None):
            queryset = queryset.filter(local_transaction_time__gte=request.data.get('start_time'))
            if request.data.get('time_window', None):
                finish_time = datetime.strptime(request.data.get('start_time'), "%Y-%m-%d %H:%M:%S")
                finish_time += timedelta(hours=request.data.get('time_window'))
                queryset = queryset.filter(local_transaction_time__lte=finish_time)
        if request.data.get('payment_type', None):
            payment_type = request.data.get('payment_type', None)
            if payment_type == enums.PaymentType.CREDIT:
                queryset = queryset.filter(credit_card_amount__gt=0)
            if payment_type == enums.PaymentType.LOYALTY:
                queryset = queryset.filter(Q(cash_amount__gt=0) | Q(balance_amount__gt=0))
            if payment_type == enums.PaymentType.EITHER:
                queryset = queryset.filter(Q(credit_card_amount__gt=0) | Q(cash_amount__gt=0) | Q(balance_amount__gt=0))
        if request.data.get('activity_type', None):
            activity_type = request.data.get('activity_type', None)
            if activity_type == enums.ActivityType.MACHINE_START:
                queryset = queryset.filter(transaction_type=enums.TransactionType.VEND)
            if activity_type == enums.ActivityType.VALUE_ADD:
                queryset = queryset.filter(transaction_type=enums.TransactionType.ADD_VALUE)
            if activity_type == enums.ActivityType.EITHER:
                queryset = queryset.filter(Q(transaction_type=enums.TransactionType.ADD_VALUE) | Q(transaction_type=enums.TransactionType.VEND))
        if request.data.get('loyalty_card_number', None):
            queryset = queryset.filter(loyalty_card_number=request.data.get('loyalty_card_number')) 
        queryset = queryset.order_by('utc_transaction_time')[:50]
        serializer = LaundryTransactionSerializer(queryset, many=True)
        return Response(serializer.data)


def group_refund_block(transactions):
    """
    Group transactions into refund blocks
    """
    for transaction in transactions:
        if transaction.credit_card_amount > 0:
            transaction.payment_processing_type = enums.PaymentType.CREDIT
            if transaction.authorizedotnet_id:
                transaction.card_number = str(transaction.authorizedotnet_id) + str(transaction.laundry_room.laundry_group.id)
            else:
                raise Exception("No Authroize.Net ID found for transaction %s" % transaction.id)
        if transaction.balance_amount > 0:
            transaction.payment_processing_type = enums.PaymentType.LOYALTY
            if transaction.loyalty_card_number:
                transaction.card_number = str(transaction.loyalty_card_number) + str(transaction.laundry_room.laundry_group.id)
            else:
                raise Exception("No Loyalty Card found for transaction %s" % transaction.id)

    get_attr = operator.attrgetter('payment_processing_type', 'card_number')
    refund_blocks = [list(g) for k, g in itertools.groupby(sorted(transactions, key=get_attr), get_attr)]
    return refund_blocks

def check_eligible_to_be_refunded(transactions, payment_processing_type, authorizedotnet_id_group):
    """
    Check refund blocks if they can be refunded or not
    """
    # All of the laundry transactions have transaction type 2 or 100
    if transactions.exclude(Q(transaction_type=enums.TransactionType.ADD_VALUE) | Q(transaction_type=enums.TransactionType.VEND)).count() > 0:
        return False
    # None of the laundry transactions have been refunded already
    if transactions.filter(is_refunded=True).count() > 0:
        return False

    # No laundry transaction with the same Authorize.net transaction id has been refunded
    if payment_processing_type == enums.PaymentType.CREDIT:
        if LaundryTransaction.objects.filter(authorizedotnet_id__in=authorizedotnet_id_group, is_refunded=True).count() > 0:
            return False
    return True

@api_view(['POST'])
@permission_classes([IsAuthenticated]) 
def refund(request):
    """
    Refund transaction.
    """
    
    #TODO: add in exception handling.
    
    if request.method == 'POST':
        res = {
            'error_transactions': []
        }
        transactions = request.data.get('transactions', [])
        laundry_transactions = LaundryTransaction.objects.filter(id__in=transactions)
        refund_blocks = group_refund_block(laundry_transactions)

        for refund_block in refund_blocks:
            if len(refund_block) > 0:
                transactions_of_block = [transaction.id for transaction in refund_block]
                payment_processing_type_of_block = refund_block[0].payment_processing_type
                card_number_of_block = refund_block[0].card_number
                authorizedotnet_id_group = [transaction.authorizedotnet_id for transaction in refund_block]
                laundry_transactions = LaundryTransaction.objects.select_for_update().filter(id__in=transactions_of_block)
                # check if block valid to be refunded
                if check_eligible_to_be_refunded(laundry_transactions, payment_processing_type_of_block, authorizedotnet_id_group):
                    refund = Refund()
                    if payment_processing_type_of_block == enums.PaymentType.CREDIT:
                        refund.refund_type = enums.RefundType.AUTHORIZEDOTNET
                        refund.amount = laundry_transactions.aggregate(total=Sum('credit_card_amount'))['total']
                        
                    if payment_processing_type_of_block == enums.PaymentType.LOYALTY:
                        refund.refund_type = enums.RefundType.FASCARD
                        refund.amount = laundry_transactions.aggregate(total=Sum('balance_amount'))['total']

                    # process refunding
                    try:
                        with django_transaction.atomic():
                            if refund.refund_type == enums.RefundType.AUTHORIZEDOTNET:
                                refund_factory = RefundFactory(enums.RefundType.AUTHORIZEDOTNET)
                                for transaction in refund_block:
                                    refund_factory.refunder.refund(transaction.authorizedotnet_id, transaction.credit_card_amount, transaction.last_four)
                            elif refund.refund_type == enums.RefundType.FASCARD:
                                #Check to make sure fascard user is the same for all transactions
                                fascard_users = set([transaction.fascard_user] for transaction in refund_block)
                                if len(fascard_users) > 1:
                                    raise Exception("Multiple fascard users found in block. Try refunding each transaction separately.")
                                if len(fascard_users) == 0:
                                    raise Exception("Transactions not matched to fascard user.  Unable to process.")
                                fascard_user = fascard_users.pop()
                                refund_factory = RefundFactory(enums.RefundType.FASCARD)
                                refund_factory.refunder.refund(fascard_user, refund.amount)
                            else:
                                raise Exception("Refund type not found")
                            refund.card_number = card_number_of_block
                            refund.save()
                            refund.user = request.user
                            laundry_transactions.update(is_refunded=True, refund=refund)
                    except Exception as e:
                        for transaction in transactions_of_block:
                            res['error_transactions'].append(transaction)
                else:
                    laundry_transactions.update()
                    for transaction in transactions_of_block:
                        res['error_transactions'].append(transaction)
        
        if len(res['error_transactions']) > 0:
            res['has_error'] = True
        return Response(res)

@api_view(['GET'])
def payment_type_list(request):
    """
    List all payment types.
    """
    if request.method == 'GET':
        types = [t[0] for t in enums.PaymentType.CHOICES]
        return Response(types)

@api_view(['GET'])
def activity_type_list(request):
    """
    List all activity types.
    """
    if request.method == 'GET':
        types = [t[0] for t in enums.ActivityType.CHOICES]
        return Response(types)