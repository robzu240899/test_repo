'''
Created on May 17, 2018

@author: tpk6
'''

from django.test import TestCase 

from owed import OwedCalculator

class TestOwedCalculator(TestCase):
    
    def test_aces_collects_cash(self):
        x = OwedCalculator(client_share = 50, aces_share = 100, aces_collects_cash=True, cash_amount=10, client_name='Client1')
        aces_owes_client, helper_text = x.calculate()
        self.assertEqual(aces_owes_client, 50)
        self.assertEqual(helper_text, "Aces Owes Client1")
        
    def test_client_collects_cash(self):
        x = OwedCalculator(client_share = 50, aces_share = 100, aces_collects_cash=False, cash_amount=10, client_name='Client1')
        aces_owes_client, helper_text = x.calculate()
        self.assertEqual(aces_owes_client, 40)
        self.assertEqual(helper_text, "Aces Owes Client1")
        
 
    def test_client_collects_cash_negative_amount_owed(self):
        x = OwedCalculator(client_share = 50, aces_share = 100, aces_collects_cash=False, cash_amount=75, client_name='Client1')
        aces_owes_client, helper_text = x.calculate()
        self.assertEqual(aces_owes_client, -25)
        self.assertEqual(helper_text, "Client1 Owes Aces")       
