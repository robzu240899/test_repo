'''
Created on May 15, 2018

@author: tpk6
'''
from datetime import date 

from django.test import TestCase
from testhelpers.factories import LaundryGroupFactory, LaundryRoomExtensionFactory, LaundryRoomFactory,\
    BillingGroupFactory, RevenueSplitRuleFactory
from reporting.enums import RevenueSplitScheduleType, RevenueSplitFormula
from reporting.models import TimeSheetsReportJobInfo, TimeSheetsReportJobTracker, LegalStructureChoice, BuildingTypeChoice
from reporting.finance.clientreport.revenuemap import RevenueMapFactory

class RevenueMapTester(TestCase):
    
    def compare_maps(self, expected, actual):
        self.assertEqual(len(expected), len(actual), "The expected and actual results had different number of maps")
        for a in actual:
            same_rules_maps = filter(lambda x: x[0].pk == a[0].pk, expected)
            same_rules_maps_list = list(same_rules_maps)
            self.assertGreater(len(same_rules_maps_list), 0, "No match found for rule %s" % a[0] )
            self.assertLess(len(same_rules_maps_list), 2, "Multiple matches found for rule %s" % a[0] )
            self.assertAlmostEqual(
                same_rules_maps_list[0][1],
                a[1],
                4,
                "Expected revenue to be %s but got %s for rule %s" %(same_rules_maps_list[0][1], a[1], a[0])
            )
    
class TestConstantRevenueMap(RevenueMapTester):
    
    def setUp(self):
        TestCase.setUp(self) 
        self.laundry_group = LaundryGroupFactory()
        self.laundry_room = LaundryRoomFactory(laundry_group = self.laundry_group)
        self.billing_group = BillingGroupFactory(schedule_type = RevenueSplitScheduleType.CONSTANT)
        self.laundry_room_extension = LaundryRoomExtensionFactory(billing_group = self.billing_group, laundry_room = self.laundry_room)
        self.split_rule = RevenueSplitRuleFactory(billing_group = self.billing_group, revenue_split_formula = RevenueSplitFormula.PERCENT,
                                                  landloard_split_percent = .25
                                                  )
        self.start_date = date(2017,2,1)
        
        #Create some dummy data to pad the database and ensure we are pulling the correct data 
        dummy_laundry_room = LaundryRoomFactory(laundry_group = self.laundry_group)
        dummy_billing_group = BillingGroupFactory(schedule_type = RevenueSplitScheduleType.CONSTANT)
        dummy_laundry_room_extension = LaundryRoomExtensionFactory(billing_group = dummy_billing_group, laundry_room = dummy_laundry_room)
        dummy_split_rule = RevenueSplitRuleFactory(billing_group = dummy_billing_group, revenue_split_formula = RevenueSplitFormula.PERCENT,
                                                  landloard_split_percent = .35
                                                  )        
        
        
        
    def test_map(self):
        net_this_period = 100
        revenue_mapper = RevenueMapFactory.create_mapper(self.billing_group, net_this_period, self.start_date, 10000)
        actual_maps = revenue_mapper.create_map()
        expected_maps = [(self.split_rule, net_this_period)]
        self.compare_maps(expected_maps, actual_maps)
        
    def test_map_zero_revenue(self):
        net_this_period = 0
        revenue_mapper = RevenueMapFactory.create_mapper(self.billing_group, net_this_period, self.start_date, 10000)
        actual_maps = revenue_mapper.create_map()
        expected_maps = [(self.split_rule, net_this_period)]
        self.compare_maps(expected_maps, actual_maps)  

