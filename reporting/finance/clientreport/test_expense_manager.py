'''
Created on Apr 17, 2017

@author: Thomas
'''

import os 
from decimal import Decimal

from django.test import TestCase

from datetime import date 

from Utils.CSVIngest.ingest import CSVIngestor

from main.settings import TEST_FILE_FOLDER

from fascard.config import FascardScrapeConfig

from roommanager.models import LaundryGroup,LaundryRoom

from ...models import ExpenseType, BillingGroupExpenseTypeMap, BillingGroup

from expense_manager import ExpenseManager


class TestExpenseManager(TestCase):
    
    def setUp(self):
        folder_name = os.path.join(TEST_FILE_FOLDER,'test_revenue_expense_manager')
        CSVIngestor(LaundryGroup,file_name = os.path.join(folder_name,'laundry_group.csv')).ingest(date_format=None,datetime_format=FascardScrapeConfig.TIME_INPUT_FORMAT)
        CSVIngestor(LaundryRoom,file_name = os.path.join(folder_name,'laundry_room.csv')).ingest(date_format=None,datetime_format=FascardScrapeConfig.TIME_INPUT_FORMAT)
        CSVIngestor(ExpenseType,file_name = os.path.join(folder_name,'expense_type.csv')).ingest(date_format=None,datetime_format=FascardScrapeConfig.TIME_INPUT_FORMAT)
        CSVIngestor(BillingGroup,file_name = os.path.join(folder_name,'billing_group.csv')).ingest(date_format=None,datetime_format=FascardScrapeConfig.TIME_INPUT_FORMAT)

        #CSVIngestor(BillingGroupExpenseTypeMap,file_name = os.path.join(folder_name,'billing_group_expense_type_map.csv')).ingest(date_format=None,datetime_format=FascardScrapeConfig.TIME_INPUT_FORMAT)
        

        
    def test_expense_manager(self):
        expenses = [{'expense_amount':.01,'expense_type':ExpenseType.objects.get(display_name='cc Processing fee')},
                    {'expense_amount':.02,'expense_type':ExpenseType.objects.get(display_name='cc Gateway')},
                    {'expense_amount':25,'expense_type':ExpenseType.objects.get(display_name='Internet fee')}
                     ]
        expense_manager = ExpenseManager(expenses=expenses,
                                         credit_card_revenue=200)
        expense_manager.process()
        self.assertEqual(expense_manager.line_items['cc Processing fee'],2)
        self.assertEqual(expense_manager.line_items['cc Gateway'],4)
        self.assertEqual(expense_manager.line_items['Internet fee'],25)
        self.assertEqual(expense_manager.total,31)
        
        
        
        
        
        
        
        
        
        
        
        
 
    
    
    