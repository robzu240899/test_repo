import calendar
import os 
from decimal import Decimal
from django.test import TestCase
from datetime import date, timedelta
from django.db.models import Q
from fascard.config import FascardScrapeConfig
from roommanager.models import LaundryGroup,LaundryRoom 
from ...models import RevenueSplitRule
from ...enums import RevenueSplitFormula, RevenueSplitScheduleType
from reporting.models import LegalStructureChoice, BuildingTypeChoice
from reporting.enums import *
from reporting.finance.clientreport.revenuesplitrule import RevenueRuleAdaptor
from reporting.finance.clientreport.revenuesplitter import RevenueSplitter
from reporting.finance.clientreport.revenuemap import RevenueMapFactory
from reporting.finance.clientreport.metricsfetcher import MetricsFetcher
from testhelpers.factories import LaundryGroupFactory, LaundryRoomFactory, BillingGroupFactory, \
LaundryRoomExtensionFactory, RevenueSplitRuleFactory, MetricFacotry
 
from reporting.models import BillingGroup
 
class TestRevenueSplitRule(TestCase):
 
    def setUp(self):
        self.laundry_group = LaundryGroupFactory()
        self.laundry_room = LaundryRoomFactory(laundry_group = self.laundry_group)
        self.billing_group = BillingGroupFactory(schedule_type=RevenueSplitScheduleType.CONSTANT)
        self.laundry_room_extension = LaundryRoomExtensionFactory(billing_group = self.billing_group, laundry_room = self.laundry_room)
  
    def test_percent(self):
         
        orm_rule = RevenueSplitRuleFactory(billing_group = self.billing_group,
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
        orm_rule = RevenueSplitRuleFactory(billing_group = self.billing_group,
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
        orm_rule = RevenueSplitRuleFactory(billing_group = self.billing_group,
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
        orm_rule = RevenueSplitRuleFactory(billing_group = self.billing_group,
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
        orm_rule = RevenueSplitRuleFactory(billing_group = self.billing_group,
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
        orm_rule = RevenueSplitRuleFactory(billing_group = self.billing_group,
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


class BaseTimeBasedRuleTests():

    def create_metrics(self, metrics_data):
        for metric_name, metric_data in metrics_data.items():
            MetricFacotry(
                metric_type=metric_data[0],
                location_id = self.room_1.id,
                duration = DurationType.MONTH,
                start_date = self.start_date_for_analysis,
                result = metric_data[1],
                location_level = LocationLevel.LAUNDRY_ROOM
            )


class TestMultipleTimeBasedPercentSplitRules(TestCase, BaseTimeBasedRuleTests):
    """
    Test the case of a billing group having more than one revenue split rules effective on the same month.
    The expected result is to treat the reveneue as an atomic unit and attribute the revene split rule
    proportionally to the days of the month that it was effective for.

    i.e If the revenue is 1,000 and the first revenue split rule was effective for the first 17.0 days
    of the month, then it would be applied over (1,000/days_in_month)*17 worth of revenue. 
    """

    #TODO: Since we dont want to go into details of daily metrics
    #just split the revenue number proportionaley based on the n revenue split rules.

    def setUp(self):
        self.billing_group = BillingGroupFactory(
            lease_term_start = date(2017,3,1),
            schedule_type  = RevenueSplitScheduleType.TIME,
            display_name = 'Client1')
        self.laundry_group = LaundryGroupFactory()
        self.room_1 = LaundryRoomFactory(laundry_group = self.laundry_group)
        structure_type = LegalStructureChoice.objects.create(name='COOP')
        building_type = BuildingTypeChoice.objects.create(name='APARTMENTS')
        self.room_1_extension = LaundryRoomExtensionFactory(
            laundry_room = self.room_1,
            billing_group = self.billing_group,
            legal_structure = structure_type,
            building_type = building_type
        )
        percent_split_rule_1 = RevenueSplitRuleFactory(
            billing_group = self.billing_group,
            revenue_split_formula = RevenueSplitFormula.PERCENT,
            landloard_split_percent = .20,
            start_date=date(2020,1,1),
            end_date=date(2020,12,10),
        )
        percent_split_rule_2 = RevenueSplitRuleFactory(
            billing_group = self.billing_group,
            revenue_split_formula = RevenueSplitFormula.PERCENT,
            landloard_split_percent = .20,
            start_date=date(2020,12,10),
            end_date=date(2020,12,20),
        )
        percent_split_rule_3 = RevenueSplitRuleFactory(
            billing_group = self.billing_group,
            revenue_split_formula = RevenueSplitFormula.PERCENT,
            landloard_split_percent = .40,
            start_date=date(2020,12,20),
            end_date=date(2024,1,31),
        )

        self.start_date_for_analysis = date(2020,12,1)
        self.net_revenue = 90

        metrics_test_data = {
            'revenue' : [MetricType.REVENUE_FUNDS, 90],
            'revenue_credit' : [MetricType.REVENUE_FUNDS_CREDIT, 30],
            'revenue_cash' : [MetricType.REVENUE_FUNDS_CASH, 30],
            'revenue_checks' : [MetricType.REVENUE_FUNDS_CHECK, 30],
            'revenue_credit_machine_starts' : [MetricType.REVENUE_FUNDS_CREDIT_DIRECT_VEND, 10],
            'revenue_credit_value_add_inroom' : [MetricType.REVENUE_FUNDS_CREDIT_PRESENT_ADD_VALUE, 10],
            'revenue_credit_value_add_web' : [MetricType.REVENUE_FUNDS_CREDIT_WEB_ADD_VALUE, 10]
        }
        self.create_metrics(metrics_test_data)
        
    def test_days_in_effect_attribution(self):
        revenue_map = []
        end_of_month = date(
                self.start_date_for_analysis.year,
                self.start_date_for_analysis.month,
                calendar.monthrange(*tuple([self.start_date_for_analysis.year, self.start_date_for_analysis.month,]))[1]
            )
        timeQ = (Q(start_date__lte=self.start_date_for_analysis) & Q(end_date__gt=self.start_date_for_analysis)) | \
                (Q(start_date__lte=self.start_date_for_analysis) & Q(end_date=None)) | \
                (Q(start_date__gte=self.start_date_for_analysis) & Q(start_date__lte=end_of_month)) | \
                (Q(start_date=None)                 & Q(end_date__gt=self.start_date_for_analysis))  
        rules = RevenueSplitRule.objects.filter(timeQ,billing_group=self.billing_group).order_by('start_date')
        start = self.start_date_for_analysis
        results = []
        for i, split_rule in enumerate(rules):
            days_in_effect = (min(split_rule.end_date, end_of_month) - start)
            if i == rules.count() - 1:
                days_in_effect += timedelta(days=1)
            start = split_rule.end_date
            results.append(days_in_effect.days)
        self.assertEqual(results,[9,10,12])

    def test_multiple_split_rules(self):
        factory = RevenueMapFactory.create_mapper(self.billing_group, 1000, self.start_date_for_analysis, 1500)
        revenue_maps = factory.create_map()
        print (revenue_maps)
        self.assertEqual(len(revenue_maps),3)

    def test_split_revenue_multiple_splitrules(self):
        splitter = RevenueSplitter(self.billing_group, Decimal(1000), self.start_date_for_analysis, Decimal(1500))
        print (splitter.split_revenue())         
         
         
class TestMultipleTimeBasedGenBreakpointSplitRules(TestCase, BaseTimeBasedRuleTests):

    def setUp(self):
        self.billing_group = BillingGroupFactory(
            lease_term_start = date(2017,3,1),
            schedule_type  = RevenueSplitScheduleType.TIME,
            display_name = 'Client111')
        self.laundry_group = LaundryGroupFactory()
        self.room_1 = LaundryRoomFactory(laundry_group = self.laundry_group, display_name='Test2')
        structure_type = LegalStructureChoice.objects.create(name='COOP')
        building_type = BuildingTypeChoice.objects.create(name='APARTMENTS')
        self.room_1_extension = LaundryRoomExtensionFactory(
            laundry_room = self.room_1,
            billing_group = self.billing_group,
            legal_structure = structure_type,
            building_type = building_type
        )

        gen_breakpoint_split_rule_1 = RevenueSplitRuleFactory(
            billing_group = self.billing_group,
            base_rent = 500,
            breakpoint = 2200,
            revenue_split_formula = RevenueSplitFormula.GENERAL_BREAKPOINT,
            landloard_split_percent = .20,
            min_comp_per_day = 20,
            start_date=date(2020,1,1),
            end_date=date(2020,12,10),
        )
        gen_breakpoint_split_rule_2 = RevenueSplitRuleFactory(
            billing_group = self.billing_group,
            base_rent = 600,
            breakpoint = 2000,
            revenue_split_formula = RevenueSplitFormula.GENERAL_BREAKPOINT,
            landloard_split_percent = .20,
            min_comp_per_day = 20,
            start_date=date(2020,12,10),
            end_date=date(2020,12,20),
        )
        gen_breakpoint_split_rule_3 = RevenueSplitRuleFactory(
            billing_group = self.billing_group,
            base_rent = 700,
            breakpoint = 1500,
            revenue_split_formula = RevenueSplitFormula.GENERAL_BREAKPOINT,
            landloard_split_percent = .40,
            min_comp_per_day = 50,
            start_date=date(2020,12,20),
            end_date=date(2024,1,31),
        )

        metrics_test_data = {
            'revenue' : [MetricType.REVENUE_FUNDS, 2000],
            'revenue_credit' : [MetricType.REVENUE_FUNDS_CREDIT, 800],
            'revenue_cash' : [MetricType.REVENUE_FUNDS_CASH, 800],
            'revenue_checks' : [MetricType.REVENUE_FUNDS_CHECK, 400],
            'revenue_credit_machine_starts' : [MetricType.REVENUE_FUNDS_CREDIT_DIRECT_VEND, 300],
            'revenue_credit_value_add_inroom' : [MetricType.REVENUE_FUNDS_CREDIT_PRESENT_ADD_VALUE, 200],
            'revenue_credit_value_add_web' : [MetricType.REVENUE_FUNDS_CREDIT_WEB_ADD_VALUE, 300]
        }
        self.start_date_for_analysis = date(2020,12,1)
        self.create_metrics(metrics_test_data)

    def test_basic(self):
        fetcher = MetricsFetcher(self.billing_group, self.start_date_for_analysis)
        laundry_room_gross_metrics = fetcher.laundry_room_data
        billing_group_gross_metrics = fetcher.totals
        net = billing_group_gross_metrics['revenue']
        splitter = RevenueSplitter(self.billing_group, net, self.start_date_for_analysis, billing_group_gross_metrics['previous_revenue'])
        client_share_premin, aces_share_premin = splitter.split_revenue()
        print (client_share_premin, aces_share_premin)

        #NOTE: 
        """
        Comments:
            -What should we do if we have two different time-based split rules effective
            on a given month and they both have min_comp_per_day
        """