class TestGrossRevenueMap(RevenueMapTester):
    
    def setUp(self):
        TestCase.setUp(self) 
        self.laundry_group = LaundryGroupFactory()
        self.laundry_room = LaundryRoomFactory(laundry_group = self.laundry_group)
        self.billing_group = BillingGroupFactory(schedule_type = RevenueSplitScheduleType.GROSS_REVENUE)
        self.laundry_room_extension = LaundryRoomExtensionFactory(billing_group = self.billing_group, laundry_room = self.laundry_room)
        self.split_rule_0 = RevenueSplitRuleFactory(billing_group = self.billing_group, revenue_split_formula = RevenueSplitFormula.PERCENT,
                                                  landloard_split_percent = .25,
                                                  start_gross_revenue = 0, end_gross_revenue = 100
                                                  )        
        self.split_rule_1 = RevenueSplitRuleFactory(billing_group = self.billing_group, revenue_split_formula = RevenueSplitFormula.PERCENT,
                                                  landloard_split_percent = .25,
                                                  start_gross_revenue = 100, end_gross_revenue = 200
                                                  )               
        self.split_rule_2 = RevenueSplitRuleFactory(billing_group = self.billing_group, revenue_split_formula = RevenueSplitFormula.PERCENT,
                                                  landloard_split_percent = .25,
                                                  start_gross_revenue = 200, end_gross_revenue = None
                                                  )            
        
        
        self.start_date = date(2017,2,1)
        
        #Create some dummy data to pad the database and ensure we are pulling the correct data 
        dummy_laundry_room = LaundryRoomFactory(laundry_group = self.laundry_group)
        dummy_billing_group = BillingGroupFactory(schedule_type = RevenueSplitScheduleType.CONSTANT)
        dummy_laundry_room_extension = LaundryRoomExtensionFactory(billing_group = dummy_billing_group, laundry_room = dummy_laundry_room)
        dummy_split_rule = RevenueSplitRuleFactory(billing_group = dummy_billing_group, revenue_split_formula = RevenueSplitFormula.PERCENT,
                                                  landloard_split_percent = .35
                                                  )      
    
    def test_revenue_in_first_period(self):
        #NB: first period has a null start revenue 
        net_this_period = 10
        gross_previous = 50

        revenue_mapper = RevenueMapFactory.create_mapper(self.billing_group, net_this_period, self.start_date, gross_previous)
        actual_maps = revenue_mapper.create_map()
        expected_maps = [(self.split_rule_0, 10)]
        self.compare_maps(expected_maps, actual_maps)          
        
    def test_revenue_middle_period(self):
        #NB: middle period has both start and end revenue filled in 
        net_this_period = 10
        gross_previous = 100

        revenue_mapper = RevenueMapFactory.create_mapper(self.billing_group, net_this_period, self.start_date, gross_previous)
        actual_maps = revenue_mapper.create_map()
        expected_maps = [(self.split_rule_1, 10)]
        self.compare_maps(expected_maps, actual_maps)            
    
    def test_revenue_final_period(self):
        #NB: middle period has null end revenue
        net_this_period = 10
        gross_previous = 200

        revenue_mapper = RevenueMapFactory.create_mapper(self.billing_group, net_this_period, self.start_date, gross_previous)
        actual_maps = revenue_mapper.create_map()
        expected_maps = [(self.split_rule_2, 10)]
        self.compare_maps(expected_maps, actual_maps)        

    def test_revenue_periods_stard_and_middle(self):
        net_this_period = 10
        gross_previous = 92

        revenue_mapper = RevenueMapFactory.create_mapper(self.billing_group, net_this_period, self.start_date, gross_previous)
        actual_maps = revenue_mapper.create_map()
        expected_maps = [(self.split_rule_0, 8),  (self.split_rule_1, 2)]
        self.compare_maps(expected_maps, actual_maps)   

    def test_revenue_periods_middle_and_end(self):
        net_this_period = 10
        gross_previous = 192

        revenue_mapper = RevenueMapFactory.create_mapper(self.billing_group, net_this_period, self.start_date, gross_previous)
        actual_maps = revenue_mapper.create_map()
        expected_maps = [(self.split_rule_1, 8),  (self.split_rule_2, 2)]
        self.compare_maps(expected_maps, actual_maps)   


    def test_revenue_covering_all_rules(self):
        net_this_period = 130
        gross_previous = 90

        revenue_mapper = RevenueMapFactory.create_mapper(self.billing_group, net_this_period, self.start_date, gross_previous)
        actual_maps = revenue_mapper.create_map()
        expected_maps = [(self.split_rule_0, 10),  (self.split_rule_1, 100), (self.split_rule_2, 20)]
        self.compare_maps(expected_maps, actual_maps)   




