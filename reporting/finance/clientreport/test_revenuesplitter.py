'''
Created on May 15, 2018

@author: tpk6
'''
import random
from django.test import TestCase 
from datetime import date
from decimal import Decimal
from ...enums import RevenueSplitFormula, RevenueSplitScheduleType
from testhelpers.factories import LaundryGroupFactory, LaundryRoomFactory, BillingGroupFactory, LaundryRoomExtensionFactory, RevenueSplitRuleFactory
from .revenuesplitter import RevenueSplitter
 
class TestRevenueSplitter(TestCase):
    
    def test_splitter(self):
        self.laundry_group = LaundryGroupFactory()
        self.laundry_room = LaundryRoomFactory(laundry_group = self.laundry_group)
        self.billing_group = BillingGroupFactory(schedule_type=RevenueSplitScheduleType.GROSS_REVENUE)
        self.laundry_room_extension = LaundryRoomExtensionFactory(billing_group = self.billing_group, laundry_room = self.laundry_room)
        self.split_rule_0 = RevenueSplitRuleFactory(billing_group = self.billing_group, revenue_split_formula = RevenueSplitFormula.PERCENT,
                                                  landloard_split_percent = .10,
                                                  start_gross_revenue = 0, end_gross_revenue = 100
                                                  )        
        self.split_rule_1 = RevenueSplitRuleFactory(billing_group = self.billing_group, revenue_split_formula = RevenueSplitFormula.PERCENT,
                                                  landloard_split_percent = .25,
                                                  start_gross_revenue = 100, end_gross_revenue = 200
                                                  )               
        self.split_rule_2 = RevenueSplitRuleFactory(billing_group = self.billing_group, revenue_split_formula = RevenueSplitFormula.PERCENT,
                                                  landloard_split_percent = .40,
                                                  start_gross_revenue = 200, end_gross_revenue = None
                                                  )       
        
        splitter = RevenueSplitter(billing_group = self.billing_group, current_net_revenue=150, start_date=None, previous_gross_revenue=90)
        client_share, aces_share = splitter.split_revenue()
        
        #10 of revenue for split rule 0, .1 stake +  100 of revenue for split rule 0, .25 stake + 40 in revenue for split rule 2, .4 stake
        expected_aces_share = .1*10 + 100*.25 + 40*.4
        expected_client_share = 150 - expected_aces_share
        
        self.assertAlmostEqual(client_share, expected_aces_share, 4)
        self.assertAlmostEqual(aces_share, expected_client_share, 4)

    def test_prorating(self):
        #TODO: Randomize operations_days, operations_start_date
        randomized_operations_start = date(2020,7,random.randint(1,31))
        randomized_operations_days = (date(2020,7,31) - randomized_operations_start).days + 1
        self.laundry_group = LaundryGroupFactory()
        self.laundry_room = LaundryRoomFactory(laundry_group = self.laundry_group)
        self.billing_group = BillingGroupFactory(
            schedule_type=RevenueSplitScheduleType.CONSTANT,
            operations_start_date = randomized_operations_start,
            lease_term_start = date(2020,8,1),
            lease_term_duration_months = 8
        )
        self.laundry_room_extension = LaundryRoomExtensionFactory(billing_group = self.billing_group, laundry_room = self.laundry_room)
        self.split_rule_0 = RevenueSplitRuleFactory(
            billing_group = self.billing_group,
            revenue_split_formula = RevenueSplitFormula.GENERAL_BREAKPOINT,
            base_rent = 4500,
            landloard_split_percent = 0,
            breakpoint = 0
        )                 
        splitter = RevenueSplitter(
            billing_group = self.billing_group,
            current_net_revenue= Decimal('710.33'),
            start_date=date(2020,7,1),
            previous_gross_revenue=Decimal('0')
        )
        client_share, aces_share = splitter.split_revenue()
        self.assertEqual(splitter.prorate, True)
        self.assertEqual(splitter.prorate_factor, (splitter.operations_days / splitter.days_in_month))
        op = Decimal(str(self.split_rule_0.base_rent)) * (Decimal(str(randomized_operations_days))/Decimal('31'))
        self.assertAlmostEqual(client_share, op, places=4)
        #self.assertAlmostEqual(client_share, expected_aces_share, 4)
        #self.assertAlmostEqual(aces_share, expected_client_share, 4)

        