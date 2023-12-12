'''
Created on Apr 12, 2017

@author: Thomas
'''
import os 
from django.test import TestCase

from datetime import date 

from Utils.CSVIngest.ingest import CSVIngestor

from main.settings import TEST_FILE_FOLDER

from fascard.config import FascardScrapeConfig

from roommanager.models import LaundryGroup,LaundryRoom

from ..models import RevenueSplitRule

from ..enums import RevenueSplitFormula, RevenueSplitScheduleType
from revenue_split_rule import RevenueRuleAdaptor
from reporting.models import BillingGroup

class TestRevenueSplitRule(TestCase):

    def setUp(self):
        folder_name = os.path.join(TEST_FILE_FOLDER,'test_revenue_split_rule')
        CSVIngestor(LaundryGroup,file_name = os.path.join(folder_name,'laundry_group.csv')).ingest(date_format=None,datetime_format=FascardScrapeConfig.TIME_INPUT_FORMAT)
        CSVIngestor(LaundryRoom,file_name = os.path.join(folder_name,'laundry_room.csv')).ingest(date_format=None,datetime_format=FascardScrapeConfig.TIME_INPUT_FORMAT)
        self.arden = LaundryRoom.objects.get(display_name='1 Arden ST')
        self.billing_group = BillingGroup.objects.create(display_name='test',schedule_type=RevenueSplitScheduleType.CONSTANT)
 
    def test_percent(self):
        
        orm_rule = RevenueSplitRule.objects.create(billing_group = self.billing_group,
                                revenue_split_formula = RevenueSplitFormula.PERCENT,
                                base_rent = None,
                                landloard_split_percent = .8,
                                breakpoint = None,
                                start_gross_revenue = None,
                                end_gross_revenue = None,
                                start_date = None,
                                end_date = None
                                )
        rule = RevenueRuleAdaptor().create_rule(orm_rule)
        client_share,aces_share=rule.calculate_split(1000)
        self.assertAlmostEqual(client_share,800,places=5)
        self.assertAlmostEqual(aces_share,200,places=5)
        
    def test_natural_breakpoint_over_base_rent(self):
        orm_rule = RevenueSplitRule.objects.create(billing_group = self.billing_group,
                                revenue_split_formula = RevenueSplitFormula.NATURAL_BREAKPOINT,
                                base_rent = 500,
                                landloard_split_percent = .8,
                                breakpoint = None,
                                start_gross_revenue = None,
                                end_gross_revenue = None,
                                start_date = None,
                                end_date = None
                                )
        rule = RevenueRuleAdaptor().create_rule(orm_rule)
        client_share,aces_share=rule.calculate_split(1000)
        self.assertAlmostEqual(client_share,900,places=5) #500+500*.8 =900
        self.assertAlmostEqual(aces_share,100,places=5)  

    def test_natural_breakpoint_under_base_rent(self):
        orm_rule = RevenueSplitRule.objects.create(billing_group = self.billing_group,
                                revenue_split_formula = RevenueSplitFormula.NATURAL_BREAKPOINT,
                                base_rent = 2000,
                                landloard_split_percent = .8,
                                breakpoint = None,
                                start_gross_revenue = None,
                                end_gross_revenue = None,
                                start_date = None,
                                end_date = None
                                )
        rule = RevenueRuleAdaptor().create_rule(orm_rule)
        client_share,aces_share=rule.calculate_split(1000)
        self.assertAlmostEqual(client_share,2000,places=5)
        self.assertAlmostEqual(aces_share,-1000,places=5)

    def test_general_breakpoint_under_base_rent(self):
        orm_rule = RevenueSplitRule.objects.create(billing_group = self.billing_group,
                                revenue_split_formula = RevenueSplitFormula.GENERAL_BREAKPOINT,
                                base_rent = 1000,
                                landloard_split_percent = .1,
                                breakpoint = 2000,
                                start_gross_revenue = None,
                                end_gross_revenue = None,
                                start_date = None,
                                end_date = None
                                )
        rule = RevenueRuleAdaptor().create_rule(orm_rule)
        client_share,aces_share=rule.calculate_split(700)
        self.assertAlmostEqual(client_share,1000,places=5)
        self.assertAlmostEqual(aces_share,-300,places=5)

    def test_general_between_base_rent_and_breakpoint(self):
        orm_rule = RevenueSplitRule.objects.create(billing_group = self.billing_group,
                                revenue_split_formula = RevenueSplitFormula.GENERAL_BREAKPOINT,
                                base_rent = 1000,
                                landloard_split_percent = .1,
                                breakpoint = 2000,
                                start_gross_revenue = None,
                                end_gross_revenue = None,
                                start_date = None,
                                end_date = None
                                )
        rule = RevenueRuleAdaptor().create_rule(orm_rule)
        client_share,aces_share=rule.calculate_split(1500)
        self.assertAlmostEqual(client_share,1000,places=5)
        self.assertAlmostEqual(aces_share,500,places=5)

    def test_general_between_over_breakpoint(self):
        orm_rule = RevenueSplitRule.objects.create(billing_group = self.billing_group,
                                revenue_split_formula = RevenueSplitFormula.GENERAL_BREAKPOINT,
                                base_rent = 1000,
                                landloard_split_percent = .1,
                                breakpoint = 2000,
                                start_gross_revenue = None,
                                end_gross_revenue = None,
                                start_date = None,
                                end_date = None
                                )
        rule = RevenueRuleAdaptor().create_rule(orm_rule)
        client_share,aces_share=rule.calculate_split(3000)
        self.assertAlmostEqual(client_share,1100,places=5) #1000 + (3000-2000)*.1
        self.assertAlmostEqual(aces_share,1900,places=5)

        
        
        
        
        
        
        
        
        