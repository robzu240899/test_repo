import random
from datetime import datetime, date 
from decimal import Decimal
from django.contrib.auth.models import User
from django.test import TestCase
from testhelpers.factories import LaundryGroupFactory, LaundryRoomFactory, BillingGroupFactory, LaundryRoomExtensionFactory, MetricFacotry, NonRecurrentExpenseFactory, \
LaundryTransactionFactory, MachineFactory, SlotFactory, MachineSlotMap as MachineSlotMapFactory
from reporting.enums import DurationType, LocationLevel, MetricType
from reporting.finance.clientreport.report import ClientRevenueReport
from revenue.services import DamageRefundManager
from revenue.models import LaundryTransaction, RefundAuthorizationRequest
from revenue.enums import RefundChannelChoices, RefundTypeChoices, TransactionType
from .metricsfetcher import MetricsFetcher

class TestMetricsFetcher(TestCase):
    
    def setUp(self):
        TestCase.setUp(self)
        self.start_date = date(2017,1,1)
        self.laundry_group = LaundryGroupFactory()
        self.billing_group = BillingGroupFactory()
        self.billing_group_2 = BillingGroupFactory(allow_cashflow_refunds_deduction=False)
        
        self.room_1 = LaundryRoomFactory(laundry_group = self.laundry_group)
        self.room_1_extension = LaundryRoomExtensionFactory(laundry_room = self.room_1, billing_group = self.billing_group)
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

      
        #create some data for rooms that aren't assocaited with the billing group.  this data should not impact the tests
        self.dummy_billing_group = BillingGroupFactory()
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
        #self.fetcher = MetricsFetcher(self.billing_group, self.start_date)

        #Non-recurrent expenses
        NonRecurrentExpenseFactory(amount=10, laundry_room=self.room_1, approved=True)
        NonRecurrentExpenseFactory(amount=10, laundry_room=self.room_1)
        NonRecurrentExpenseFactory(amount=10, laundry_room=self.room_2)
        NonRecurrentExpenseFactory(amount=10, laundry_room=self.room_3)
        self.nonrecurrent_expenses_start_date = date(2021,7,1) #This date must be on the same month of the timestamp of the objects created above
        #TODO: Uncomment
        #Damage Refunds Pass/No Pass Expense logic
        self.damage_as_expense_fetcher_start_datetime = datetime(2021,6,1)
        self.requestor_user = User.objects.create(
            email='test@gmail.com',
            first_name='Testing account',
            username = 'testaccount'
        )
        self.requestor_user.set_password("test")
        self.requestor_user.save()
        #dummy, regular, refund
        fake_tx = LaundryTransaction.objects.create(
            external_fascard_id = 101010101,
            fascard_record_id = f"{101010101}-86",
            transaction_type =  TransactionType.VEND,
            local_transaction_time = datetime(2021,6,3),
            utc_transaction_time = datetime(2021,6,3),
            balance_amount = Decimal(20),
            laundry_room = self.room_1,
            assigned_laundry_room = self.room_1
        )
        self.dummy_refund_request = RefundAuthorizationRequest.objects.create(
            check_recipient = 'John Doe',
            aggregator_param = 'balance_amount',
            external_fascard_user_id = 16269,
            description = "TEST",
            transaction = fake_tx,
            created_by = self.requestor_user,
            refund_amount = Decimal(10),
            refund_channel = RefundChannelChoices.CHECK,
            refund_type_choice = RefundTypeChoices.DAMAGE
        )
        self.dummy_refund_request.approved = True
        self.dummy_refund_request.save()
        #Extra room and billing group for Damange refunds
        self.room_4 = LaundryRoomFactory(laundry_group = self.laundry_group)
        self.room_4_extension = LaundryRoomExtensionFactory(laundry_room=self.room_4, billing_group=self.billing_group_2)
        self.fake_tx_2 = LaundryTransaction.objects.create(
            external_fascard_id = 101010222,
            fascard_record_id = f"{101010222}-86",
            transaction_type =  TransactionType.VEND,
            local_transaction_time = datetime(2021,6,3),
            utc_transaction_time = datetime(2021,6,3),
            balance_amount = Decimal(20),
            laundry_room = self.room_4,
            assigned_laundry_room = self.room_4
        )
        self.dummy_refund_request2 = RefundAuthorizationRequest.objects.create(
            check_recipient = 'John Doe',
            aggregator_param = 'balance_amount',
            external_fascard_user_id = 16269,
            description = "TEST",
            transaction = self.fake_tx_2,
            created_by = self.requestor_user,
            refund_amount = Decimal(10),
            refund_channel = RefundChannelChoices.CHECK,
            refund_type_choice = RefundTypeChoices.DAMAGE
        )
        self.dummy_refund_request2.approved = True
        self.dummy_refund_request2.save()
    
    def _check_data_equality(self, x, y):
        self.assertEqual(x['display_name'], y['display_name'])
        self.assertAlmostEqual(x['revenue'], y['revenue'], 4)
        self.assertAlmostEqual(x['revenue_credit'], y['revenue_credit'], 4)
        self.assertAlmostEqual(x['revenue_cash'], y['revenue_cash'], 4)
        self.assertAlmostEqual(x['revenue_checks'], y['revenue_checks'], 4)
        self.assertAlmostEqual(x['revenue_credit_machine_starts'], y['revenue_credit_machine_starts'], 4)
        self.assertAlmostEqual(x['revenue_credit_value_add_inroom'], y['revenue_credit_value_add_inroom'], 4)
        self.assertAlmostEqual(x['revenue_credit_value_add_web'], y['revenue_credit_value_add_web'], 4)
        self.assertAlmostEqual(x['previous_revenue'], y['previous_revenue'], 4)
    
    def test_laundry_room_data(self):
        
        laundry_room_data = self.fetcher.laundry_room_data
        self.assertEqual(len(laundry_room_data),2)
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
        self._check_data_equality(laundry_room_data[self.room_1.id], expected_room_1_data)
        
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
        self._check_data_equality(laundry_room_data[self.room_2.id], expected_room_2_data)        
    
    def test_totals(self):
        
        totals = self.fetcher.totals
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
        self._check_data_equality(totals, expected_totals)       

    def test_get_nonrecurrent_expenses_in_totals(self):
        report_ins = ClientRevenueReport(self.billing_group, self.nonrecurrent_expenses_start_date)
        nonrecurrent_expenses = report_ins._get_nonrecurrent_expenses()
        total = sum([expense.get('expense_amount') for expense in nonrecurrent_expenses])
        self.assertEqual(10, total)

    def _damage_refund_request_creator(self, payload):
        default_start_datetime = self.damage_as_expense_fetcher_start_datetime.date()
        approval_request = DamageRefundManager().send_for_approval(payload, self.requestor_user)
        tx = approval_request.transaction
        tx.local_transaction_time = default_start_datetime
        tx.assigned_local_transaction_time = default_start_datetime
        tx.save()
        tx.refresh_from_db()
        approval_request.approved = True
        approval_request.save()
        return approval_request

    def _execute_refund(self, payload, billing_group=None):
        bg = billing_group or self.billing_group
        approval_request = self._damage_refund_request_creator(payload)
        self.damage_as_expense_fetcher = MetricsFetcher(
            bg,
            self.damage_as_expense_fetcher_start_datetime.date()
        )
        return self.damage_as_expense_fetcher.totals


    def test_bg_allow_refunds_damage_passed(self):
        """
        Test case: A Billing group allows cashflow refunds deduction by default and a damage refund
        is marked as NOT passable to landlord with the force flag set to false.

        Expected result: The damage refund MUST be passed to landlord, despite it being marked as NOT passed
        since the force flag is set to false.
        """
        bg = self.billing_group
        #create damage refund request and auto approve it.
        payload = {
            'refund_amount' : Decimal(45.0),
            'fascard_user_id' : 16269,
            'slot' : None,
            'laundry_room' : self.room_1,
            'check_payee_name' : 'John Doe',
            'description' : "damaged his gucci clothes",
            'charge_damage_to_landlord' : False,
            'force' : False,
            'refund_channel' : RefundChannelChoices.CHECK,
        }
        totals = self._execute_refund(payload)
        self.assertEqual(totals.get('refunds_check'), Decimal(55)) #45 damage refund + 10 dummy refund

    def test_bg_allow_refunds_damage_notpassed(self):
        """
        Test case: A Billing group allows cashflow refunds deduction by default and a damage refund
        is marked as NOT passable to landlord with the force flag set to True.

        Expected result: The damage refund MUST NOT be passed to landlord, despite the landlord's bg accepting cashflow refunds
        deduction by default, since the force flag is set to True.
        """
        payload = {
            'refund_amount' : Decimal(45.0),
            'fascard_user_id' : 16269,
            'slot' : None,
            'laundry_room' : self.room_1,
            'check_payee_name' : 'John Doe',
            'description' : "damaged his gucci clothes",
            'charge_damage_to_landlord' : False,
            'force' : True,
            'refund_channel' : RefundChannelChoices.CHECK,
        }
        totals = self._execute_refund(payload)
        print (totals)
        self.assertEqual(totals.get('refunds_check'), Decimal(10)) #45 damage refund + 10 dummy refund

    def test_bg_allow_refunds_damage_passed_soft(self):
        """
        Test Case: The billing group allows cashflow refunds deduction by default, charge_damage_to_landlord is set to True
        and force is set to False.

        Expected Result: The damage refund amount must be charged to the landlord
        """
        payload = {
            'refund_amount' : Decimal(45.0),
            'fascard_user_id' : 16269,
            'slot' : None,
            'laundry_room' : self.room_1,
            'check_payee_name' : 'John Doe',
            'description' : "damaged his gucci clothes",
            'charge_damage_to_landlord' : True,
            'force' : False,
            'refund_channel' : RefundChannelChoices.CHECK,
        }
        totals = self._execute_refund(payload)
        print (totals)
        self.assertEqual(totals.get('refunds_check'), Decimal(55))

    def test_bg_dont_allow_refunds_damage_forced(self):
        """
        Test Case: The Billing group does not allow cashflow refunds deductions by default and the damage refund
        is charged to landlord with force set to True

        Expected Result: the damage refund must be charged to the landlord since the force flag is set to True
        """
        payload = {
            'refund_amount' : Decimal(45.0),
            'fascard_user_id' : 16269,
            'slot' : None,
            'laundry_room' : self.room_4,
            'check_payee_name' : 'John Doe',
            'description' : "damaged his gucci clothes",
            'charge_damage_to_landlord' : True,
            'force' : True,
            'refund_channel' : RefundChannelChoices.CHECK,
        }
        totals = self._execute_refund(payload, billing_group=self.billing_group_2)
        #Only damage refund (45) is applied, dummy refund (10) is ignored
        self.assertEqual(totals.get('refunds_check'), Decimal(45))

    def test_bg_dont_allow_refunds_damage_notforced(self):
        """
        Test Case: The Billing group does not allow cashflow refunds deductions by default and the damage refund
        is charged to landlord with force set to False

        Expected Result: the damage refund MUST NO be charged to the landlord since the force flag is set to False, regardless
        of charge_damage_to_landlord being set to True
        """
        payload = {
            'refund_amount' : Decimal(45.0),
            'fascard_user_id' : 16269,
            'slot' : None,
            'laundry_room' : self.room_4,
            'check_payee_name' : 'John Doe',
            'description' : "damaged his gucci clothes",
            'charge_damage_to_landlord' : True,
            'force' : False,
            'refund_channel' : RefundChannelChoices.CHECK,
        }
        totals = self._execute_refund(payload, billing_group=self.billing_group_2)
        #The damage refund is not applied and the dummy refund is not applied
        self.assertEqual(totals.get('refunds_check'), Decimal(0))    