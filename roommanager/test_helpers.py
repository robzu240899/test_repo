'''
Created on Apr 5, 2017

@author: Thomas
'''

from django.test import TestCase

from roommanager.models import LaundryGroup, LaundryRoom, Slot
from roommanager.enums import TimeZoneType, SlotType

from helpers import Helpers

class TestGetActiveSlots(TestCase):

    def setUp(self):

        self.laundry_group_1 = LaundryGroup.objects.create(display_name='Laundry Group 1')


        self.room1_active = LaundryRoom.objects.create(laundry_group=self.laundry_group_1,
                                                       display_name='room 1 active',
                                                       time_zone=TimeZoneType.EASTERN,
                                                       fascard_code = 1)

        self.slot_room1_1_active = Slot.objects.create(laundry_room=self.room1_active,
                                                       slot_fascard_id = '1',
                                                       web_display_name = '100',
                                                       slot_type = SlotType.STANDARD,
                                                       is_active=True
                                                       )

        self.slot_room1_2_inactive = Slot.objects.create(laundry_room=self.room1_active,
                                                       slot_fascard_id = '2',
                                                       web_display_name = '101',
                                                       slot_type = SlotType.STANDARD,
                                                       is_active=False
                                                       )


        self.room2_inactive = LaundryRoom.objects.create(laundry_group=self.laundry_group_1,
                                                       display_name='room 2 inactive',
                                                       time_zone=TimeZoneType.EASTERN,
                                                       is_active=False,
                                                       fascard_code=2)
        self.slot_room2_1_active = Slot.objects.create(laundry_room=self.room2_inactive,
                                                       slot_fascard_id = '3',
                                                       web_display_name = '100',
                                                       slot_type = SlotType.STANDARD,
                                                       is_active=True
                                                       )
        self.slot_room2_2_inactive = Slot.objects.create(laundry_room=self.room2_inactive,
                                                       slot_fascard_id = '4',
                                                       web_display_name = '101',
                                                       slot_type = SlotType.STANDARD,
                                                       is_active=False
                                                       )

        self.laundry_group_2 = LaundryGroup.objects.create(display_name='Laundry Group 2')


        self.room3_active = LaundryRoom.objects.create(laundry_group=self.laundry_group_2,
                                                       display_name='room 3 active',
                                                       time_zone=TimeZoneType.EASTERN,
                                                       fascard_code = 1)

        self.slot_room3_1_active = Slot.objects.create(laundry_room=self.room3_active,
                                                       slot_fascard_id = '111',
                                                       web_display_name = '100',
                                                       slot_type = SlotType.STANDARD,
                                                       is_active=True
                                                       )

    def test_laundry_room_level(self):
        '''Tests active slot is returned and inactive slot is not returned'''
        '''Also tests to make sure other laundry rooms are excluded'''
        active_slots = Helpers.get_active_slots(self.room1_active.pk)
        self.assertEqual(active_slots.count(),1)
        self.assertEqual(active_slots.first(),self.slot_room1_1_active)

    def test_laundry_group_level(self):
        '''Tests active slot is returned and inactive slot is not returned
           Tests slots in inactive rooms are excluded
           Tests to make sure other laundry groups are excluded'''
        active_slots = Helpers.get_active_slots(self.laundry_group_1.pk,use_room=False)
        self.assertEqual(active_slots.count(),1)
        self.assertEqual(active_slots.first(),self.slot_room1_1_active)

        #just for good measure
        active_slots = Helpers.get_active_slots(self.laundry_group_2.pk,use_room=False)
        self.assertEqual(active_slots.count(),1)
        self.assertEqual(active_slots.first(),self.slot_room3_1_active)
