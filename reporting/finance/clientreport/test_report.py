'''
Created on May 16, 2018

@author: tpk6
'''

from datetime import date 

from django.test import TestCase
from testhelpers.factories import LaundryGroupFactory, LaundryRoomExtensionFactory, LaundryRoomFactory,\
    BillingGroupFactory, RevenueSplitRuleFactory, MetricFacotry, ExpenseTypeFactory, FascardUserFactory
from reporting.enums import RevenueSplitScheduleType, RevenueSplitFormula
from reporting.enums import DurationType, LocationLevel, MetricType, ExpenseType
from reporting.models import TimeSheetsReportJobInfo, TimeSheetsReportJobTracker, LegalStructureChoice, BuildingTypeChoice
from reporting.finance.clientreport.job import TimeSheetsReportJobProcessor, TimeSheetsJobsTrackerProcessor
from .report import ClientRevenueReport
from .job import TimeSheetsReportJobProcessor

class TestReport(TestCase):
    
    def setUp(self):
        TestCase.setUp(self)
        self.start_date = date(2017,3,1)
        self.billing_group = BillingGroupFactory(
            lease_term_start = self.start_date,
            schedule_type  = RevenueSplitScheduleType.CONSTANT,
            display_name = 'Client1')
        self.laundry_group = LaundryGroupFactory()
        
        RevenueSplitRuleFactory(billing_group = self.billing_group, revenue_split_formula = RevenueSplitFormula.PERCENT, landloard_split_percent = .25)
        self.room_1 = LaundryRoomFactory(laundry_group = self.laundry_group)
        structure_type = LegalStructureChoice.objects.create(name='COOP')
        building_type = BuildingTypeChoice.objects.create(name='APARTMENTS')
        self.room_1_extension = LaundryRoomExtensionFactory(
            laundry_room = self.room_1,
            billing_group = self.billing_group,
            legal_structure = structure_type,
            building_type = building_type
        )
        MetricFacotry(metric_type = MetricType.REVENUE_FUNDS, location_id = self.room_1.id, duration = DurationType.MONTH, start_date = self.start_date,
                      result = 100, location_level = LocationLevel.LAUNDRY_ROOM)
        MetricFacotry(metric_type = MetricType.REVENUE_FUNDS_CREDIT, location_id = self.room_1.id, duration = DurationType.MONTH, start_date = self.start_date,
                      result = 60, location_level = LocationLevel.LAUNDRY_ROOM)     
        MetricFacotry(metric_type = MetricType.REVENUE_FUNDS_CASH, location_id = self.room_1.id, duration = DurationType.MONTH, start_date = self.start_date,
                      result = 22, location_level = LocationLevel.LAUNDRY_ROOM)          
        MetricFacotry(metric_type = MetricType.REVENUE_FUNDS_CHECK, location_id = self.room_1.id, duration = DurationType.MONTH, start_date = self.start_date,
                      result = 18, location_level = LocationLevel.LAUNDRY_ROOM)      
        MetricFacotry(metric_type = MetricType.REVENUE_FUNDS_CREDIT_DIRECT_VEND, location_id = self.room_1.id, duration = DurationType.MONTH, start_date = self.start_date,
                      result = 10, location_level = LocationLevel.LAUNDRY_ROOM)  
        MetricFacotry(metric_type = MetricType.REVENUE_FUNDS_CREDIT_PRESENT_ADD_VALUE, location_id = self.room_1.id, duration = DurationType.MONTH, start_date = self.start_date,
                      result = 15, location_level = LocationLevel.LAUNDRY_ROOM)  
        MetricFacotry(metric_type = MetricType.REVENUE_FUNDS_CREDIT_WEB_ADD_VALUE, location_id = self.room_1.id, duration = DurationType.MONTH, start_date = self.start_date,
                      result = 35, location_level = LocationLevel.LAUNDRY_ROOM)  
        MetricFacotry(metric_type = MetricType.REVENUE_FUNDS, location_id = self.room_1.id, duration = DurationType.BEFORE, start_date = self.start_date,
                      result = 99, location_level = LocationLevel.LAUNDRY_ROOM)  
        
        

        self.room_2 = LaundryRoomFactory(laundry_group = self.laundry_group)
        self.room_2_extension = LaundryRoomExtensionFactory(laundry_room = self.room_2, billing_group = self.billing_group)
        MetricFacotry(metric_type = MetricType.REVENUE_FUNDS, location_id = self.room_2.id, duration = DurationType.MONTH, start_date = self.start_date,
                      result = 1000, location_level = LocationLevel.LAUNDRY_ROOM)
        MetricFacotry(metric_type = MetricType.REVENUE_FUNDS_CREDIT, location_id = self.room_2.id, duration = DurationType.MONTH, start_date = self.start_date,
                      result = 600, location_level = LocationLevel.LAUNDRY_ROOM)       
        MetricFacotry(metric_type = MetricType.REVENUE_FUNDS_CASH, location_id = self.room_2.id, duration = DurationType.MONTH, start_date = self.start_date,
                      result = 220, location_level = LocationLevel.LAUNDRY_ROOM)             
        MetricFacotry(metric_type = MetricType.REVENUE_FUNDS_CHECK, location_id = self.room_2.id, duration = DurationType.MONTH, start_date = self.start_date,
                      result = 180, location_level = LocationLevel.LAUNDRY_ROOM)       
        MetricFacotry(metric_type = MetricType.REVENUE_FUNDS_CREDIT_DIRECT_VEND, location_id = self.room_2.id, duration = DurationType.MONTH, start_date = self.start_date,
                      result = 100, location_level = LocationLevel.LAUNDRY_ROOM)   
        MetricFacotry(metric_type = MetricType.REVENUE_FUNDS_CREDIT_PRESENT_ADD_VALUE, location_id = self.room_2.id, duration = DurationType.MONTH, start_date = self.start_date,
                      result = 150, location_level = LocationLevel.LAUNDRY_ROOM)   
        MetricFacotry(metric_type = MetricType.REVENUE_FUNDS_CREDIT_WEB_ADD_VALUE, location_id = self.room_2.id, duration = DurationType.MONTH, start_date = self.start_date,
                      result = 350, location_level = LocationLevel.LAUNDRY_ROOM)   
        MetricFacotry(metric_type = MetricType.REVENUE_FUNDS, location_id = self.room_2.id, duration = DurationType.BEFORE, start_date = self.start_date,
                      result = 990, location_level = LocationLevel.LAUNDRY_ROOM)   

        #Setup Expenses 
        credit_card_split = ExpenseTypeFactory(expense_type = ExpenseType.CREDIT_CARD_SPLIT, display_name = 'Credit Card Fees')
        internet = ExpenseTypeFactory(expense_type = ExpenseType.STANDARD, display_name = 'internet')
        self.raw_expenses = [{'expense_amount': .05, 'expense_type': credit_card_split},
                             {'expense_amount':20, 'expense_type':internet}]
    
      
        #create some data for rooms that aren't assocaited with the billing group.  this data should not impact the tests
        self.dummy_billing_group = BillingGroupFactory(lease_term_start=self.start_date)
        self.room_3 = LaundryRoomFactory(laundry_group = self.laundry_group)
        self.room_3_extension = LaundryRoomExtensionFactory(laundry_room = self.room_3, billing_group = self.dummy_billing_group)
        MetricFacotry(metric_type = MetricType.REVENUE_FUNDS, location_id = self.room_3.id, duration = DurationType.MONTH, start_date = self.start_date,
                      result = 11111, location_level = LocationLevel.LAUNDRY_ROOM)
        MetricFacotry(metric_type = MetricType.REVENUE_FUNDS_CREDIT, location_id = self.room_3.id, duration = DurationType.MONTH, start_date = self.start_date,
                      result = 11111, location_level = LocationLevel.LAUNDRY_ROOM)       
        MetricFacotry(metric_type = MetricType.REVENUE_FUNDS_CASH, location_id = self.room_3.id, duration = DurationType.MONTH, start_date = self.start_date,
                      result = 11111, location_level = LocationLevel.LAUNDRY_ROOM)             
        MetricFacotry(metric_type = MetricType.REVENUE_FUNDS_CHECK, location_id = self.room_3.id, duration = DurationType.MONTH, start_date = self.start_date,
                      result = 11111, location_level = LocationLevel.LAUNDRY_ROOM)      
        MetricFacotry(metric_type = MetricType.REVENUE_FUNDS_CREDIT_DIRECT_VEND, location_id = self.room_3.id, duration = DurationType.MONTH, start_date = self.start_date,
                      result = 11111, location_level = LocationLevel.LAUNDRY_ROOM)   
        MetricFacotry(metric_type = MetricType.REVENUE_FUNDS_CREDIT_PRESENT_ADD_VALUE, location_id = self.room_3.id, duration = DurationType.MONTH, start_date = self.start_date,
                      result = 11111, location_level = LocationLevel.LAUNDRY_ROOM)   
        MetricFacotry(metric_type = MetricType.REVENUE_FUNDS_CREDIT_WEB_ADD_VALUE, location_id = self.room_3.id, duration = DurationType.MONTH, start_date = self.start_date,
                      result = 11111, location_level = LocationLevel.LAUNDRY_ROOM)         
        MetricFacotry(metric_type = MetricType.REVENUE_FUNDS, location_id = self.room_3.id, duration = DurationType.BEFORE, start_date = self.start_date,
                      result = 11111, location_level = LocationLevel.LAUNDRY_ROOM)     
       
        #create some historical data for the laundry rooms in our billing group.  this data shouldn't impact the tests 
        MetricFacotry(metric_type = MetricType.REVENUE_FUNDS, location_id = self.room_1.id, duration = DurationType.MONTH, start_date = date(2014,1,1),
                      result = 222222, location_level = LocationLevel.LAUNDRY_ROOM)
        MetricFacotry(metric_type = MetricType.REVENUE_FUNDS_CREDIT, location_id = self.room_1.id, duration = DurationType.MONTH, start_date = date(2014,1,1),
                      result = 22222, location_level = LocationLevel.LAUNDRY_ROOM)       
        MetricFacotry(metric_type = MetricType.REVENUE_FUNDS_CASH, location_id = self.room_1.id, duration = DurationType.MONTH, start_date = date(2014,1,1),
                      result = 22222, location_level = LocationLevel.LAUNDRY_ROOM)             
        MetricFacotry(metric_type = MetricType.REVENUE_FUNDS_CHECK, location_id = self.room_1.id, duration = DurationType.MONTH, start_date = date(2014,1,1),
                      result = 22222, location_level = LocationLevel.LAUNDRY_ROOM)    
        MetricFacotry(metric_type = MetricType.REVENUE_FUNDS_CREDIT_DIRECT_VEND, location_id = self.room_1.id, duration = DurationType.MONTH, start_date = date(2014,1,1),
                      result = 222222, location_level = LocationLevel.LAUNDRY_ROOM)   
        MetricFacotry(metric_type = MetricType.REVENUE_FUNDS_CREDIT_PRESENT_ADD_VALUE, location_id = self.room_1.id, duration = DurationType.MONTH, start_date = date(2014,1,1),
                      result = 222222, location_level = LocationLevel.LAUNDRY_ROOM)   
        MetricFacotry(metric_type = MetricType.REVENUE_FUNDS_CREDIT_WEB_ADD_VALUE, location_id = self.room_1.id, duration = DurationType.MONTH, start_date = date(2014,1,1),
                      result = 222222, location_level = LocationLevel.LAUNDRY_ROOM)            
        MetricFacotry(metric_type = MetricType.REVENUE_FUNDS, location_id = self.room_1.id, duration = DurationType.BEFORE, start_date = date(2014,1,1,),
                      result = 222222, location_level = LocationLevel.LAUNDRY_ROOM)            


    def _check_gross_data_equality(self, x, y):
        self.assertEqual(x['display_name'], y['display_name'])
        self.assertAlmostEqual(x['revenue'], y['revenue'], 4)
        self.assertAlmostEqual(x['revenue_credit'], y['revenue_credit'], 4)
        self.assertAlmostEqual(x['revenue_cash'], y['revenue_cash'], 4)
        self.assertAlmostEqual(x['revenue_checks'], y['revenue_checks'], 4)
        self.assertAlmostEqual(x['revenue_credit_machine_starts'], y['revenue_credit_machine_starts'], 4)
        self.assertAlmostEqual(x['revenue_credit_value_add_inroom'], y['revenue_credit_value_add_inroom'], 4)
        self.assertAlmostEqual(x['revenue_credit_value_add_web'], y['revenue_credit_value_add_web'], 4)
        self.assertAlmostEqual(x['previous_revenue'], y['previous_revenue'], 4)
       
    def test_laundry_room_gross_data(self):
        self.report = ClientRevenueReport(self.billing_group, self.raw_expenses, self.start_date)
        self.data = self.report.process()
        
        laundry_room_gross = self.data['laundry_room_gross']
        self.assertEqual(len(laundry_room_gross), 2)
        
        expected_room_1_data = {'display_name': self.room_1.display_name,
                                               'revenue':100,
                                               'revenue_credit':60,
                                               'revenue_cash':22,
                                               'revenue_checks':18,
                                               'revenue_credit_machine_starts':10,
                                               'revenue_credit_value_add_inroom':15,
                                               'revenue_credit_value_add_web':35,
                                               'previous_revenue': 99
                                               }
        self._check_gross_data_equality(laundry_room_gross[self.room_1.id], expected_room_1_data)
        
        expected_room_2_data = {
                                               'display_name':  self.room_2.display_name,
                                               'revenue': 1000,
                                               'revenue_credit': 600,
                                               'revenue_cash': 220,
                                               'revenue_checks': 180,
                                               'revenue_credit_machine_starts': 100,
                                               'revenue_credit_value_add_inroom': 150,
                                               'revenue_credit_value_add_web': 350,
                                               'previous_revenue':  990
                                               }
        self._check_gross_data_equality(laundry_room_gross[self.room_2.id], expected_room_2_data)             
        
    def test_billing_group_gross_data(self):
        self.report = ClientRevenueReport(self.billing_group, self.raw_expenses, self.start_date)
        self.data = self.report.process()
               
        totals = self.data['billing_group_gross']
        expected_totals = {
                                'display_name':  'Totals',
                                'revenue': 1100,
                                'revenue_credit': 660,
                                'revenue_cash': 220+22,
                                'revenue_checks': 180+18,
                                'revenue_credit_machine_starts': 110,
                                'revenue_credit_value_add_inroom': 150+15,
                                'revenue_credit_value_add_web': 350+35,
                                'previous_revenue':  990+99
                                               }
        self._check_gross_data_equality(totals, expected_totals)    
       
    def test_expense_line_items(self):
        self.report = ClientRevenueReport(self.billing_group, self.start_date)
        self.report.raw_expenses = self.raw_expenses
        self.data = self.report.process()
                
        expenses = self.data['expense_line_items']
        self.assertAlmostEqual(expenses['internet'], 20, 4)
        self.assertAlmostEqual(expenses['Credit Card Fees'], .05*660, 4)  #NB: credit card fee is 5% and total credit card revenue was 660
        self.assertEqual(len(expenses), 2)

    def test_expense_totals(self):
        self.report = ClientRevenueReport(self.billing_group, self.raw_expenses, self.start_date)
        self.data = self.report.process()
        
        expense_totals = self.data['expense_totals']
        self.assertAlmostEqual(expense_totals, 20 + .05*660, 4)
        
    def test_net(self):
        self.report = ClientRevenueReport(self.billing_group, self.raw_expenses, self.start_date)
        self.data = self.report.process()
        
        net = self.data['net']
        expected_net = 1100-(20 + .05*660) #revenue - total expenses
        self.assertAlmostEqual(net, expected_net, 4) 
        
    def test_shares_before_mincomp(self):
        self.report = ClientRevenueReport(self.billing_group, self.raw_expenses, self.start_date)
        self.data = self.report.process()
        
        client_share_premincomp = self.data['client_share_premincomp']
        aces_share_premincomp = self.data['aces_share_premincomp']
        
        net = 1100-(20 + .05*660)
        expected_client_share_premincomp = net * .25
        expected_aces_share_premincomp = net * .75

        self.assertAlmostEqual(client_share_premincomp, expected_client_share_premincomp, 4)
        self.assertAlmostEqual(aces_share_premincomp, expected_aces_share_premincomp, 4)

    def test_mincomp(self):
        #NB: aces_share is the post min comp rule version of aces_share_premincomp
        #NB: no min comp rule is applied in this test, so aces_share should be the same as aces_share_premincomp.  ditto client_share and client_share_premincomp
        self.report = ClientRevenueReport(self.billing_group, self.raw_expenses, self.start_date)
        self.data = self.report.process()
        
        is_mincomp_applied = self.data['is_mincomp_applied']
        client_share = self.data['client_share']
        aces_share = self.data['aces_share']
        
        net = 1100-(20 + .05*660)
        expected_client_share = net * .25
        expected_aces_share = net * .75

        self.assertFalse(is_mincomp_applied)
        self.assertAlmostEqual(client_share, expected_client_share, 4)
        self.assertAlmostEqual(aces_share, expected_aces_share, 4)        
    
    def test_owed_aces_collects_cash(self):
        self.report = ClientRevenueReport(self.billing_group, self.raw_expenses, self.start_date)
        self.data = self.report.process()
        
        net = 1100-(20 + .05*660)
        expected_client_share = net * .25 #NB: No mim comp rule appleid
        epxected_owed = expected_client_share
        
        self.assertAlmostEqual(float(self.data['aces_owes_client']), epxected_owed, 4)
        self.assertAlmostEqual(float(self.data['client_owes_aces']), -1.*epxected_owed, 4)
  
    def test_owed_client_collects_cash(self):
        self.billing_group.aces_collects_cash = False
        self.billing_group.save()
        
        self.report = ClientRevenueReport(self.billing_group, self.raw_expenses, self.start_date)
        self.data = self.report.process()
        
        net = 1100-(20 + .05*660)
        expected_client_share = net * .25 #NB: No mim comp rule appleid
        epxected_owed = expected_client_share - 242  #NB: 244 is the amount of cash collected by the client.
        
        self.assertAlmostEqual(float(self.data['aces_owes_client']), epxected_owed, 4)
        self.assertAlmostEqual(float(self.data['client_owes_aces']), -1.*epxected_owed, 4)
                 
    def test_cash_collector_aces(self):
        self.report = ClientRevenueReport(self.billing_group, self.raw_expenses, self.start_date)
        self.data = self.report.process()
        self.assertEqual(self.data['cash_collector'], 'Aces')
        
    def test_cash_collector_client(self):
        self.billing_group.aces_collects_cash = False
        self.billing_group.save()
        self.report = ClientRevenueReport(self.billing_group, self.raw_expenses, self.start_date)
        self.data = self.report.process()
        self.assertEqual(self.data['cash_collector'], 'Client1')                
        

