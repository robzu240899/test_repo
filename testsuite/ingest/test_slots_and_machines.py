'''
Created on Apr 29, 2018

@author: tpk6
'''

from django.test import TestCase

from testhelpers.factories import LaundryGroupFactory, LaundryRoomFactory, SlotFactory, MachineFactory, MachineSlotMap as MachineSlotMapFactory, EquipmentTypeFactory

from roommanager.slot_finder import ConfigurationRecorder
from roommanager.models import MachineSlotMap, Slot, EquipmentType

class TestConfigurationIntialEquipmentRun(TestCase):
    '''
        Tests to ensure the initial run of the Configuration finder that is used to attach the new notion of equipment type to machines works
        Setup requirements:  Mimic a slot that is in production
        Run:     The initial equipment attachment procedure and the equipment type ingtest
        Test:     1) Machine has the appropriate equipment attached to it
                  2) The machine slot map has stayed the same
                  3) No new machine slot map has been created for either the machine or the slot
                  4) Never before seen slots get the correct machine
    '''

    @classmethod
    def setUpClass(cls):
        cls.laundry_group = LaundryGroupFactory(id=1)  #using id=1 ensures that we pull the correct credentials
        cls.laundry_room = LaundryRoomFactory(laundry_group = cls.laundry_group, fascard_code = 21) #1 Arden Street
        cls.slot_1 = SlotFactory(laundry_room = cls.laundry_room, slot_fascard_id = 546, web_display_name = 1, clean_web_display_name = 1)
        cls.machine_1 = MachineFactory(equipment_type = None)
        cls.map_1_1 = MachineSlotMapFactory(slot = cls.slot_1, machine = cls.machine_1)
        ConfigurationRecorder.record_equipment(cls.laundry_room.id)
        ConfigurationRecorder.record_slot_configuration(cls.laundry_room.id, force_equipment_override=True)
        return super(TestConfigurationIntialEquipmentRun, cls).setUpClass()

    @classmethod
    def tearDownClass(cls):
        super(TestConfigurationIntialEquipmentRun, cls).tearDownClass()
        cls.slot_1.delete()
        cls.machine_1.delete()
        cls.map_1_1.delete()
        cls.laundry_room.delete()
        cls.laundry_group.delete()

    def test_attach_equipment(self):
        '''Validate 1) Machine has the appropriate equipment attached to it'''
        expected_fascard_equipment_id = 167
        self.machine_1.refresh_from_db()
        self.assertEqual(self.machine_1.equipment_type.fascard_id, expected_fascard_equipment_id,
                         "Wrong equipment type attached.  Expected facard %s by got %s" % (expected_fascard_equipment_id, self.machine_1.equipment_type.fascard_id))

    def test_original_maping_stays_the_same(self):
        '''The machine slot map has stayed the same'''
        self.map_1_1.refresh_from_db()
        self.assertEqual(self.map_1_1.slot, self.slot_1, "The original mappings slot has changed")
        self.assertEqual(self.map_1_1.machine, self.machine_1, "The original mappings machine has changed")
        self.assertTrue(self.map_1_1.is_active, "The original mapping is no longer active")

    def test_no_new_maps(self):
        ''' Validate '3) No new machine slot map has been created for either the machine or the slot'''
        self.assertEqual(MachineSlotMap.objects.filter(slot = self.slot_1).count(), 1, "There should be no new/deleted maps with slot_1")
        self.assertEqual(MachineSlotMap.objects.filter(machine = self.machine_1).count(), 1, "There should be no new/deleted maps with machine_1")

    def test_previously_unseen_slot(self):
        '''Validate 4) Never before seen slots get the correct machine'''
        slot = Slot.objects.get(slot_fascard_id = 556)
        expected_fascard_equipment_id = 165
        mp = MachineSlotMap.objects.get(slot = slot, is_active = True)
        self.assertEqual(mp.machine.equipment_type.fascard_id, expected_fascard_equipment_id,
                         "Wrong equipment type attached.  Expected facard %s by got %s" % (expected_fascard_equipment_id, mp.machine.equipment_type.fascard_id))


