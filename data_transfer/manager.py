'''
Created on Apr 21, 2017

@author: Thomas
'''
from django.db import connection

from .metrics import SCRIPTS as metrics_scripts 
from roommanager import SCRIPTS as rooommanager_scripts 

class Manager(object):
    
    @classmethod 
    def run_all(cls):
        cls.run_scripts(rooommanager_scripts)
        cls.run_scripts(metrics_scripts)
        
    @classmethod 
    def run_scripts(cls,scripts):
        with connection.cursor() as c:
            for script in scripts:
                if script.endswith(';'):
                    script = script[:-1]
                print (script) 
                c.execute(script)
        
 
            
        