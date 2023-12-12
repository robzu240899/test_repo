'''
Created on Apr 6, 2017

@author: Thomas
'''


class OutOfOrderConfig(): 
    RUNNING_STATE_MIN = 30 #NB: Used for finding missed endtimes
    
class ErrorMarkerConfig():
    LONG_RUNNING_HOURS = 10
    SHORT_RUNNING_MAX_SEC = 10*60
    
    IDLE_DEFAULT_SECONDS = 8*86400 
    IDLE_MAX_SECONDS = 15*86400
    IDLE_MIN_SECONDS = 8*86400
    
    FLICKER_DEF  = 30  #seconds