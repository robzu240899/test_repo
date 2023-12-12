'''
Created on Jan 25, 2018

@author: tpk6
'''


from datetime import datetime 
from django.test import TestCase
from testhelpers.recipes import BasicRecipeMixin
from testhelpers.factories import LaundryTransactionFactory, UnassignedLaundryTransactionFactory, FascardUserFactory
from matcher import WebBasedMatcher, StandardMatcher
from revenue.enums import TransactionType, AddValueSubType

class MatcherTest(TestCase, BasicRecipeMixin):
    
    def setUp(self):
        TestCase.setUp(self)
        self.create_data()
    
    def test_web_transaction_match_with_no_previous_transactions(self):
        '''A new user loads up value via the website.  There are no previous transactions that can tell us what room the user belongs to
        The user then starts a laundry machine in a room, x.  The web value adds should be attributed to room x
        The assigned time should be the future tx's time for both local and utch
        '''

        new_user = FascardUserFactory()
        tx_first_web  = UnassignedLaundryTransactionFactory(laundry_room = None, fascard_user = new_user, local_transaction_time = datetime (2015,6,1,2,3))
        tx_second_web = UnassignedLaundryTransactionFactory(laundry_room = None, fascard_user = new_user, local_transaction_time = datetime (2015,6,2,2,3))
        tx_laundry_start_2  = LaundryTransactionFactory(laundry_room = self.laundry_room_1_3, fascard_user = new_user, local_transaction_time = datetime (2015,8,1,2,3))
        tx_laundry_start_1  = LaundryTransactionFactory(laundry_room = self.laundry_room_1_4, fascard_user = new_user, local_transaction_time = datetime (2015,7,1,2,3)) #Should be matched to this room
         
        WebBasedMatcher(tx_first_web.id).match()
        tx_first_web.refresh_from_db()
         
        self.assertEqual(tx_first_web.assigned_laundry_room, self.laundry_room_1_4)
        self.assertEqual(tx_first_web.assigned_local_transaction_time, tx_laundry_start_1.local_transaction_time)
        self.assertEqual(tx_first_web.assigned_utc_transaction_time, tx_laundry_start_1.utc_transaction_time)
 
       
    def test_web_transaction_match_with_previous_transactions(self):
        '''A new user loads up value via the website.  There are no previous transactions that can tell us what room the user belongs to
        The user then starts a laundry machine in a room, x.  The web value adds should be attributed to room x.
        The assigned time should be the web value add's time for both local and utc.
        '''
         
        new_user = FascardUserFactory()
        tx_first_web  = UnassignedLaundryTransactionFactory(laundry_room = None, fascard_user = new_user, utc_transaction_time = datetime (2015,6,1,2,3),  local_transaction_time = datetime(2015,6,1,8,3))
        tx_second_web = UnassignedLaundryTransactionFactory(laundry_room = None, fascard_user = new_user, utc_transaction_time = datetime (2015,6,2,2,3))
                  
        past_tx_with_user_1 = LaundryTransactionFactory(laundry_room = self.laundry_room_1_5, fascard_user = new_user, utc_transaction_time = datetime(2015,5,1,2,3)) #Should be matched to this transaction
        past_tx_with_user_2 = LaundryTransactionFactory(laundry_room = self.laundry_room_1_6, fascard_user = new_user, utc_transaction_time = datetime(2014,5,1,2,3)) #Should not be matched to this transaction
          
        future_tx_laundry_start_2    = LaundryTransactionFactory(laundry_room = self.laundry_room_1_3, fascard_user = new_user, utc_transaction_time = datetime (2015,8,1,2,3))  #Shouldn't be used in the calcuations
        future_tx_laundry_start_1  = LaundryTransactionFactory(laundry_room = self.laundry_room_1_4, fascard_user = new_user, utc_transaction_time = datetime (2015,7,1,2,3))  #Shouldn't be used in the calcuations
       
        WebBasedMatcher(tx_first_web.id).match()
        tx_first_web.refresh_from_db()
         
        self.assertEqual(tx_first_web.assigned_laundry_room, self.laundry_room_1_5)
        self.assertEqual(tx_first_web.assigned_local_transaction_time,  datetime(2015,6,1,8,3))
        self.assertEqual(tx_first_web.assigned_utc_transaction_time, datetime(2015,6,1,2,3))
 
             
    def test_web_based_transaction_match_no_other_record_forUser(self):
        '''The user for the web based transaction has no other records that are not web based.  No assigned fields should be updated 
        '''

        new_user = FascardUserFactory()
        tx_first_web  = UnassignedLaundryTransactionFactory(laundry_room = None, fascard_user = new_user, utc_transaction_time = datetime (2015,6,1,2,3))
        tx_second_web = UnassignedLaundryTransactionFactory(laundry_room = None, fascard_user = new_user, utc_transaction_time = datetime (2015,6,2,2,3))
 
 
        WebBasedMatcher(tx_first_web.id).match()
        tx_first_web.refresh_from_db()
    
        self.assertIsNone(tx_first_web.assigned_laundry_room)
        self.assertIsNone(tx_first_web.assigned_local_transaction_time)
        self.assertIsNone(tx_first_web.assigned_utc_transaction_time)            
     
    def test_standard_matcher_on_web_based_transaction(self):
 

        new_user = FascardUserFactory()
        tx_first_web  = UnassignedLaundryTransactionFactory(laundry_room = self.laundry_room_1_1, fascard_user = new_user, utc_transaction_time = datetime (2015,6,1,2,3),  local_transaction_time = datetime(2015,6,1,8,3),
                                                            transaction_type = TransactionType.ADD_VALUE, trans_sub_type = AddValueSubType.CREDIT_ON_WEBSITE)
         
        StandardMatcher.match_all()
        tx_first_web.refresh_from_db()
         
        self.assertIsNone(tx_first_web.assigned_laundry_room)
        self.assertIsNone(tx_first_web.assigned_local_transaction_time)
        self.assertIsNone(tx_first_web.assigned_utc_transaction_time)  
         
    def test_standard_matcher_on_normall_transaction(self):     
        
        tx  = UnassignedLaundryTransactionFactory(laundry_room = self.laundry_room_1_1, utc_transaction_time = datetime(2015,6,1,2,3),  local_transaction_time = datetime(2015,6,1,8,3),
                                transaction_type = TransactionType.ADD_VALUE, trans_sub_type = AddValueSubType.CREDIT_AT_READER)

        StandardMatcher.match_all()       
        tx.refresh_from_db()
         
        self.assertEqual(tx.assigned_laundry_room, self.laundry_room_1_1)
        self.assertEqual(tx.assigned_local_transaction_time, datetime(2015,6,1,8,3))
        self.assertEqual(tx.assigned_utc_transaction_time, datetime(2015,6,1,2,3))         
        
        
        
        
        
        