class TestTimeMap(RevenueMapTester):
     
    def setUp(self):
        TestCase.setUp(self) 
        self.laundry_group = LaundryGroupFactory()
        self.laundry_room = LaundryRoomFactory(laundry_group = self.laundry_group)
        self.billing_group = BillingGroupFactory(
            lease_term_start = date(2013,1,1),
            schedule_type = RevenueSplitScheduleType.TIME,
            display_name = 'Client1')
        structure_type = LegalStructureChoice.objects.create(name='COOP')
        building_type = BuildingTypeChoice.objects.create(name='APARTMENTS')
        self.laundry_room_extension = LaundryRoomExtensionFactory(
            laundry_room = self.laundry_room,
            billing_group = self.billing_group,
            legal_structure = structure_type,
            building_type = building_type
        )
        self.split_rule_00 = RevenueSplitRuleFactory(billing_group = self.billing_group, revenue_split_formula = RevenueSplitFormula.PERCENT,
                                                  landloard_split_percent = .25,
                                                  start_date = None, end_date = date(2015,1,1))
        self.split_rule_0 = RevenueSplitRuleFactory(billing_group = self.billing_group, revenue_split_formula = RevenueSplitFormula.PERCENT,
                                                  landloard_split_percent = .25,
                                                  start_date = date(2015,1,1), end_date = date(2017,1,1)
                                                  )        
        self.split_rule_1 = RevenueSplitRuleFactory(billing_group = self.billing_group, revenue_split_formula = RevenueSplitFormula.PERCENT,
                                                  landloard_split_percent = .35,
                                                  start_date = date(2017,1,1), end_date = date(2017,2,1)
                                                  )               
        self.split_rule_2 = RevenueSplitRuleFactory(billing_group = self.billing_group, revenue_split_formula = RevenueSplitFormula.PERCENT,
                                                  landloard_split_percent = .45,
                                                  start_date = date(2017,2,1), end_date = None
                                                  )            
         
         
        #Create some dummy data to pad the database and ensure we are pulling the correct data 
        dummy_laundry_room = LaundryRoomFactory(laundry_group = self.laundry_group)
        dummy_billing_group = BillingGroupFactory(schedule_type = RevenueSplitScheduleType.CONSTANT)
        dummy_laundry_room_extension = LaundryRoomExtensionFactory(billing_group = dummy_billing_group, laundry_room = dummy_laundry_room)
        dummy_split_rule = RevenueSplitRuleFactory(billing_group = dummy_billing_group, revenue_split_formula = RevenueSplitFormula.PERCENT,
                                                  landloard_split_percent = .35
                                                  )      

    def test_no_start_date(self):
        net_this_period = 10
 
        revenue_mapper = RevenueMapFactory.create_mapper(self.billing_group, net_this_period, date(2014,6,1), 1010101)
        actual_maps = revenue_mapper.create_map()
        expected_maps = [(self.split_rule_00, 10)]
        self.compare_maps(expected_maps, actual_maps) 

        
    def test_first_period(self):
        net_this_period = 10
 
        revenue_mapper = RevenueMapFactory.create_mapper(self.billing_group, net_this_period, date(2016,6,1), 1010101)
        actual_maps = revenue_mapper.create_map()
        expected_maps = [(self.split_rule_0, 10)]
        self.compare_maps(expected_maps, actual_maps)           
        
    def test_middle_period_at_lhs_endge(self):
        net_this_period = 10
 
        revenue_mapper = RevenueMapFactory.create_mapper(self.billing_group, net_this_period, date(2017,1,1), 1010101)
        actual_maps = revenue_mapper.create_map()
        expected_maps = [(self.split_rule_1, 10)]
        self.compare_maps(expected_maps, actual_maps)            
    
    def test_middle_period(self):
        net_this_period = 10
 
        revenue_mapper = RevenueMapFactory.create_mapper(self.billing_group, net_this_period, date(2017,1,15), 1010101)
        actual_maps = revenue_mapper.create_map()
        expected_maps = [(self.split_rule_1, 10)]
        self.compare_maps(expected_maps, actual_maps)        
    
    def test_end_period_lhs_edge(self):
        net_this_period = 10
 
        revenue_mapper = RevenueMapFactory.create_mapper(self.billing_group, net_this_period, date(2017,2,1), 1010101)
        actual_maps = revenue_mapper.create_map()
        expected_maps = [(self.split_rule_2, 10)]
        self.compare_maps(expected_maps, actual_maps) 
    
    def test_end_period(self):
        net_this_period = 10
 
        revenue_mapper = RevenueMapFactory.create_mapper(self.billing_group, net_this_period, date(2017,6,1), 1010101)
        actual_maps = revenue_mapper.create_map()
        expected_maps = [(self.split_rule_2, 10)]
        self.compare_maps(expected_maps, actual_maps)                  