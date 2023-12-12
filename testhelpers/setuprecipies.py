'''
Created on Dec 21, 2017

@author: tpk6
'''
from factories import *

class BasicTestSetupRecipie():
    
    @classmethod 
    def setup_basic_class(cls):
        ''' Creates 2 Laundry Groups and 10 Laundry Rooms'''
        for n in range(1, 3):
            setattr(cls, 'laundry_group_%s' % n, LaundryGroupFactory())
        
        for n in range(1, 11):
            setattr(cls, 'laundry_room_%s' % n, LaundryRoomFactory())

    def setup_basic_individual(self):
        ''' Creates 2 Laundry Groups and 10 Laundry Rooms'''
        for n in range(1, 3):
            setattr(self, 'laundry_group_%s' % n, LaundryGroupFactory())
        
        for n in range(1, 11):
            setattr(self, 'laundry_room_%s' % n, LaundryRoomFactory())