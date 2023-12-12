from datetime import datetime
from django.test import TestCase
from roommanager.models import *
from roommanager.enums import *
from .api import UpkeepAPI
from .manager import UpkeepAssetManager

class TestUpkeepManager(UpkeepAssetManager):

    def _get_custom_fields_payload(self, machine):
        return [
            {
                'name' : 'asset_make_serial',
                'value' : str(getattr(machine, 'asset_serial_number', '')),
                'unit' : 'serial_number'
            },
            {
                'name' : 'test',
                'value' : '100100100',
                'unit' : 'cm'
            }
        ]

# Create your tests here.
class testUpkeepCustomFields(TestCase):

    def setUp(self):
        self.laundry_group_1 = LaundryGroup.objects.create(display_name='Laundry Group 1')
        self.asset_upkeep_id = 'DSqMcXy9KG'
        self.laundry_room = LaundryRoom.objects.create(
            display_name = "Laundry Room #1",
            laundry_group = self.laundry_group_1,
            fascard_code = 353,
            upkeep_code = 'cAcOBmhosY'
        )
        self.slot = Slot.objects.create(
            web_display_name = 'Slot #1',
            clean_web_display_name = "Slot #1 - Clean",
            slot_fascard_id = '40508',
            slot_type = SlotType.STANDARD,
            laundry_room = self.laundry_room,
            is_active = True
        )
        self.equipment = EquipmentType.objects.create(
            fascard_id = 10313,
            machine_text = 'Wascomat -- Crossover Washer -- MLV cxn - Copy',
            machine_type = 0,
            laundry_group = self.laundry_group_1
        )
        self.machine = Machine.objects.create(
            machine_type = 0,
            asset_code = 'JUAN-LOCAL-TEST',
            placeholder = False,
            asset_serial_number = 100200300,
            equipment_type = self.equipment
        )
        self.hardware_bundle = HardwareBundle.objects.create(
            location = self.laundry_room,
            slot = self.slot,
            machine = self.machine
        )
        MachineSlotMap.objects.create(machine=self.machine, slot=self.slot, start_time=datetime.now())
        self.api = UpkeepAPI()
        self.existing_machine = Machine.objects.create(
            machine_type = 0,
            asset_code = 'JUAN-LOCAL-TEST2',
            placeholder = False,
            asset_serial_number = 100200300,
            equipment_type = self.equipment,
            upkeep_id = '00fRPjt2iP',
        )
        self.hardware_bundle = HardwareBundle.objects.create(
            location = self.laundry_room,
            slot = self.slot,
            machine = self.existing_machine
        )
        MachineSlotMap.objects.create(machine=self.existing_machine, slot=self.slot, start_time=datetime.now())
        

    def test_creation(self):
        manager = UpkeepAssetManager()
        manager.create_or_update(self.machine)
        self.machine.refresh_from_db()
        self.assertIsNot(self.machine.upkeep_id, None)
        upkeep_custom_fields = self.api.get_asset(self.machine.upkeep_id).get('customFieldsAsset')
        print (upkeep_custom_fields)
        self.assertIsNot(upkeep_custom_fields, None)

    def test_update(self):
        manager = UpkeepAssetManager()
        manager.create_or_update(self.machine)
        initial_value = self.machine.asset_serial_number
        self.machine.asset_serial_number = 999999999
        self.machine.save()
        self.machine.refresh_from_db()
        manager.create_or_update(self.machine)
        self.machine.refresh_from_db()
        upkeep_custom_fields = self.api.get_asset(self.machine.upkeep_id).get('customFieldsAsset')
        for field in upkeep_custom_fields:
            if field.get('name') == 'asset_make_serial':
                self.assertEqual(field.get('value'), '999999999')
                self.assertNotEqual(field.get('value'), initial_value)
        return True

    def test_add_new_fields(self):
        manager = TestUpkeepManager()
        manager.create_or_update(self.existing_machine)
        self.machine.refresh_from_db()
        upkeep_custom_fields = self.api.get_asset(self.existing_machine.upkeep_id).get('customFieldsAsset')
        field_names = [f.get('name') for f in upkeep_custom_fields]
        self.assertTrue('asset_make_serial' in field_names)
        self.assertTrue('test' in field_names)