#             'is_mincomp_applied': is_mincomp_applied,
#             'client_share_premincomp': client_share_premin,
#             'aces_share_premincomp': aces_share_premin,
#             'aces_share': aces_share,
#             'client_share': client_share,
#             'owed_amount': owed_amount,
#             'owed_text': owed_text        

    
    
class TestTimesheetJobProcessor(TestCase):

    def setUp(self):
        self.jobs_tracker = TimeSheetsReportJobTracker.objects.create(user_requested_email='dispatchbackend@gmail.com')
        self.laundry_group = LaundryGroupFactory()
        self.user = FascardUserFactory(laundry_group = self.laundry_group, name='Juan Eljach')
        self.job_info = TimeSheetsReportJobInfo.objects.create(
            employee = self.user,
            start_date = date(2021,1,1),
            end_date = date(2021,1,31),
            job_tracker = self.jobs_tracker
        )

    def test_payload_creation(self):
        report = TimeSheetsReportJobProcessor()
        report.generate_report(self.job_info.id)
        self.assertEqual(self.user, report.payload.get('employee'))
        self.assertEqual(date(2021,1,1), report.payload.get('start'))
        self.assertEqual(date(2021,1,31), report.payload.get('end'))
        self.assertEqual(self.jobs_tracker, report.payload.get('job_tracker'))

    def test_report_file_creation(self):
        TimeSheetsReportJobProcessor().generate_report(self.job_info.id)
        self.jobs_tracker.refresh_from_db()
        self.assertEqual(self.jobs_tracker.generated_files.all().count(), 1)
        self.assertEqual(self.jobs_tracker.jobs_processed, 1)

    def test_zip_file_creation(self):
        """
        Tests whether or not the final zip file with all html reports is created.
        """
        TimeSheetsReportJobProcessor().generate_report(self.job_info.id)
        r = TimeSheetsJobsTrackerProcessor.run_as_job(self.jobs_tracker.id)
        self.assertTrue(r)

    #def test_report_creation(self):