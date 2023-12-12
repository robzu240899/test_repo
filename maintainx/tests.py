from datetime import datetime
from django.test import TestCase
from roommanager.models import HardwareBundle, MaintainxWorkOrderRecord
from roommanager.enums import BundleType
from testhelpers import factories
from .api import MaintainxAPI
from .managers.managers import MaintainxLocationManager, MaintainxMachineManager, MaintainxCardReaderManager, MaintainxWorkOrderManager
from django.test import SimpleTestCase
import time
from .jobs import MaintainxSync as ms

# Create your tests here.
class LocationsManagerTests(TestCase):
    """
    In order to pass all this cases the @ProductionCheck should be commented out momentarily from the methods invoked
    """

    def setUp(self):
        self.laundry_group = factories.LaundryGroupFactory()
        self.billing_group = factories.BillingGroupFactory()
        self.room = factories.LaundryRoomFactory(laundry_group = self.laundry_group, display_name='Testing Location')
        self.manager = MaintainxLocationManager()

    def down(self):
        print ("Implement logic that deletes all junk objects created in Maintainx")
        pass

    def _create_location(self):
        response = self.manager.create_location(self.room)
        self.room.refresh_from_db()

    def _delete_location(self, maintainx_id):
        self.manager.delete_location(self.room)

    def test_create_location(self):
        self._create_location()
        self.assertIsNot(self.room.maintainx_id, None)

    def test_update_location(self):
        kwargs = {
            'name' : 'Testing Location Name Updated'
        }
        self.manager.create_location(self.room)
        self.room.refresh_from_db()
        response = self.manager.update_location(self.room, **kwargs)
        self.assertEqual(response.get('name'), 'Testing Location Name Updated')

    def test_deactivate_location(self):
        self.manager.create_location(self.room)
        response = self.manager.deactivate_location(self.room)
        self.assertIn('DISABLED', response.get('name'))

    def test_delete_location(self):
        """
        Maintainx DELETE implementation is sort of buggy. If you delete the location via endpoint
        you can still retrieve it after deletion. So we don't really have a way to test for successful delete.
        Instead, we print the deleted id to console output and check it manually in Maintainx's UI.
        """
        self._create_location()
        print (self.room.maintainx_id)
        self.assertIsNot(self.room.maintainx_id, None)
        self._delete_location(self.room)

    def test_activate_location(self):
        self.test_deactivate_location()
        response = self.manager.activate_location(self.room)
        self.assertEqual(response.get('name'), self.room.display_name)

    def test_update_room_meter(self):
        self._create_location()
        self.assertIsNot(self.room.maintainx_id, None)


