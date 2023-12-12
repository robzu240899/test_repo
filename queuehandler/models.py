'''
Created on Apr 26, 2017

@author: Thomas
'''

from django.db import models 


class NightlyRunTracker(models.Model):
    id = models.AutoField(primary_key=True)
    start_time = models.DateTimeField(auto_now=True)
    
    class Meta:
        managed=True
        db_table = "nightly_run_tracker"