'''
Created on May 8, 2018

@author: tpk6
'''
from django.db.models import Q 
from .enums import TransactionType, AddValueSubType


class StandardFilters(object):
    
    WEB_VALUE_ADD_Q = Q( Q(transaction_type = TransactionType.ADD_VALUE) & Q(trans_sub_type = AddValueSubType.CREDIT_ON_WEBSITE) )  #NB: wrapped in the outer Q to ensure order of operations works in complex Q expressiosn
    FAKE_TX_Q = Q(Q(transaction_type = TransactionType.CASHOUT_REQUEST) | Q(transaction_type = TransactionType.DAMAGE_REFUND_REQUEST))
    