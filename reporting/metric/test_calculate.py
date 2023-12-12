'''
Created on Mar 13, 2017

@author: Linh Duong
'''
from datetime import datetime, date
from decimal import Decimal

from django.test import TestCase


from roommanager.models import LaundryGroup, LaundryRoom,Machine


from revenue.enums import TransactionType, AddValueSubType
from reporting.models import MetricsCache, BillingGroup
from reporting.metric.calculate import CacheFramework
from reporting.enums import LocationLevel, MetricType, DurationType
from reporting.metric.job import MetricsJobProcessor
from testhelpers.recipes import BasicRecipeMixin
from testhelpers import factories
from testhelpers.factories import LaundryGroupFactory, LaundryRoomFactory, BillingGroupFactory

class TestCahceFrameWork(TestCase, BasicRecipeMixin):
 
    def setUp(self):
        TestCase.setUp(self)
        self.create_data()
 
    def test_location_id(self):
        #Ensure the correct location id gets populated 
        #for laundry room
        metrics_cache = CacheFramework.calculate_and_cache(MetricType.REVENUE_FUNDS_CREDIT_DIRECT_VEND, date(2017,2,1), DurationType.YEAR, LocationLevel.LAUNDRY_ROOM, self.laundry_room_1_5.id)
        self.assertEqual(metrics_cache.location_id, self.laundry_room_1_5.id)
        #for billing group 
        metrics_cache = CacheFramework.calculate_and_cache(MetricType.REVENUE_FUNDS_CREDIT_DIRECT_VEND, date(2017,2,1), DurationType.YEAR, LocationLevel.BILLING_GROUP, self.billing_group_1_1.id)
        self.assertEqual(metrics_cache.location_id, self.billing_group_1_1.id)       
        #for machine
        metrics_cache = CacheFramework.calculate_and_cache(MetricType.REVENUE_FUNDS_CREDIT_DIRECT_VEND, date(2017,2,1), DurationType.YEAR, LocationLevel.BILLING_GROUP, self.machine_1_1_1.id)
        self.assertEqual(metrics_cache.location_id, self.machine_1_1_1.id)     
     
    def test_time_frame_day(self):
        #Ensure we account for the correct transactions when using the DAY time frame.  The day time frame looks at the start_date passed to calculate_and_cache
        slot = self.slot_1_1_1  #NB: This is associated with laundry_room_1_1
        laundry_room = slot.laundry_room
        start_date = date(2017,6,1)
        #Transactions that should be accounted for 
        factories.TransactionTypeAdaptor.create_credit_vend_at_machine(slot, 10.5, datetime(2017,6,1,1))
        factories.TransactionTypeAdaptor.create_credit_vend_at_machine(slot, 4.5, datetime(2017,6,1,2))
        factories.TransactionTypeAdaptor.create_credit_vend_at_machine(slot, 4.0, datetime(2017,6,1,2))
        #Transactions that should not be accounted for     
        factories.TransactionTypeAdaptor.create_credit_vend_at_machine(slot, 100, datetime(2018,6,1,1))
        factories.TransactionTypeAdaptor.create_credit_vend_at_machine(slot, 1000, datetime(2016,6,1,2))
        factories.TransactionTypeAdaptor.create_credit_vend_at_machine(slot, 10000, datetime(2017,6,2,2))   
        factories.TransactionTypeAdaptor.create_credit_vend_at_machine(slot, 100000, datetime(2017,5,31,2))  
 
        CacheFramework.calculate_and_cache(MetricType.REVENUE_FUNDS_CREDIT_DIRECT_VEND, start_date, DurationType.DAY, LocationLevel.LAUNDRY_ROOM, laundry_room.id)
        metric = MetricsCache.objects.get(metric_type = MetricType.REVENUE_FUNDS_CREDIT_DIRECT_VEND, start_date = start_date, duration = DurationType.DAY,
                                 location_level = LocationLevel.LAUNDRY_ROOM, location_id = laundry_room.id)
 
        self.assertAlmostEqual(float(metric.result), 19.0, places = 4)
         
    def test_time_frame_month(self):
        #Ensure we account for the correct transactions when using the MONTH time frame.  The month time frame from the state date until one month after. 
        #ex 7/1/2016 -> 7/1/2016 (inclusive) until 7/31/2016 (inclusive) 
        slot = self.slot_1_1_1  #NB: This is associated with laundry_room_1_1
        laundry_room = slot.laundry_room
        start_date = date(2017,6,1)
        #Transactions that should be accounted for 
        factories.TransactionTypeAdaptor.create_credit_vend_at_machine(slot, 10.5, datetime(2017,6,1,1))
        factories.TransactionTypeAdaptor.create_credit_vend_at_machine(slot, 4.5, datetime(2017,6,2,2))
        factories.TransactionTypeAdaptor.create_credit_vend_at_machine(slot, 4.0, datetime(2017,6,30,4))
        #Transactions that should not be accounted for     
        factories.TransactionTypeAdaptor.create_credit_vend_at_machine(slot, 100, datetime(2016,7,1,2))
        factories.TransactionTypeAdaptor.create_credit_vend_at_machine(slot, 1000, datetime(2018,6,1,1))
        factories.TransactionTypeAdaptor.create_credit_vend_at_machine(slot, 100000, datetime(2017,5,31,2))  
         
        CacheFramework.calculate_and_cache(MetricType.REVENUE_FUNDS_CREDIT_DIRECT_VEND, start_date, DurationType.MONTH, LocationLevel.LAUNDRY_ROOM, laundry_room.id)
        metric =MetricsCache.objects.get(metric_type = MetricType.REVENUE_FUNDS_CREDIT_DIRECT_VEND, start_date = start_date, duration = DurationType.MONTH,
                                 location_level = LocationLevel.LAUNDRY_ROOM, location_id = laundry_room.id)
        self.assertAlmostEqual(float(metric.result), 19.0, places = 4)
         
    def test_time_frame_year(self):
        #Ensure we account for the correct transactions when using the MONTH time frame.  The month time frame from the state date until one month after. 
        #ex 6/1/2016 -> 6/1/2016 (inclusive) until 5/31/2016 (inclusive) 
        slot = self.slot_1_1_1  #NB: This is associated with laundry_room_1_1
        laundry_room = slot.laundry_room
        start_date = date(2014,6,1)
        #Transactions that should be accounted for 
        factories.TransactionTypeAdaptor.create_credit_vend_at_machine(slot, 10.5, datetime(2014,6,1))
        factories.TransactionTypeAdaptor.create_credit_vend_at_machine(slot, 4.5, datetime(2015,1,1))
        factories.TransactionTypeAdaptor.create_credit_vend_at_machine(slot, 4.0, datetime(2015,5,31))
        #Transactions that should not be accounted for     
        factories.TransactionTypeAdaptor.create_credit_vend_at_machine(slot, 1000,  datetime(2014,5,31))
        factories.TransactionTypeAdaptor.create_credit_vend_at_machine(slot, 100000, datetime(2015,6,1))
 
        CacheFramework.calculate_and_cache(MetricType.REVENUE_FUNDS_CREDIT_DIRECT_VEND, start_date, DurationType.YEAR, LocationLevel.LAUNDRY_ROOM, laundry_room.id)
        metric =MetricsCache.objects.get(metric_type = MetricType.REVENUE_FUNDS_CREDIT_DIRECT_VEND, start_date = start_date, duration = DurationType.YEAR,
                                 location_level = LocationLevel.LAUNDRY_ROOM, location_id = laundry_room.id)
        self.assertAlmostEqual(float(metric.result), 19.0, places = 4)  
         
    def test_time_frame_before(self):
        #Ensure we account for the correct transactions when using the BEFORE time frame.  The previous time frame looks from the start_date (exclusive), backwards through all time.
        slot = self.slot_1_1_1  #NB: This is associated with laundry_room_1_1
        laundry_room = slot.laundry_room
        start_date = date(2017,6,1)
        #Transactions that should be accounted for 
        factories.TransactionTypeAdaptor.create_credit_vend_at_machine(slot, 10.5, datetime(2017,5,31,1))
        factories.TransactionTypeAdaptor.create_credit_vend_at_machine(slot, 4.5, datetime(2017,1,1,2))
        factories.TransactionTypeAdaptor.create_credit_vend_at_machine(slot, 4.0, datetime(2016,1,1,2))
         
 
        #Transactions that should not be accounted for     
        factories.TransactionTypeAdaptor.create_credit_vend_at_machine(slot, 100, datetime(2017,6,1,1))
        factories.TransactionTypeAdaptor.create_credit_vend_at_machine(slot, 1000, datetime(2018,7,1,2))
        factories.TransactionTypeAdaptor.create_credit_vend_at_machine(slot, 100000, datetime(2019,5,31,2))  
 
        CacheFramework.calculate_and_cache(MetricType.REVENUE_FUNDS_CREDIT_DIRECT_VEND, start_date, DurationType.BEFORE, LocationLevel.LAUNDRY_ROOM, laundry_room.id)
        metric =MetricsCache.objects.get(metric_type = MetricType.REVENUE_FUNDS_CREDIT_DIRECT_VEND, start_date = start_date, duration = DurationType.BEFORE,
                                 location_level = LocationLevel.LAUNDRY_ROOM, location_id = laundry_room.id)
        self.assertAlmostEqual(float(metric.result), 19.0, places = 4)  
         
    def test_location_type(self):
        #We want to create a machine, laundry room, and laundry group all with the same ids.  This allows us to test if the location level is working properly.
        pk = max([Machine.objects.all().order_by('-id').first().id, BillingGroup.objects.all().order_by('-id').first().id, LaundryGroup.objects.all().order_by('-id').first().id]) + 1
        machine = factories.MachineFactory(id = pk)
        slot = factories.SlotFactory()
        map = factories.MachineSlotMap(machine = machine, slot = slot)
        laundry_room = factories.LaundryRoomFactory(id = pk)
        laundry_room_2 = factories.LaundryRoomFactory()
        billing_group = factories.BillingGroupFactory(id = pk)
        factories.LaundryRoomExtensionFactory(billing_group = billing_group, laundry_room = laundry_room_2)
        dttm = datetime(2014, 1, 1)
         
        factories.LaundryTransactionFactory(laundry_room = laundry_room_2, transaction_type = TransactionType.VEND, credit_card_amount = 111, local_transaction_time = dttm)
        factories.LaundryTransactionFactory(laundry_room = laundry_room, transaction_type = TransactionType.VEND, credit_card_amount = 222, local_transaction_time = dttm)
        factories.LaundryTransactionFactory(machine = machine, transaction_type = TransactionType.VEND, credit_card_amount = 333, local_transaction_time = dttm)
         
        CacheFramework.calculate_and_cache(MetricType.REVENUE_FUNDS_CREDIT_DIRECT_VEND, dttm.date(), DurationType.DAY, LocationLevel.BILLING_GROUP, pk)
        metric = MetricsCache.objects.get(metric_type = MetricType.REVENUE_FUNDS_CREDIT_DIRECT_VEND, start_date = dttm.date(), duration = DurationType.DAY,
                                 location_level = LocationLevel.BILLING_GROUP, location_id = billing_group.id)
        self.assertAlmostEqual(float(metric.result), 111, places=4)     
         
        CacheFramework.calculate_and_cache(MetricType.REVENUE_FUNDS_CREDIT_DIRECT_VEND, dttm.date(), DurationType.DAY, LocationLevel.LAUNDRY_ROOM, pk)
        metric = MetricsCache.objects.get(metric_type = MetricType.REVENUE_FUNDS_CREDIT_DIRECT_VEND, start_date = dttm.date(), duration = DurationType.DAY,
                                 location_level = LocationLevel.LAUNDRY_ROOM, location_id = pk)
        self.assertAlmostEqual(float(metric.result), 222, places=4)       
           
         
        CacheFramework.calculate_and_cache(MetricType.REVENUE_FUNDS_CREDIT_DIRECT_VEND, dttm.date(), DurationType.DAY, LocationLevel.MACHINE, pk)
        metric = MetricsCache.objects.get(metric_type = MetricType.REVENUE_FUNDS_CREDIT_DIRECT_VEND, start_date = dttm.date(), duration = DurationType.DAY,
                                 location_level = LocationLevel.MACHINE, location_id = pk)
        self.assertAlmostEqual(float(metric.result), 333, places=4)               
     

