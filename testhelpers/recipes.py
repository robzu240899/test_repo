'''
Created on Jan 19, 2018

@author: tpk6
'''

import factories 

from revenue.enums import TransactionType

from random import uniform
from testhelpers.factories import BillingGroupFactory,\
    LaundryRoomExtensionFactory

class BasicRecipeMixin():

    @classmethod 
    def _create_data(cls,assing_to):
        for i in range(2):
            laundry_group = factories.LaundryGroupFactory()
            setattr(assing_to, 'laundry_group_%s' %i, laundry_group)
            for j in range(10):
                laundry_room = factories.LaundryRoomFactory(laundry_group = laundry_group)
                setattr(assing_to, 'laundry_room_%s_%s' % (i, j), laundry_room)
                for k in range(10):
                    machine = factories.MachineFactory()
                    setattr(assing_to, 'machine_%s_%s_%s' % (i, j, k), machine)
                    slot = factories.SlotFactory(laundry_room = laundry_room)
                    setattr(assing_to, "slot_%s_%s_%s" %(i, j, k), slot)
                    machine_slot_map = factories.MachineSlotMap(machine = machine, slot = slot)
                    setattr(assing_to, "map_%s_%s" %(machine.id, slot.id), machine_slot_map)
                billing_group = BillingGroupFactory()
                setattr(assing_to, 'billing_group_%s_%s' % (i, j), billing_group)
                laundry_room_extension = LaundryRoomExtensionFactory(laundry_room = laundry_room, billing_group = billing_group)
                setattr(assing_to, 'laundry_room_extension_%s_%s' % (i, j), laundry_room_extension)
                    
            for k in range(2):
                user = factories.FascardUserFactory(laundry_group = laundry_group)
                setattr(assing_to,'fascard_user_%s_%s' % (i, k), user)
    
    
    @classmethod 
    def create_class_data(cls):
        cls._create_data(cls)
    
    def create_data(self):
        BasicRecipeMixin._create_data(self)

    
    def create_filler_transactions(self, laundry_room):
        for slot in laundry_room.slot_set.all():
            for _ in range(2):
                #Add cash to card
                factories.LaundryTransactionFactory(transaction_type = TransactionType.ADD_VALUE,
                                cash_amount = self._generate_random_amount(), credit_amount = 0, balance_amount = 0,
                                laundry_room = laundry_room, slot = slot)
                #Add credit to card 
                factories.LaundryTransactionFactory(transaction_type = TransactionType.ADD_VALUE,
                                cash_amount = 0, credit_amount = self._generate_random_amount(), balance_amount = 0,
                                laundry_room = laundry_room, slot = slot)
                #Use credit card at machine 
                factories.LaundryTransactionFactory(transaction_type = TransactionType.VEND,
                                cash_amount = 0, credit_amount = self._generate_random_amount(), balance_amount = 0,
                                laundry_room = laundry_room, slot = slot)
                #Use loyalty card at machine 
                factories.LaundryTransactionFactory(transaction_type = TransactionType.VEND,
                                cash_amount = 0, credit_amount = 0, balance_amount = self._generate_random_amount(),
                                laundry_room = laundry_room, slot = slot)
                
    def _generte_random_amount(self,lower = 1, upper = 10):
        return round(uniform(upper,lower),2)
        