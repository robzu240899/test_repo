import time
from decimal import *
from copy import deepcopy
from decimal import Decimal
from django.test import TestCase
from fascard.api import FascardApi
from reporting.models import *
from revenue.models import *
from roommanager.models import *
from roommanager.enums import *
from .enums import TransactionType, RefundChannelChoices
from .refund import FascardRefund, WipeBonus, AdditionalBonus, AuthorizeDotNetRefund

class FascardRefundTest(TestCase):
    """
    Note: Comment out @ProductionCheck decorator from refund handler definition in order to test    
    """

    def setUp(self):
        self.external_fascard_user_id = 16269 #Juan's testing account
        self.laundry_group_1 = LaundryGroup.objects.create(display_name='Laundry Group 1')
        #Via Fascard
        self.room1 = LaundryRoom.objects.create(
            laundry_group=self.laundry_group_1,
            display_name='room 1',
            time_zone=TimeZoneType.EASTERN,
            fascard_code = 1
        )
        self.slot_room1_1 = Slot.objects.create(
            laundry_room=self.room1,
            slot_fascard_id = '1',
            web_display_name = '100',
            slot_type = SlotType.STANDARD,
            is_active=True
        )
        self.laundry_transaction_2 = LaundryTransaction.objects.create(
            laundry_room=self.room1,
            slot=self.slot_room1_1,
            transaction_type = TransactionType.ADD_VALUE,
            external_fascard_id=2,
            bonus_amount=2,
            balance_amount=5,
            credit_card_amount=10,
            external_fascard_user_id=self.external_fascard_user_id,
            first_name='laundry',
            last_name='transaction 2'
        )
        self.refund_request_base_payload = {
            "transaction" : self.laundry_transaction_2,
            "additional_bonus_amount" : None,
            "refund_channel" : RefundChannelChoices.FASCARD_ADJUST,
            "refund_amount" : Decimal("1.75")
        }
        self.api = FascardApi(1)
        self.initial_bonus_payload = {
            "Bonus" : 100.0,
            "TransType" : 3,
            "TransSubType" : 0,
            "SetExactValue" : True
        }
        self.initial_balance_payload = {
            "Balance" : 100.0,
            "TransType" : 3,
            "TransSubType" : 0,
            "SetExactValue" : True
        }
        self.api.refund_loyalty_account(self.external_fascard_user_id, self.initial_bonus_payload)
        self.api.refund_loyalty_account(self.external_fascard_user_id, self.initial_balance_payload)

    def test(self):
        """
        TODO: need to refactor. refund() only takes a refund request object as parameter
        """
        current_balance = self.api.get_user_account(self.external_fascard_user_id)[0].get('Bonus')
        current_balance = Decimal(str(current_balance))
        refund_amount = self.laundry_transaction_2.balance_amount
        expected_balance = current_balance + refund_amount
        refund_request = RefundAuthorizationRequest.objects.create(
            transaction = self.laundry_transaction_2,
            external_fascard_user_id = self.external_fascard_user_id,
            refund_amount = refund_amount,
            refund_channel = 1,
            aggregator_param = 'balance_amount'
        )
        FascardRefund().refund(refund_request)
        time.sleep(15)
        new_balance = self.api.get_user_account(self.external_fascard_user_id)[0].get('Bonus')
        self.assertEqual(expected_balance, new_balance)

    def test_bonus_wipeout(self):
        time.sleep(60)
        WipeBonus().wipe_bonus(self.laundry_transaction_2)
        user_account = self.api.get_user_account(getattr(self.laundry_transaction_2, 'external_fascard_user_id'))
        account_bonus_amount = Decimal(user_account[0]['Bonus'])
        deducted_amount = self.laundry_transaction_2.bonus_amount
        initial_bonus = Decimal(self.initial_bonus_payload["Bonus"])
        self.assertEqual(account_bonus_amount, (initial_bonus - deducted_amount))

    def test_zero_additional_bonus_amount(self):
        user_initial_bonus = self.initial_bonus_payload.get('Bonus')
        user_initial_bonus = Decimal(user_initial_bonus)
        payload = deepcopy(self.refund_request_base_payload)
        payload['additional_bonus_amount'] = Decimal("0.00")
        refund_request = RefundAuthorizationRequest.objects.create(**payload)
        response = AdditionalBonus(refund_request).add()
        user_final_bonus = self.api.get_user_account(16269)[0]['Bonus']
        user_final_bonus = Decimal(user_final_bonus)
        self.assertTrue(response)
        self.assertEqual(user_initial_bonus, user_final_bonus)

    def test_large_additional_bonus_amount(self):
        user_initial_bonus = self.initial_bonus_payload.get('Bonus')
        user_initial_bonus = Decimal(user_initial_bonus)
        payload = deepcopy(self.refund_request_base_payload)
        payload['additional_bonus_amount'] = Decimal("200.00")
        refund_request = RefundAuthorizationRequest.objects.create(**payload)
        response = AdditionalBonus(refund_request).add()
        user_final_bonus = self.api.get_user_account(16269)[0]['Bonus']
        user_final_bonus = Decimal(user_final_bonus)
        self.assertFalse(response)
        self.assertEqual(user_initial_bonus, user_final_bonus)

    def test_no_additional_bonus_amount(self):
        user_initial_bonus = self.initial_bonus_payload.get('Bonus')
        user_initial_bonus = Decimal(user_initial_bonus)
        payload = deepcopy(self.refund_request_base_payload)
        payload.pop('additional_bonus_amount')
        refund_request = RefundAuthorizationRequest.objects.create(**payload)
        response = AdditionalBonus(refund_request).add()
        user_final_bonus = self.api.get_user_account(16269)[0]['Bonus']
        user_final_bonus = Decimal(user_final_bonus)
        self.assertTrue(response)
        self.assertEqual(user_initial_bonus, user_final_bonus)

    def test_valid_bonus_amount(self):
        user_initial_bonus = self.initial_bonus_payload.get('Bonus')
        user_initial_bonus = Decimal(user_initial_bonus)
        payload = deepcopy(self.refund_request_base_payload)
        payload['additional_bonus_amount'] = Decimal("5.00")
        refund_request = RefundAuthorizationRequest.objects.create(**payload)
        response = AdditionalBonus(refund_request).add()
        user_final_bonus = self.api.get_user_account(16269)[0]['Bonus']
        user_final_bonus = Decimal(user_final_bonus)
        self.assertTrue(response)
        self.assertEqual((user_initial_bonus + Decimal("5.00")), user_final_bonus)

    #TODO: Add test -> Refund managers should throw InvalidAmountException if partial refund amount
    #is greater than associated transaction amount.
