'''
Created on Mar 6, 2018

@author: tpk6
'''

from django.test import TestCase
from .testhelpers import factories
from .refunds import RefundBrowser

class TestRefund(TestCase):
    
    def test_refund(self):
        laundry_group = factories.LaundryGroupFactory(id=1)  #Note, this will let us access the Fascard account 
        fascard_user = factories.FascardUserFactory(name="Daniel", laundry_group=laundry_group, fascard_user_account_id=7)
        with RefundBrowser(fascard_user, 2.00) as refunder:
            success = refunder.refund()
        self.assertTrue(success)

    