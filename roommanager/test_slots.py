'''
Created on Mar 5, 2017
  
@author: Thomas
'''
import os 
  
from django.test import TestCase
  
from main import settings
from Utils.CSVIngest.ingest import CSVIngestor
from fascard.config import FascardScrapeConfig
  
import models
from slot_finder import ConfigurationRecorder
from datetime import datetime
from roommanager.models import LaundryRoom, Slot, MachineSlotMap
from roommanager.enums import MachineType
  
class TestSlotFinder(TestCase):
      
    def setUp(self):
        CSVIngestor(models.LaundryGroup,file_name = os.path.join(settings.TEST_FILE_FOLDER,'test_slots','laundry_group.csv')).ingest(date_format=None,datetime_format=FascardScrapeConfig.TIME_INPUT_FORMAT)
        CSVIngestor(models.LaundryRoom,file_name = os.path.join(settings.TEST_FILE_FOLDER,'test_slots','laundry_room.csv')).ingest(date_format=None,datetime_format=FascardScrapeConfig.TIME_INPUT_FORMAT)
        self.arden = LaundryRoom.objects.get(display_name='1 Arden ST')
         
    def test_find_slots_with_no_previous_data(self):
        ConfigurationRecorder.record_slot_configuration(self.arden.id) 
  
        #TODO: change this out after we get a test room!
        slots = models.Slot.objects.all()
        num_slots = slots.count()
        self.assertGreater(num_slots,5)
        self.assertLess(num_slots,20)
        num_machines = models.Machine.objects.count()
        num_maps = models.MachineSlotMap.objects.count()
        self.assertEqual(num_slots,num_machines)
        self.assertEqual(num_slots,num_maps)
          
    def test_find_slots_with_previous_data(self):
        ConfigurationRecorder.record_slot_configuration(self.arden.id) 
        #TODO: change this out after we get a test room!
        num_slots_old = models.Slot.objects.count()
        num_machines_old = models.Machine.objects.count()
        num_maps_old = models.MachineSlotMap.objects.count()
          
        ConfigurationRecorder.record_slot_configuration(self.arden.id) 
        num_slots_new = models.Slot.objects.count()
        num_machines_new = models.Machine.objects.count()
        num_maps_new = models.MachineSlotMap.objects.count()
        self.assertEqual(num_slots_old,num_slots_new)
        self.assertEqual(num_machines_old,num_machines_new)
        self.assertEqual(num_maps_old,num_maps_new)
    
    def test_machine_type_detection(self):
        ConfigurationRecorder.record_slot_configuration(self.arden.id) 
        washer_slot=Slot.objects.get(laundry_room=self.arden,web_display_name='1')
        washer = MachineSlotMap.objects.get(slot=washer_slot).machine 
        self.assertEqual(washer.machine_type,MachineType.WASHER)
        
        dryer_slot =Slot.objects.get(laundry_room=self.arden,web_display_name='101')
        dryer = MachineSlotMap.objects.get(slot=dryer_slot).machine 
        self.assertEqual(dryer.machine_type,MachineType.DRYER)     
 
     
     
          
     
     
     