class MaintainxAssetTests(TestCase):

    def setUp(self):
        self.api = MaintainxAPI()
        self.machine_manager = MaintainxMachineManager()
        self.cardreader_manager = MaintainxCardReaderManager()
        self.location_manager = MaintainxLocationManager()
        self.laundry_group = factories.LaundryGroupFactory(display_name='EmpireState')
        self.billing_group = factories.BillingGroupFactory()
        self.room = factories.LaundryRoomFactory(laundry_group = self.laundry_group, display_name='Testing Location')
        self.slot = factories.SlotFactory(laundry_room = self.room, slot_fascard_id = 546, web_display_name = 1, clean_web_display_name = 1)
        self.equipment_type = factories.EquipmentTypeFactory()
        self.machine = factories.MachineFactory(
            placeholder=False,
            equipment_type = self.equipment_type,
            asset_code = 'TEST-MACHINE-CODE',
            asset_serial_number = '123456789'
        )
        self.card_reader = factories.CardReaderFactory(
            card_reader_tag = 'TEST-CARDREADER-CODE',
            serial = '987654321',
        )
        self.card_reader_2 = factories.CardReaderFactory(
            card_reader_tag = 'TEST-CARDREADER2-CODE',
            serial = '984321111',
        )
        self.map = factories.MachineSlotMap(slot = self.slot, machine = self.machine)
        #Hardware Bundle
        self.hardware_bundle = HardwareBundle.objects.create(
            slot = self.slot,
            machine = self.machine,
            card_reader = self.card_reader,
            location = self.room,
            start_time = datetime(2021,5,1),
            is_active = True,
            bundle_type = BundleType.SINGLE
        )
        self.location_manager.create_location(self.room)
        self.slot_2 = factories.SlotFactory(laundry_room = self.room, slot_fascard_id = 547, web_display_name = 2, clean_web_display_name = 2)
        self.machine_2 = factories.MachineFactory(
            placeholder=False,
            equipment_type = self.equipment_type,
            asset_code = 'TEST-MACHINE2-CODE',
            asset_serial_number = '1111222233'
        )
        self.map_2 = factories.MachineSlotMap(slot = self.slot_2, machine = self.machine_2)
        self.hardware_bundle_2 = HardwareBundle.objects.create(
            slot = self.slot_2,
            machine = self.machine_2,
            card_reader = self.card_reader_2,
            location = self.room,
            start_time = datetime(2021,5,1),
            is_active = True,
            bundle_type = BundleType.SINGLE
        )

    def test_machine_and_meter_creation(self):
        self.room.refresh_from_db()
        created = self.machine_manager.create_or_update(self.machine)
        self.assertTrue(created)
        self.machine.refresh_from_db()
        self.assertIsNotNone(getattr(self.machine, 'meter'))        

    def test_cardreader_and_meter_creation(self):
        self.room.refresh_from_db()
        created = self.cardreader_manager.create_or_update(self.card_reader)
        self.assertTrue(created)
        self.card_reader.refresh_from_db()
        self.assertIsNotNone(getattr(self.card_reader, 'meter'))

    def test_update_machine_and_meter(self):
        """
        Must change TEST-UPDATED-CODE11 for a new random asset code everytime.
        Right now, Maintainx complains for the asset code not being unique, even if you explicitly deleted
        the asset associated with that asset code.
        """
        created = self.machine_manager.create_or_update(self.machine_2)
        self.assertTrue(created)
        self.machine_2.asset_code = 'TEST-UPDATED-CODE1123324234'
        self.machine_2.save()
        self.machine_2.refresh_from_db()
        created = self.machine_manager.create_or_update(self.machine_2)
        self.assertFalse(created)
        self.assertIn('TEST-UPDATED-CODE1123324234', self.api.get_asset(self.machine_2.maintainx_id)['name'])

    def test_update_asset_custom_field(self):
        created = self.machine_manager.create_or_update(self.machine)
        self.assertTrue(created)
        self.machine.asset_serial_number = 111111
        self.machine.save()
        self.machine.refresh_from_db()
        created = self.machine_manager.create_or_update(self.machine)
        self.assertFalse(created)
        self.assertEqual(
            str(111111), 
            str(self.api.get_asset(self.machine.maintainx_id)['extraFields']['Serial Number'])
        )

    def test_update_custom_field_independently(self):
        created = self.machine_manager.create_or_update(self.machine)
        self.api.update_custom_field(self.machine.maintainx_id, {'Serial Number' : str(100200)})
        self.assertEqual(
            str(100200), 
            str(self.api.get_asset(self.machine.maintainx_id)['extraFields']['Serial Number'])
        )

    def test_update_meter_reading(self):
        created = self.machine_manager.create_or_update(self.machine)
        meter_obj = getattr(self.machine , 'meter')
        meter_obj.transactions_counter = 100
        meter_obj.save()
        meter_obj.refresh_from_db()
        response = self.api.update_asset_meter_reading(meter_obj, 'transactions_counter')
        self.assertEqual(response.get('readingValue'), 100)


class WorkOrderManagerTests(TestCase):

    def setUp(self):
        self.api = MaintainxAPI()
        self.manager = MaintainxWorkOrderManager()

    def test_create_work_order_no_title(self):
        payload = {
            'category': 'Mechanical'
        }
        self.assertRaises(AssertionError, self.manager.create_work_order, payload)

    def test_create_work_order_unknown_category(self):
        payload = {
            'title': 'test work order',
            'categories': ['Test Category']
        }
        self.assertRaises(AssertionError, self.manager.create_work_order, payload)

    def test_create_valid_work_order(self):
        #create then
        payload = {
            "title": "Test Work Order",
            "categories" : ["Preventive"],
            "description" : "test work order description",
            "assignees": [{"type": "USER", "id": "110230"}],
        }
        response = self.manager.create_work_order(payload)
        self.assertGreaterEqual(response, 0)
        self.manager.delete_work_order(response)

    def test_work_order_ingest(self):
        """
        Based on manually created work order in Maintainx: 
        https://app.getmaintainx.com/workorders/2290129
        """
        self.manager._sync_records()
        work_order = MaintainxWorkOrderRecord.objects.get(maintainx_id=2290129)
        self.assertEqual(2, work_order.parts.all().count())
        self.assertEqual(2, work_order.assignees.all().count())


class ResetCounterMaintainxTests(SimpleTestCase):

    def setUp(self) -> None:
        self.count = 55
        self.start = time.time()

    def test_not_reset_counter(self):
        """
        Calculate the value of the counter when it is 55.
        The return value does not change, so when evaluating it with 0 these 2 values are not equal
        """
        count = self.count
        start = self.start
        expected_count = 0

        self.count, self.start = ms.reset_counters(count, start)
        self.assertNotEqual(self.count, expected_count, 'The counter should not change at this time')

    def test_reset_counter_to_zero(self):
        """
        Calculate the value of the counter when it is 60.
        return value = 0
        """
        count = 60
        start = self.start
        expected_count = 0

        self.count, self.start = ms.reset_counters(count, start)
        self.assertEqual(self.count, expected_count, 'The expected value of the counter should be 0')

    def test_exec_time(self):
        """
        Calculate the execution time of the test method.
        Initially the algorithm finishes its execution in less than 1 sec.
        """
        st = time.time()
        count = 60
        start = self.start

        self.count, self.start = ms.reset_counters(count, start)
        fn = time.time()
        calc = fn - st
        self.assertGreater(calc, 60)
