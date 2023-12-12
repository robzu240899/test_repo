'''
Created on May 16, 2018

@author: tpk6
'''
from decimal import Decimal

from django.test import TestCase

from testhelpers.factories import BillingGroupFactory

from mincomp import MinimumCompensationRule



class TestMinComp(TestCase):
    
    def test_no_min_comp_rule_specified(self):
        self.billing_group = BillingGroupFactory(min_compensation_per_day = None)
        min_comp = MinimumCompensationRule(billing_group = self.billing_group, aces_share = Decimal('50.00'), client_share = Decimal('100.00'), number_days=30)
        min_comp.calculate()
        self.assertFalse(min_comp.rule_applied)
        self.assertAlmostEqual(min_comp.aces_share_after_mincomp, 50.0)
        self.assertAlmostEqual(min_comp.client_share_after_mincomp, 100.0)
        
    def test_min_comp_rule_kicks_in(self):
        self.billing_group = BillingGroupFactory(min_compensation_per_day = 2.0)
        min_comp = MinimumCompensationRule(billing_group = self.billing_group, aces_share = Decimal('50.00'), client_share = Decimal('100.00'), number_days=30)
        min_comp.calculate()
        self.assertTrue(min_comp.rule_applied)
        self.assertAlmostEqual(min_comp.aces_share_after_mincomp, 60.0)
        self.assertAlmostEqual(min_comp.client_share_after_mincomp, 90.0)
        
    def test_min_comp_rule_does_not_kick_in(self):
        self.billing_group = BillingGroupFactory(min_compensation_per_day = .25)
        min_comp = MinimumCompensationRule(billing_group = self.billing_group, aces_share = Decimal('50.00'), client_share = Decimal('100.00'), number_days=30)
        min_comp.calculate()
        self.assertFalse(min_comp.rule_applied)
        self.assertAlmostEqual(min_comp.aces_share_after_mincomp, 50.0)
        self.assertAlmostEqual(min_comp.client_share_after_mincomp, 100.0)
        
    def test_min_comp_rule_exceeds_total_revenue(self):
        self.billing_group = BillingGroupFactory(min_compensation_per_day = 10.0)
        min_comp = MinimumCompensationRule(billing_group = self.billing_group, aces_share = Decimal('50.00'), client_share = Decimal('100.00'), number_days=30)
        min_comp.calculate()
        self.assertTrue(min_comp.rule_applied)
        self.assertAlmostEqual(min_comp.aces_share_after_mincomp, 150.0)
        self.assertAlmostEqual(min_comp.client_share_after_mincomp, 0.0)        
        
        