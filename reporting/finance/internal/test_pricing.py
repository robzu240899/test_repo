'''
Created on Dec 21, 2017

@author: tpk6
'''
from datetime import date 
from django.test import TestCase

from testhelpers.factories import PirceHistoryFactory
from testhelpers.recipes import BasicRecipeMixin

from reporting.finance.internal import pricing_report

class PricingReportTest(TestCase, BasicRecipeMixin):
    
    def setUp(self):
        TestCase.setUp(self)
        self.create_data()
        self.cycle_type_1 = 'cycle type 1'
        self.cycle_type_2 = 'cycle type 2'
        self.machine_type_1 = 'machine type 1'
        self.machine_type_2 = 'machine type 2'
        self.t0 = date(2017,1,14)
        self.t1 = date(2017,1,15)
        self.t2 = date(2017,1,16)
        self.t3 = date(2017,1,17)

    
    def create_constant_history(self, date_list, laundry_room_list, cycle_type_list, machine_type_list, price):
        '''Create a 2 day period of constant history accross laundry room's 1 and 2.  using cycle type 1 and machine type 1'''
        for dt in date_list:
            for laundry_room in laundry_room_list:
                for machine_type in machine_type_list:
                    for cycle_type in cycle_type_list:
                        PirceHistoryFactory(laundry_room = laundry_room, cycle_type = cycle_type, machine_type = machine_type,  price_date = dt,
                                            price = price)     
     

    def test_no_pricing_changes(self):
        #Two days of constant pricing history.
        self.create_constant_history([self.t1, self.t2], [self.laundry_room_1_1], [self.cycle_type_1, self.cycle_type_2], [self.machine_type_1], 2.5)
        self.create_constant_history([self.t1, self.t2], [self.laundry_room_1_2], [self.cycle_type_1, self.cycle_type_2], [self.machine_type_2], 3.5)
        report = pricing_report.PricingReport(self.t1, self.t2, [self.laundry_room_1_1.id, self.laundry_room_1_2.id], False)
        report.generate_csv()
        results = report.csv_data
        expected_headers = ['Laundry Room', 'Machine Type', 'Cycle Type', '01/15/2017 to 01/16/2017']
        expected_rows = [ [self.laundry_room_1_1.display_name, self.machine_type_1, self.cycle_type_1, 2.5],
                          [self.laundry_room_1_1.display_name, self.machine_type_1, self.cycle_type_2, 2.5],
                          [self.laundry_room_1_2.display_name, self.machine_type_2, self.cycle_type_1, 3.5],
                          [self.laundry_room_1_2.display_name, self.machine_type_2, self.cycle_type_2, 3.5],
        ]
        
        self.assertEqual(results[0], expected_headers)
        self.assertEqual(len(expected_rows)+2, len(results)) #No Extra rows, +1 to account for headers, +1 to account for blank line at the end
        for row in expected_rows:
            self.assertIn(row, results)
        
    def test_with_pricing_change(self):
        #Two days of constant pricing history. Last day has a pricing shift of 1 laundry room / machine type / cycle type combo
        self.create_constant_history([self.t1, self.t2, self.t3], [self.laundry_room_1_1], [self.cycle_type_1, self.cycle_type_2], [self.machine_type_1], 2.5)
        self.create_constant_history([self.t1, self.t2], [self.laundry_room_1_2], [self.cycle_type_1, self.cycle_type_2], [self.machine_type_2], 3.5)
        PirceHistoryFactory(laundry_room = self.laundry_room_1_2, cycle_type = self.cycle_type_1, machine_type = self.machine_type_2,  price_date = self.t3,
                    price = 3.5)     
        PirceHistoryFactory(laundry_room = self.laundry_room_1_2, cycle_type = self.cycle_type_2, machine_type = self.machine_type_2,  price_date = self.t3,
                    price = 4.5)           
      
        report = pricing_report.PricingReport(self.t1, self.t3, [self.laundry_room_1_1.id, self.laundry_room_1_2.id], False)
        report.generate_csv()
        results = report.csv_data
        expected_headers = ['Laundry Room', 'Machine Type', 'Cycle Type', '01/15/2017 to 01/16/2017', '01/17/2017 to 01/17/2017']
        expected_rows = [ [self.laundry_room_1_1.display_name, self.machine_type_1, self.cycle_type_1, 2.5, 2.5],
                          [self.laundry_room_1_1.display_name, self.machine_type_1, self.cycle_type_2, 2.5, 2.5],
                          [self.laundry_room_1_2.display_name, self.machine_type_2, self.cycle_type_1, 3.5, 3.5],
                          [self.laundry_room_1_2.display_name, self.machine_type_2, self.cycle_type_2, 3.5, 4.5],
        ]
        
        self.assertEqual(results[0], expected_headers)
        self.assertEqual(len(expected_rows)+2, len(results)) #No Extra rows, +1 to account for headers, +1 to account for blank line at the end
        for row in expected_rows:
            self.assertIn(row, results)     

        