class TestMetrics(TestCase, BasicRecipeMixin):
 
        
        
    def setUp(self):
        TestCase.setUp(self)
        self.create_data()
        self.slot = self.slot_1_1_1
        self.laundry_room  = self.slot.laundry_room
        self.dttm = datetime(2014,1,1,1)
        self.dt = date(2014,1,1)
        

    def test_revenue_funds(self):
        #Credit Direct Vend
        factories.TransactionTypeAdaptor.create_credit_vend_at_machine(self.slot, 10.5, self.dttm)  
        #Credit Add Value Card Present 
        factories.TransactionTypeAdaptor.create_credit_value_add_card_present(self.laundry_room, 200.5, self.dttm)  
        #Credit Add Value Web
        factories.TransactionTypeAdaptor.create_credit_value_add_web(self.laundry_room, 3000.5, self.dttm)  
        #Cash Add Value 
        factories.TransactionTypeAdaptor.create_cash_value_add_at_kiosk(self.laundry_room, 40000.5, self.dttm)
        #Check Add Value 
        factories.TransactionTypeAdaptor.create_check_deposit(self.laundry_room, 7000000.5, self.dttm)
        #Start machine with Loyalty Card
        factories.TransactionTypeAdaptor.create_loyalty_card_vend_at_machine(self.slot, 500000.5, self.dttm)

        CacheFramework.calculate_and_cache(MetricType.REVENUE_FUNDS,  self.dt, DurationType.MONTH, LocationLevel.LAUNDRY_ROOM,  self.laundry_room.id)
        
        metric = MetricsCache.objects.get(metric_type = MetricType.REVENUE_FUNDS, start_date =  self.dt, location_level = LocationLevel.LAUNDRY_ROOM, location_id =  self.laundry_room.id)
        self.assertAlmostEqual(float(metric.result), 10.5+200.5+3000.5+40000.5+7000000.5, places = 4)           
        
    def test_revenue_funds_credit_direct_vend(self):
        #Credit Direct Vend
        factories.TransactionTypeAdaptor.create_credit_vend_at_machine(self.slot, 10.5, self.dttm)  
        #Credit Add Value Card Present 
        factories.TransactionTypeAdaptor.create_credit_value_add_card_present(self.laundry_room, 200.5, self.dttm)  
        #Credit Add Value Web
        factories.TransactionTypeAdaptor.create_credit_value_add_web(self.laundry_room, 3000.5, self.dttm)  
        #Cash Add Value 
        factories.TransactionTypeAdaptor.create_cash_value_add_at_kiosk(self.laundry_room, 40000.5, self.dttm)
        #Start machine with Loyalty Card
        factories.TransactionTypeAdaptor.create_loyalty_card_vend_at_machine(self.slot, 500000.5, self.dttm)
        #Check Add Value 
        factories.TransactionTypeAdaptor.create_check_deposit(self.laundry_room, 7000000.5, self.dttm)
        

        CacheFramework.calculate_and_cache(MetricType.REVENUE_FUNDS_CREDIT_DIRECT_VEND,  self.dt, DurationType.MONTH, LocationLevel.LAUNDRY_ROOM,  self.laundry_room.id)
        
        metric = MetricsCache.objects.get(metric_type = MetricType.REVENUE_FUNDS_CREDIT_DIRECT_VEND, start_date =  self.dt, location_level = LocationLevel.LAUNDRY_ROOM, location_id =  self.laundry_room.id)
        self.assertAlmostEqual(float(metric.result), 10.5, places = 4)        
        
    def test_revenue_funds_credit_present_add_value(self):
        #Credit Direct Vend
        factories.TransactionTypeAdaptor.create_credit_vend_at_machine(self.slot, 10.5, self.dttm)  
        #Credit Add Value Card Present 
        factories.TransactionTypeAdaptor.create_credit_value_add_card_present(self.laundry_room, 200.5, self.dttm)  
        #Credit Add Value Web
        factories.TransactionTypeAdaptor.create_credit_value_add_web(self.laundry_room, 3000.5, self.dttm)  
        #Cash Add Value 
        factories.TransactionTypeAdaptor.create_cash_value_add_at_kiosk(self.laundry_room, 40000.5, self.dttm)
        #Start machine with Loyalty Card
        factories.TransactionTypeAdaptor.create_loyalty_card_vend_at_machine(self.slot, 500000.5, self.dttm)
        #Check Add Value 
        factories.TransactionTypeAdaptor.create_check_deposit(self.laundry_room, 7000000.5, self.dttm)
        

        CacheFramework.calculate_and_cache(MetricType.REVENUE_FUNDS_CREDIT_PRESENT_ADD_VALUE,  self.dt, DurationType.MONTH, LocationLevel.LAUNDRY_ROOM,  self.laundry_room.id)
        
        metric = MetricsCache.objects.get(metric_type = MetricType.REVENUE_FUNDS_CREDIT_PRESENT_ADD_VALUE, start_date =  self.dt, location_level = LocationLevel.LAUNDRY_ROOM, location_id =  self.laundry_room.id)
        self.assertAlmostEqual(float(metric.result), 200.5, places = 4)           
    
    def test_revenue_funds_credit_web_add_value(self):
        #Credit Direct Vend
        factories.TransactionTypeAdaptor.create_credit_vend_at_machine(self.slot, 10.5, self.dttm)  
        #Credit Add Value Card Present 
        factories.TransactionTypeAdaptor.create_credit_value_add_card_present(self.laundry_room, 200.5, self.dttm)  
        #Credit Add Value Web
        factories.TransactionTypeAdaptor.create_credit_value_add_web(self.laundry_room, 3000.5, self.dttm)  
        #Cash Add Value 
        factories.TransactionTypeAdaptor.create_cash_value_add_at_kiosk(self.laundry_room, 40000.5, self.dttm)
        #Start machine with Loyalty Card
        factories.TransactionTypeAdaptor.create_loyalty_card_vend_at_machine(self.slot, 500000.5, self.dttm)
        #Check Add Value 
        factories.TransactionTypeAdaptor.create_check_deposit(self.laundry_room, 7000000.5, self.dttm)
        

        CacheFramework.calculate_and_cache(MetricType.REVENUE_FUNDS_CREDIT_WEB_ADD_VALUE,  self.dt, DurationType.MONTH, LocationLevel.LAUNDRY_ROOM,  self.laundry_room.id)
        
        metric = MetricsCache.objects.get(metric_type = MetricType.REVENUE_FUNDS_CREDIT_WEB_ADD_VALUE, start_date =  self.dt, location_level = LocationLevel.LAUNDRY_ROOM, location_id =  self.laundry_room.id)
        self.assertAlmostEqual(float(metric.result), 3000.5, places = 4)                   
    
    def test_revenue_funds_credit(self):
        #Credit Direct Vend
        factories.TransactionTypeAdaptor.create_credit_vend_at_machine(self.slot, 10.5, self.dttm)  
        #Credit Add Value Card Present 
        factories.TransactionTypeAdaptor.create_credit_value_add_card_present(self.laundry_room, 200.5, self.dttm)  
        #Credit Add Value Web
        factories.TransactionTypeAdaptor.create_credit_value_add_web(self.laundry_room, 3000.5, self.dttm)  
        #Cash Add Value 
        factories.TransactionTypeAdaptor.create_cash_value_add_at_kiosk(self.laundry_room, 40000.5, self.dttm)
        #Start machine with Loyalty Card
        factories.TransactionTypeAdaptor.create_loyalty_card_vend_at_machine(self.slot, 500000.5, self.dttm)
        #Check Add Value 
        factories.TransactionTypeAdaptor.create_check_deposit(self.laundry_room, 7000000.5, self.dttm)
        

        CacheFramework.calculate_and_cache(MetricType.REVENUE_FUNDS_CREDIT,  self.dt, DurationType.MONTH, LocationLevel.LAUNDRY_ROOM,  self.laundry_room.id)
        
        metric = MetricsCache.objects.get(metric_type = MetricType.REVENUE_FUNDS_CREDIT, start_date =  self.dt, location_level = LocationLevel.LAUNDRY_ROOM, location_id =  self.laundry_room.id)
        self.assertAlmostEqual(float(metric.result), 10.5+200.5+3000.5, places = 4)      

    def test_revenue_funds_cash(self):
        #Credit Direct Vend
        factories.TransactionTypeAdaptor.create_credit_vend_at_machine(self.slot, 10.5, self.dttm)  
        #Credit Add Value Card Present 
        factories.TransactionTypeAdaptor.create_credit_value_add_card_present(self.laundry_room, 200.5, self.dttm)  
        #Credit Add Value Web
        factories.TransactionTypeAdaptor.create_credit_value_add_web(self.laundry_room, 3000.5, self.dttm)  
        #Cash Add Value 
        factories.TransactionTypeAdaptor.create_cash_value_add_at_kiosk(self.laundry_room, 40000.5, self.dttm)
        #Start machine with Loyalty Card
        factories.TransactionTypeAdaptor.create_loyalty_card_vend_at_machine(self.slot, 500000.5, self.dttm)
        #Check Add Value 
        factories.TransactionTypeAdaptor.create_check_deposit(self.laundry_room, 7000000.5, self.dttm)
        
        CacheFramework.calculate_and_cache(MetricType.REVENUE_FUNDS_CASH,  self.dt, DurationType.MONTH, LocationLevel.LAUNDRY_ROOM,  self.laundry_room.id)
        
        metric = MetricsCache.objects.get(metric_type = MetricType.REVENUE_FUNDS_CASH, start_date =  self.dt, location_level = LocationLevel.LAUNDRY_ROOM, location_id =  self.laundry_room.id)
        self.assertAlmostEqual(float(metric.result), 40000.5, places = 4)             

    def test_revenue_funds_check(self):
        #Credit Direct Vend
        factories.TransactionTypeAdaptor.create_credit_vend_at_machine(self.slot, 10.5, self.dttm)  
        #Credit Add Value Card Present 
        factories.TransactionTypeAdaptor.create_credit_value_add_card_present(self.laundry_room, 200.5, self.dttm)  
        #Credit Add Value Web
        factories.TransactionTypeAdaptor.create_credit_value_add_web(self.laundry_room, 3000.5, self.dttm)  
        #Cash Add Value 
        factories.TransactionTypeAdaptor.create_cash_value_add_at_kiosk(self.laundry_room, 40000.5, self.dttm)
        #Start machine with Loyalty Card
        factories.TransactionTypeAdaptor.create_loyalty_card_vend_at_machine(self.slot, 500000.5, self.dttm)
        #Check Add Value 
        factories.TransactionTypeAdaptor.create_check_deposit(self.laundry_room, 7000000.5, self.dttm)
        
        CacheFramework.calculate_and_cache(MetricType.REVENUE_FUNDS_CHECK,  self.dt, DurationType.MONTH, LocationLevel.LAUNDRY_ROOM,  self.laundry_room.id)
        
        metric = MetricsCache.objects.get(metric_type = MetricType.REVENUE_FUNDS_CHECK, start_date =  self.dt, location_level = LocationLevel.LAUNDRY_ROOM, location_id =  self.laundry_room.id)
        self.assertAlmostEqual(float(metric.result), 7000000.5, places = 4)  


    def test_earned(self):
        #Credit Direct Vend (ie machine start)
        factories.TransactionTypeAdaptor.create_credit_vend_at_machine(self.slot, 10.5, self.dttm)  
        #Credit Add Value Card Present 
        factories.TransactionTypeAdaptor.create_credit_value_add_card_present(self.laundry_room, 200.5, self.dttm)  
        #Credit Add Value Web
        factories.TransactionTypeAdaptor.create_credit_value_add_web(self.laundry_room, 3000.5, self.dttm)  
        #Cash Add Value 
        factories.TransactionTypeAdaptor.create_cash_value_add_at_kiosk(self.laundry_room, 40000.5, self.dttm)
        #Loyalty Direct Vend (ie machine start)
        factories.TransactionTypeAdaptor.create_loyalty_card_vend_at_machine(self.slot, 500000.5, self.dttm)
        #Check Add Value 
        factories.TransactionTypeAdaptor.create_check_deposit(self.laundry_room, 7000000.5, self.dttm)
        

        CacheFramework.calculate_and_cache(MetricType.REVENUE_EARNED,  self.dt, DurationType.MONTH, LocationLevel.LAUNDRY_ROOM,  self.laundry_room.id)
        
        metric = MetricsCache.objects.get(metric_type = MetricType.REVENUE_EARNED, start_date =  self.dt, location_level = LocationLevel.LAUNDRY_ROOM, location_id =  self.laundry_room.id)
        self.assertAlmostEqual(float(metric.result), 500000.5 + 10.5, places = 4)  

    #TODO: Complete
    def test_refunds(self):
        factories.TransactionTypeAdaptor.create_credit_vend_at_machine(
            self.slot,
            10.5,
            self.dttm,
            is_refunded = True,
            refund = self.refund_obj,
            assigned_laundry_room = self.laundry_room
        )
        CacheFramework.calculate_and_cache(
            MetricType.REFUNDS,
            self.dt,
            DurationType.MONTH,
            LocationLevel.LAUNDRY_ROOM,
            self.laundry_room.id
        )

        
        
    def test_zero_dollar(self):
           
        slot = self.slot_1_1_1
        laundry_room  = slot.laundry_room
        dttm = datetime(2014,1,1,1)
        dt = date(2014,1,1)
           
        factories.LaundryTransactionFactory(slot = slot, transaction_type = TransactionType.VEND, credit_card_amount = 1.0, cash_amount=0, balance_amount=1.0, local_transaction_time = dttm)
        factories.LaundryTransactionFactory(slot = slot, transaction_type = TransactionType.VEND, credit_card_amount = 0,  cash_amount=1.0, balance_amount=1.0, local_transaction_time = dttm)
        factories.LaundryTransactionFactory(slot = slot, transaction_type = TransactionType.VEND, credit_card_amount = 0,  cash_amount=1.0, balance_amount=1.0, local_transaction_time = dttm)
           
        factories.LaundryTransactionFactory(slot = slot, transaction_type = TransactionType.VEND, credit_card_amount = 0, cash_amount = 0, balance_amount = 0, local_transaction_time = dttm)
        factories.LaundryTransactionFactory(slot = slot, transaction_type = TransactionType.VEND, credit_card_amount = None, cash_amount = 0, balance_amount = None, local_transaction_time = dttm)
   
        CacheFramework.calculate_and_cache(MetricType.REVENUE_NUM_ZERO_DOLLAR_TRANSACTIONS, dt, DurationType.MONTH, LocationLevel.LAUNDRY_ROOM, laundry_room.id)
        metric = MetricsCache.objects.get(metric_type = MetricType.REVENUE_NUM_ZERO_DOLLAR_TRANSACTIONS, start_date = dt, location_level = LocationLevel.LAUNDRY_ROOM, location_id = laundry_room.id)
        self.assertAlmostEqual(float(metric.result), 2, places = 4)
          
    def test_number_days_with_no_data(self):
           
        slot = self.slot_1_1_1
        laundry_room  = slot.laundry_room
        dttm = datetime(2014,1,1,1)
        dt = date(2014,1,1)
   
        factories.LaundryTransactionFactory(slot = slot, transaction_type = TransactionType.VEND, credit_card_amount = 1.0, local_transaction_time = datetime(2014,1,1,1))
        factories.LaundryTransactionFactory(slot = slot, transaction_type = TransactionType.VEND, credit_card_amount = 1.0, local_transaction_time = datetime(2014,1,15,1))
        factories.LaundryTransactionFactory(slot = slot, transaction_type = TransactionType.VEND, credit_card_amount = 1.0, local_transaction_time =  datetime(2014,1,31,1))
           
        CacheFramework.calculate_and_cache(MetricType.REVENUE_NUM_NO_DATA_DAYS, dt, DurationType.MONTH, LocationLevel.LAUNDRY_ROOM, laundry_room.id)
        metric = MetricsCache.objects.get(metric_type = MetricType.REVENUE_NUM_NO_DATA_DAYS, start_date = dt, location_level = LocationLevel.LAUNDRY_ROOM, location_id = laundry_room.id)
        self.assertAlmostEqual(float(metric.result), 28, places = 4)


