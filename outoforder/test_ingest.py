'''
Created on Apr 5, 2017
  
@author: Thomas
'''
import os 
  
from roommanager.models import LaundryGroup,LaundryRoom,Slot
from roommanager.slot_finder import ConfigurationRecorder
 
from django.test import TestCase
   
from main import settings
from Utils.CSVIngest.ingest import CSVIngestor
from fascard.config import FascardScrapeConfig
  
from .ingest import SlotStateIngestor, LastRunTimeIngestor
from .models import SlotState
import enums
  
   
class TestSlotStateIngest(TestCase):       
       

    def setUp(self):
        CSVIngestor(LaundryGroup,file_name = os.path.join(settings.TEST_FILE_FOLDER,'test_slot_state','laundry_group.csv')).ingest(date_format=None,datetime_format=FascardScrapeConfig.TIME_INPUT_FORMAT)
        CSVIngestor(LaundryRoom,file_name = os.path.join(settings.TEST_FILE_FOLDER,'test_slot_state','laundry_room.csv')).ingest(date_format=None,datetime_format=FascardScrapeConfig.TIME_INPUT_FORMAT)
        self.arden = LaundryRoom.objects.first()
        ConfigurationRecorder.record_slot_configuration(self.arden.id)
        
   
    def test_ingest(self):
        SlotStateIngestor.ingest(laundry_room_id=self.arden.pk)
        num_slot_states = SlotState.objects.all().count()
        self.assertGreater(num_slot_states,400)
        self.assertLess(num_slot_states,1000)
        self.assertEqual(SlotState.objects.exclude(slot__laundry_room=self.arden).count(),0)
           
    def test_ingest_updated_slot_state(self):
        '''makes sure previously found states get updated and that we aren't double loading previous states '''
        SlotStateIngestor.ingest(laundry_room_id=self.arden.pk)
        num_slot_states_old = SlotState.objects.all().count()
           
        test_slot_state = SlotState.objects.filter().first()
        test_slot_state.slot_status = enums.MachineStateType.TEST_STATE
        test_slot_state.end_time = None 
        test_slot_state.save()
        SlotStateIngestor.ingest(laundry_room_id=self.arden.pk)
        test_slot_state.refresh_from_db()
        self.assertNotEqual(test_slot_state.slot_status,enums.MachineStateType.TEST_STATE)
           
           
        #make sure we aren't double loading
        num_slot_states_new = SlotState.objects.all().count()
        self.assertLess(num_slot_states_new, num_slot_states_old+60)
  
class TestLastRuntime(TestCase):

     
    def setUp(self):
        CSVIngestor(LaundryGroup,file_name = os.path.join(settings.TEST_FILE_FOLDER,'test_slot_state','laundry_group.csv')).ingest(date_format=None,datetime_format=FascardScrapeConfig.TIME_INPUT_FORMAT)
        CSVIngestor(LaundryRoom,file_name = os.path.join(settings.TEST_FILE_FOLDER,'test_slot_state','laundry_room.csv')).ingest(date_format=None,datetime_format=FascardScrapeConfig.TIME_INPUT_FORMAT)
        self.arden = LaundryRoom.objects.first()
    
    def test_basic(self):
        ConfigurationRecorder.record_slot_configuration(self.arden.id)
        LastRunTimeIngestor.ingest(self.arden.id)
        with_last_runtime = Slot.objects.filter(laundry_room=self.arden).exclude(last_run_time=None)
        self.assertGreater(with_last_runtime.count(),10)
         
         
          