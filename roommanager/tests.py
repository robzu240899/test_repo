import random
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from django.test import TestCase
from revenue.models import LaundryTransaction
from revenue.utils import MergeTransactionsCount
from roommanager.models import LaundryGroup, LaundryRoom, Machine, Slot, CardReaderAsset, \
MachineSlotMap, HardwareBundle, BundleChangeApproval
from roommanager.job import MapOutAsset, HardwareBundleManager
from .enums import MachineType, SlotType, HardwareType

class TestMergeTransactionsCount(TestCase):

    def setUp(self):
        self.laundry_group_1 = LaundryGroup.objects.create(display_name='Laundry Group 1')
        self.laundry_room = LaundryRoom.objects.create(
            display_name = "Laundry Room #1",
            fascard_code = 1,
            laundry_group = self.laundry_group_1
        )
        self.machine_1 = Machine.objects.create(machine_type = MachineType.WASHER)
        self.machine_2 = Machine.objects.create(machine_type = MachineType.WASHER)
        self.machine_3 = Machine.objects.create(
            machine_type = MachineType.WASHER,
            placeholder = False
        )
        self.slot = Slot.objects.create(
            slot_fascard_id = 1,
            web_display_name = 'Slot #1',
            clean_web_display_name = "Slot #1 - Clean",
            slot_type = SlotType.STANDARD,
            laundry_room = self.laundry_room,
            is_active = True
        )
        start = datetime.today() - relativedelta(months=3)
        self.msm_1 = MachineSlotMap.objects.create(
            machine = self.machine_1, 
            slot=self.slot,
            start_time = start,
            end_time = start + relativedelta(months=1)
        )
        self.msm_2 = MachineSlotMap.objects.create(
            machine = self.machine_2,
            slot=self.slot,
            start_time = start + relativedelta(months=1),
            end_time = start + relativedelta(months=2)
        )
        self.msm_3 = MachineSlotMap.objects.create(
            machine = self.machine_3, 
            slot=self.slot,
            start_time = start + relativedelta(months=2)
        )
        placeholders = [self.machine_1, self.machine_2]
        for placeholder in placeholders:
            for i in range(100):
                try:
                    LaundryTransaction.objects.create(
                        external_fascard_id = random.randint(1000000,2000000),
                        fascard_record_id = random.randint(1000000,2000000),
                        machine = placeholder,
                        slot = self.slot,
                        first_name='laundry',
                        last_name='transaction 2',
                        laundry_room = self.laundry_room,
                        transaction_type = "100"
                    )
                except Exception as e:
                    raise (e)

    def test_count(self):
        count = MergeTransactionsCount().run()
        self.assertEqual(count, 200)


class TestBundleChangeApproval(TestCase):

    def setUp(self):
        self.laundry_group_1 = LaundryGroup.objects.create(display_name='Laundry Group 1')
        self.laundry_room = LaundryRoom.objects.create(
            display_name = "Laundry Room #1",
            laundry_group = self.laundry_group_1,
            fascard_code = 353
        )
        self.machine1 = Machine.objects.create(
            machine_type = MachineType.WASHER,
            asset_code = 'AAA-BBB-CCC'
        )
        self.machine2 = Machine.objects.create(
            machine_type = MachineType.WASHER,
            asset_code = 'XXX-YYY-ZZZ'
        )
        self.card_reader = CardReaderAsset.objects.create(
            card_reader_tag = 'XYZ-ABC',

        )
        self.slot = Slot.objects.create(
            web_display_name = 'Slot #1',
            clean_web_display_name = "Slot #1 - Clean",
            slot_fascard_id = '40508',
            slot_type = SlotType.STANDARD,
            laundry_room = self.laundry_room,
            is_active = True
        )
        self.original_bundle = HardwareBundle.objects.create(
            machine = self.machine1,
            card_reader = self.card_reader,
            slot = self.slot
        )
        self.scan_payload = {
            'datamatrixstring' : '1\x11HK(5oj' ,
            'assettag' : self.machine2.asset_code,
            'fascardreader' : self.card_reader.card_reader_tag,
            'submissionid' : '123456789',
            'codereadrusername' : 'juaneljach10@gmail.com',
        }

    def test_bundle_change_approval_creation(self):
        #Machine
        case3 = HardwareBundle.objects.filter(
            is_active = True,
            slot = self.slot,
            card_reader__card_reader_tag = self.card_reader.card_reader_tag
        ).last()
        bundle_manager = HardwareBundleManager(**self.scan_payload)
        bundle_manager.validate_data()
        if bundle_manager.valid:
            bundle_manager.save_model()
            bundle_manager.pair()
            if hasattr(bundle_manager, 'err_msg'):
                print (bundle_manager.err_msg)
            elif hasattr(bundle_manager, 'msg'):
                print (bundle_manager.msg)
        else:
            raise Exception(f"Invalid data: {bundle_manager.err_msg}")
        latest_bundle_change = BundleChangeApproval.objects.last()
        print (f"latest_bundle_change: {latest_bundle_change}")
        self.assertIsNotNone(latest_bundle_change)
        previous_bundle_machine = self.machine1
        self.assertEqual(previous_bundle_machine, latest_bundle_change.previous_bundle.machine)
        self.assertEqual(
            latest_bundle_change.scan_pairing.asset_code,
            self.machine2.asset_code
        )
        #Testing Approval
        latest_bundle_change.approved = True
        latest_bundle_change.save()
        latest_bundle_change.refresh_from_db()
        right_now = datetime.now()
        self.assertLess(
            (right_now - latest_bundle_change.approved_timestamp).total_seconds(), 
            60
        )


class TestAssetMapOut(TestCase):

    def setUp(self):
        self.laundry_group_1 = LaundryGroup.objects.create(display_name='Laundry Group 1')
        self.laundry_room = LaundryRoom.objects.create(
            display_name = "Laundry Room #1",
            fascard_code = 1,
            laundry_group = self.laundry_group_1
        )
        self.machine = Machine.objects.create(
            machine_type = MachineType.WASHER,
            asset_code = 'AAA-BBB'
        )
        self.slot = Slot.objects.create(
            slot_fascard_id = 1,
            web_display_name = 'Slot #1',
            clean_web_display_name = "Slot #1 - Clean",
            slot_type = SlotType.STANDARD,
            laundry_room = self.laundry_room,
            is_active = True
        )
        self.card_reader = CardReaderAsset.objects.create(
            card_reader_tag = 'XYZ-ABC',

        )
        start = datetime.today() - relativedelta(months=3)
        self.msm = MachineSlotMap.objects.create(
            machine = self.machine, 
            slot=self.slot,
            start_time = start,
            end_time = start + relativedelta(months=1)
        )
        self.bundle = HardwareBundle.objects.create(
            slot = self.slot,
            machine = self.machine,
            card_reader = self.card_reader,
            location = self.slot.laundry_room
        )

    def test_disabled_status(self):
        test_payload = {
            'asset-map-out' : 'Disabled',
            'asset_tag' : 'AAA-BBB'
        }
        manager = MapOutAsset(test_payload, 'juaneljach10@gmail.com')
        r = manager.process()
        print ("Response: {}".format(r))
        self.bundle.refresh_from_db()
        self.assertFalse(self.bundle.is_active)
        hqr = HardwareBundleRequirement.objects.filter(
            hardware_id = self.machine.id, 
            hardware_type = HardwareType.MACHINE
        )
        self.assertIsNotNone(hqr)