class TestMetricsWatcher(TestCase):

    def setUp(self):
        self.laundry_group = LaundryGroupFactory()
        self.billing_group = BillingGroupFactory()
        self.billing_group_2 = BillingGroupFactory(allow_cashflow_refunds_deduction=False)
        
        self.room_1 = LaundryRoomFactory(laundry_group = self.laundry_group)

    def test_expected_metrics_when_durationtype_isnot_month(self):
        rooms = LaundryRoom.objects.all().values_list('id', flat=True).distinct()
        payload = {
            'duration' :  DurationType.DAY,
            'location_level' : LocationLevel.LAUNDRY_ROOM,
            'start_date' : date(2021,7,1)
        }
        watcher = MetricsJobProcessor._get_metrics_watcher(payload, rooms)
        expected = (rooms.count() * len(MetricType.CHOICES)) -1 #Refunds not included when DurationType != MONTH
        self.assertEqual(expected, watcher.expected)

    def test_expected_metrics_when_durationtype_is_before(self):
        rooms = LaundryRoom.objects.all().values_list('id', flat=True).distinct()
        payload = {
            'duration' :  DurationType.BEFORE,
            'location_level' : LocationLevel.LAUNDRY_ROOM,
            'start_date' : date(2021,7,1)
        }
        watcher = MetricsJobProcessor._get_metrics_watcher(payload, rooms)
        expected = (rooms.count() * len(MetricType.CHOICES)) -3 
        #Exclude REVENUE_NUM_NO_DATA_DAYS and REVENUE_NUM_ZERO_DOLLAR_TRANSACTIONS
        #and exclude REFUNDS as well, since BEFORE != Month
        self.assertEqual(expected, watcher.expected)