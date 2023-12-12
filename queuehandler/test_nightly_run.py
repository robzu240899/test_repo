'''
Created on May 25, 2017

@author: Thomas
'''
import mock
from django.test import TestCase
from datetime import timedelta, datetime
from .nightly_run import StepManager
from .models import NightlyRunTracker

class TestCreateNightlyRun(TestCase):
    
    def test_first_setup(self):
        nrt = StepManager.create_nightly_run_model()
        self.assertIsNotNone(nrt)
        
    def test_standard_case(self):
        '''Last run > 5 min ago'''
        testtime = datetime.now() - timedelta(days=60)
    
        with mock.patch('django.utils.timezone.now') as mock_now:
            mock_now.return_value = testtime
            nrt = NightlyRunTracker.objects.create()
    
        nrt2 = StepManager.create_nightly_run_model()
        self.assertIsNotNone(nrt2)
        
    def test_too_soon(self):
        '''Last Run < 5 min ago'''
        nrt = StepManager.create_nightly_run_model()
        nrt.save()
        
        nrt2 = StepManager.create_nightly_run_model()
        self.assertIsNone(nrt2)   