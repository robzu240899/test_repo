'''
Created on May 1, 2017

@author: Duong
'''
import os
import json

from django.test import TestCase
from django.contrib.auth.models import User
from rest_framework.test import force_authenticate
from rest_framework.test import APIRequestFactory

from revenue.models import Refund, LaundryTransaction
from revenue.api import group_refund_block, refund
from revenue.enums import TransactionType, RefundType
from roommanager.models import LaundryGroup, LaundryRoom, Slot, MachineSlotMap
from roommanager.enums import TimeZoneType, SlotType


class TestRefundAPI(TestCase):

    def setUp(self):
        #Set up non-modified objects used by all test methods
        self.laundry_group_1 = LaundryGroup.objects.create(display_name='Laundry Group 1')

        self.room1 = LaundryRoom.objects.create(laundry_group=self.laundry_group_1,
                                               display_name='room 1',
                                               time_zone=TimeZoneType.EASTERN,
                                               fascard_code = 1)

        self.slot_room1_1 = Slot.objects.create(laundry_room=self.room1,
                                               slot_fascard_id = '1',
                                               web_display_name = '100',
                                               slot_type = SlotType.STANDARD,
                                               is_active=True
                                               )

        #Via Authorize.Net
        self.laundry_transaction_1 = LaundryTransaction.objects.create(laundry_room=self.room1,
                                                                        slot=self.slot_room1_1,
                                                                        external_fascard_id=1,
                                                                        credit_card_amount=20,
                                                                        authorizedotnet_id='40010993540',
                                                                        last_four = '0002',
                                                                        first_name='laundry',
                                                                        last_name='transaction 1'
                                                                        )

        #Via Fascard
        self.laundry_transaction_2 = LaundryTransaction.objects.create(laundry_room=self.room1,
                                                                        slot=self.slot_room1_1,
                                                                        external_fascard_id=2,
                                                                        balance_amount=20,
                                                                        loyalty_card_number='1',
                                                                        first_name='laundry',
                                                                        last_name='transaction 2'
                                                                        )

        #Via Authorize.Net
        self.laundry_transaction_3 = LaundryTransaction.objects.create(laundry_room=self.room1,
                                                                        slot=self.slot_room1_1,
                                                                        external_fascard_id=3,
                                                                        credit_card_amount=10,
                                                                        authorizedotnet_id='40010994399 ',
                                                                        first_name='laundry',
                                                                        last_name='transaction 3'
                                                                        )

        #Via Fascard
        self.laundry_transaction_4 = LaundryTransaction.objects.create(laundry_room=self.room1,
                                                                        slot=self.slot_room1_1,
                                                                        external_fascard_id=4,
                                                                        balance_amount=10,
                                                                        loyalty_card_number='2',
                                                                        first_name='laundry',
                                                                        last_name='transaction 4'
                                                                        )

        #Via Authorize.Net
        self.laundry_transaction_5 = LaundryTransaction.objects.create(laundry_room=self.room1,
                                                                        slot=self.slot_room1_1,
                                                                        external_fascard_id=5,
                                                                        credit_card_amount=10,
                                                                        authorizedotnet_id='40010994399',
                                                                        last_four = '0015',
                                                                        first_name='laundry',
                                                                        last_name='transaction 5',
                                                                        transaction_type=TransactionType.VEND
                                                                        )

        #Via Fascard
        self.laundry_transaction_6 = LaundryTransaction.objects.create(laundry_room=self.room1,
                                                                        slot=self.slot_room1_1,
                                                                        external_fascard_id=6,
                                                                        balance_amount=20,
                                                                        loyalty_card_number='1',
                                                                        last_four = '0015',
                                                                        first_name='laundry',
                                                                        last_name='transaction 6',
                                                                        transaction_type=TransactionType.ADD_VALUE
                                                                        )

        self.user = User.objects.create_user('Foo', 'Foo@bar.com', 'testpw1')

#     def test_group_refund_block(self):
#         laundry_transactions = LaundryTransaction.objects.all()
#         refund_blocks = group_refund_block(laundry_transactions)
#         self.assertEqual(len(refund_blocks),4)
#
#
#     def test_all_transactions_are_not_eligible_to_be_refunded(self):
#         laundry_transactions = LaundryTransaction.objects.all()
#         transactions = [transaction.id for transaction in laundry_transactions]
#
#         factory = APIRequestFactory()
#         request = factory.post('/revenue/api/v1/refund', json.dumps({'transactions': transactions}), content_type="application/json")
#         force_authenticate(request, user = self.user)
#         response = refund(request)
#         self.assertEqual(response.status_code, 200)
#         # all transactions are not eligible
#         self.assertEqual(len(response.data['error_transactions']), 6)

    def test_transactions_are_eligible_to_be_refunded(self):
        self.laundry_transaction_1.transaction_type = TransactionType.ADD_VALUE
        self.laundry_transaction_1.save()
        self.laundry_transaction_2.transaction_type = TransactionType.ADD_VALUE
        self.laundry_transaction_2.save()
        self.laundry_transaction_3.transaction_type = TransactionType.VEND
        self.laundry_transaction_3.save()

        transactions = [self.laundry_transaction_1.id, self.laundry_transaction_2.id, self.laundry_transaction_3.id]
        factory = APIRequestFactory()
        request = factory.post('/revenue/api/v1/refund', json.dumps({'transactions': transactions}), content_type="application/json")
        force_authenticate(request, user = self.user)
        resp = refund(request)

        # all transactions are eligible
        self.assertEqual(len(resp.data['error_transactions']), 0)
        self.assertEqual(Refund.objects.all().count(), 3)
        self.assertTrue(LaundryTransaction.objects.get(external_fascard_id=1).is_refunded)
        self.assertTrue(LaundryTransaction.objects.get(external_fascard_id=2).is_refunded)
        self.assertTrue(LaundryTransaction.objects.get(external_fascard_id=3).is_refunded)

#     def test_transactions_already_refunded(self):
#         transactions = [self.laundry_transaction_1.id]
#
#         factory = APIRequestFactory()
#         request = factory.post('/revenue/api/v1/refund', json.dumps({'transactions': transactions}), content_type="application/json")
#         force_authenticate(request, user = self.user)
#         resp = refund(request)
#         # transaction is not eligible
#         self.assertEqual(len(resp.data['error_transactions']), 1)
#
#     def test_transaction_has_same_authorizedotnet_id_has_been_refunded(self):
#         self.laundry_transaction_3.is_refunded = True
#         self.laundry_transaction_3.save()
#         transactions = [self.laundry_transaction_5.id]
#
#         factory = APIRequestFactory()
#         request = factory.post('/revenue/api/v1/refund', json.dumps({'transactions': transactions}), content_type="application/json")
#         force_authenticate(request, user = self.user)
#         resp = refund(request)
#         # transaction is not eligible
#         self.assertEqual(self.laundry_transaction_3.authorizedotnet_id, self.laundry_transaction_5.authorizedotnet_id)
#         self.assertEqual(len(resp.data['error_transactions']), 1)