class TestConfigurationRecorderNewSlots(TestCase):
    ''' Validate that slots and machines are recorded correctly for a a new room
        Setup:  Create a new room that mimics Arden Street.  No not attach any slots
        Run:  Equipment configuration recorder, and then slot configuration recorder for the laundry room
        Test:  1) at least two slots, each with a machine and active slot state map
               2) each machine has equipment attached
               3) all of the data for a specific slot
    '''

    @classmethod
    def setUpClass(cls):
        cls.laundry_group = LaundryGroupFactory(id=1)  #using id=1 ensures that we pull the correct credentials
        cls.laundry_room = LaundryRoomFactory(laundry_group = cls.laundry_group, fascard_code = 21) #1 Arden Street
        ConfigurationRecorder.record_equipment(cls.laundry_room.id)
        ConfigurationRecorder.record_slot_configuration(cls.laundry_room.id, force_equipment_override=False)
        return super(TestConfigurationRecorderNewSlots, cls).setUpClass()

    @classmethod
    def tearDownClass(cls):
        super(TestConfigurationRecorderNewSlots, cls).tearDownClass()
        cls.laundry_room.delete()
        cls.laundry_group.delete()

    def test_number_slots(self):
        ''' Validate 1) at least two slots, each with a machine and active slot state map'''
        self.assertGreater(MachineSlotMap.objects.filter(is_active = True, slot__laundry_room = self.laundry_room), 1)

    def test_equipmenet_attached(self):
        ''' Validate 2) each machine has equipment attached'''
        for msmap in MachineSlotMap.objects.filter(slot__laundry_room = self.laundry_room):
            self.assertIsNotNone(msmap.machine.equipment_type)

    def test_specific_slot(self):
        ''' Validate 3) all of the data for a specific slot'''
        slot = Slot.objects.get(slot_fascard_id = 554)
        machine = MachineSlotMap.objects.get(slot = slot).machine
        self.assertEqual(slot.laundry_room, self.laundry_room)
        self.assertEqual(slot.web_display_name, '103')
        self.assertEqual(slot.clean_web_display_name, '103')
        self.assertEqual(machine.equipment_type.fascard_id, 165)

class TestConfigurationRecorderExistingSlots(TestCase):
    '''Validate the machines and slots get ingested correctly for an existing room
       Setup: Create a laundry room to mimic 1 Arden Street.  Mimic a slot/machine that is there.  Mimic a slot/machine that is there but has the wrong equipment attached
       Run: Run Equipment configuration recorder, and then slot configuration recorder for the laundry room
       Validate: 1) First machine/slot remains unchanged
                 2) Second machine/slot gets the correct equipment attached
    '''



    @classmethod
    def setUpClass(cls):
        cls.laundry_group = LaundryGroupFactory(id=1)  #using id=1 ensures that we pull the correct credentials
        cls.laundry_room = LaundryRoomFactory(laundry_group = cls.laundry_group, fascard_code = 21) #1 Arden Street
        #setup equipment types
        ConfigurationRecorder.record_equipment(cls.laundry_room.id)
        #setup slot 1 to match Fascard
        cls.slot_1 = SlotFactory(laundry_room = cls.laundry_room, slot_fascard_id = 554)
        cls.machine_1 = MachineFactory(equipment_type = EquipmentType.objects.get(fascard_id =165))
        cls.map_1_1 = MachineSlotMapFactory(slot = cls.slot_1, machine = cls.machine_1)
        #setup slot 2 to match Fascard but the associated equipment type is outdated
        cls.old_equipment_type = EquipmentTypeFactory(fascard_id=100000)
        cls.slot_2 = SlotFactory(laundry_room = cls.laundry_room, slot_fascard_id = 555)
        cls.machine_2 = MachineFactory(equipment_type = cls.old_equipment_type)
        cls.map_2_2 = MachineSlotMapFactory(slot = cls.slot_2, machine = cls.machine_2)
        #Run
        ConfigurationRecorder.record_slot_configuration(cls.laundry_room.id, force_equipment_override=False)
        return super(TestConfigurationRecorderExistingSlots, cls).setUpClass()

    def test_unchanged(self):
        ''' Validates: 1) First machine/slot remains unchanged'''
        self.map_1_1.refresh_from_db()
        self.assertTrue(self.map_1_1.is_active)
        self.assertEqual(self.map_1_1.machine.equipment_type.fascard_id, 165)

    def test_outdate(self):
        '''2) Second machine/slot gets the correct equipment attached'''
        msmap = MachineSlotMap.objects.get(slot = self.slot_2, is_active = True)
        self.assertNotEqual(msmap, self.map_1_1) #A new map should be created
        self.assertNotEqual(msmap, self.map_2_2) #A new map should be created
        self.assertNotEqual(msmap.machine, self.machine_2)  #The new map should have a new machine
        self.assertNotEqual(msmap.machine, self.machine_1)  #The new map should have a new machine
        self.assertEqual(msmap.machine.equipment_type.fascard_id, 165) #The new machine's equipment type should match Fascard


        #check that the old map is retired correctly
        self.map_2_2.refresh_from_db()
        self.assertFalse(self.map_2_2.is_active)
        self.assertEqual(self.map_2_2.machine, self.machine_2)


    @classmethod
    def tearDownClass(cls):
        super(TestConfigurationRecorderExistingSlots, cls).tearDownClass()
        cls.laundry_group.delete()
        cls.laundry_room.delete()
        cls.slot_1.delete()
        cls.machine_1.delete()
        cls.map_1_1.delete()
        cls.old_equipment_type.delete()
        cls.slot_2.delete()
        cls.machine_2.delete()
        cls.map_2_2.delete()
