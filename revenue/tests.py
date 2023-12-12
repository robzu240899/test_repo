import time
from datetime import date
from decimal import Decimal
from django.contrib.auth.models import User
from django.test import TestCase
from fascard.api import FascardApi
from reporting.enums import LocationLevel, DurationType, MetricType
from reporting.metric.calculate import CacheFramework
from revenue.models import RefundAuthorizationRequest
from revenue.enums import RefundChannelChoices
from roommanager.models import *
from roommanager.enums import TimeZoneType, SlotType, MachineType
#from revenue.ingest import 
from .services import CashoutRefundManager, DamageRefundManager
from .exceptions import BalanceChangedException


class TesteCheckRecharge(TestCase):

    def setUp(self):
        pass

    def test_recharge_balance_above(self):
        """
        Tries to trigger a balance recharge with the balance still
        above the threshold. This is supposed to fail
        """
        
        pass

    def test_recharge_balance_below(self):
        """
        Tries to trigger a balance recharge with the balance 
        below the threshold. This is supposed to succeed
        """
        pass
    

class TestSpecialRefunds(TestCase):

    def setUp(self):
        self.fascard_api = FascardApi()
        self.laundry_group = LaundryGroup.objects.create(display_name='Laundry Group 1')
        self.room = LaundryRoom.objects.create(
            laundry_group=self.laundry_group,
            display_name='room 1',
            time_zone=TimeZoneType.EASTERN,
            fascard_code = 1
        )
        self.slot = Slot.objects.create(
            laundry_room=self.room,
            slot_fascard_id = '1',
            web_display_name = '100',
            slot_type = SlotType.STANDARD,
            is_active=True
        )
        self.machine = Machine.objects.create(
            machine_type = MachineType.WASHER,
            asset_code = 'WHAT-A-NICE-MACHINE',

        )
        self.msm = MachineSlotMap.objects.create(
            slot = self.slot,
            machine = self.machine,
            start_time = datetime.now()
        )
        self.initial_balance_payload = {
            "Balance" : str(Decimal(100.0)),
            "Bonus" : str(Decimal(100.0)),
            "TransType" : 3,
            "TransSubType" : 0,
            "AdditionalInfo" : "Test",
            "SetExactValue": True
        }
        self.requestor_user = User.objects.create(
            email='test@gmail.com',
            first_name='Testing account',
            username = 'testaccount'
        )
        self.requestor_user.set_password("test")
        self.requestor_user.save()
        self.fascard_api.refund_loyalty_account(16269, self.initial_balance_payload) #test account

    def test_fakeid_collisions(self):
        hashes = []
        for _ in range(1, 100000):
            new_hash = SpecialRefundBase._compute_new_fake_id(SpecialRefundBase.CASHOUT_CODE)
            print (new_hash)
            if new_hash in hashes:
                raise Exception("Collision")
            hashes.append(new_hash)
        #self.assertEqual(collision, False)

    def _basic_cashout(self, balance_type):
        payload = {
            'cashout_amount' : Decimal(45.0),
            'check_payee_name' : 'John Doe',
            'fascard_user_id' : 16269,
            'description' : 'test',
            'cashout_balance_type' : balance_type,
        }
        approval_request = CashoutRefundManager().send_for_approval(payload, self.requestor_user)
        approval_request.approved = True
        approval_request.save()
        time.sleep(10)
        user_account = self.fascard_api.get_user_account(user_account_id=approval_request.external_fascard_user_id)[0]
        new_balance = user_account.get(payload['cashout_balance_type'])
        self.assertEqual(new_balance, (Decimal(100.0) - Decimal(45.0)))

    def test_basic_balance_cashout(self):
        self._basic_cashout("Balance")

    def test_basic_bonus_cashout(self):
        self._basic_cashout("Bonus")

    def test_cashout_balance_changed(self):
        """
        Test the case in which a refund request is sent for approval for an amount less than the user's current balance
        but the user's balance changes to an amount smaller than the requested cashout before the refund request is approved
        """
        payload = {
            'cashout_amount' : Decimal(45.0),
            'check_payee_name' : 'John Doe',
            'fascard_user_id' : 16269,
            'description' : 'test',
            'cashout_balance_type' : 'Balance',
        }
        approval_request = CashoutRefundManager().send_for_approval(payload, self.requestor_user)
        #change user's balance to 30
        self.initial_balance_payload['Balance'] = 30.0
        time.sleep(30)
        self.fascard_api.refund_loyalty_account(16269, self.initial_balance_payload)
        time.sleep(10)
        try:
            approval_request.approved = True
            approval_request.save()
        except BalanceChangedException:
            return True
        except Exception as e:
            raise Exception(e)
        raise Exception("test failed")
    

    def _test_basic_damage_refund(self, slot=None, location_levels=[LocationLevel.LAUNDRY_ROOM]):
        default_start_datetime = datetime.today()
        payload = {
            'refund_amount' : Decimal(45.0),
            'fascard_user_id' : 16269,
            'slot' : slot,
            'laundry_room' : self.room,
            'check_payee_name' : None,
            'description' : "damaged his gucci clothes",
            'charge_damage_to_landlord' : True,
            'refund_channel' : RefundChannelChoices.FASCARD_ADJUST,
        }
        approval_request = DamageRefundManager().send_for_approval(payload, self.requestor_user)
        tx = approval_request.transaction
        tx.local_transaction_time = default_start_datetime
        tx.assigned_local_transaction_time = default_start_datetime
        tx.save()
        tx.refresh_from_db()
        approval_request.approved = True
        approval_request.save()


        for duration, _ in DurationType.CHOICES:
            for location_level in location_levels:
                if location_level == LocationLevel.LAUNDRY_ROOM:
                    location_id = self.room.id
                elif location_level == LocationLevel.MACHINE:
                    location_id = self.machine.id
                metric_record = CacheFramework.calculate_and_cache(
                    MetricType.REFUNDS,
                    default_start_datetime.date(),
                    duration,
                    location_level,
                    location_id,
                    False,
                    False
                )
                if metric_record.duration == DurationType.BEFORE:
                    self.assertEqual(metric_record.result, 0)
                else:
                    self.assertEqual(metric_record.result, 45)



    def test_basic_damage_refund_no_slot_metrics(self):
        self._test_basic_damage_refund()


    def test_basic_damage_refund_with_slot_metrics(self):
        self._test_basic_damage_refund(
            slot=self.slot,
            location_levels=[LocationLevel.LAUNDRY_ROOM, LocationLevel.MACHINE])



        






