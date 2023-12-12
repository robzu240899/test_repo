'''
Created on Apr 5, 2017

@author: Thomas
'''

from os import times
from django.db import models

from roommanager.models import Slot 
from outoforder import enums


'''Represents the state a machine was/is in'''
class SlotState(models.Model):
    MLVMACHERROR_CHOICES = [
        (0, 'Machine OK'),
        (1, 'Unable to communicate with machine'),
        (2, 'Machine leaking water'),
        (3, 'Machine stuck in cycle'),
        (4, 'Machine not filling'),
        (5, 'Machine not draining'),
        (6, 'Machine not heating'),
        (7, 'Machine door problem'),
        (100, 'Part or all of config was rejected'),
        (101, 'One or more messages timed out or were rejected'),
        (999, 'Unknown machine problem'),
        (1000, 'Machine code indicates error')
    ]
    id = models.AutoField(primary_key=True)
    slot = models.ForeignKey(Slot, on_delete=models.CASCADE, related_name='slot_set')
    start_time = models.DateTimeField()
    end_time = models.DateTimeField(null=True)
    local_start_time = models.DateTimeField()
    local_end_time = models.DateTimeField(null=True)
    duration = models.BigIntegerField(null=True)
    slot_status = models.IntegerField(choices=enums.MachineStateType.CHOICES)
    slot_status_text = models.CharField(max_length=50, blank=True, null=True)
    recorded_time = models.DateTimeField()  
    local_recorded_time = models.DateTimeField()  
    error_checking_complete = models.BooleanField(default=False)
    certified_error_free = models.BooleanField(default=False) 
    has_endtime_guess = models.BooleanField(default=False)
    is_filler_state = models.BooleanField(default=False)
    is_guess_state = models.BooleanField(default=False)
    state_order = models.IntegerField(null=True,blank=True)
    mlvmacherror_description = models.IntegerField(choices=MLVMACHERROR_CHOICES, default=0, blank=True, null=True)
    
    class Meta:
        managed = True
        db_table = 'slot_state'
    
    @staticmethod
    def to_status_enum(txt):
        txt = txt.lower().strip()
        if txt.startswith('disabled'):
            return enums.MachineStateType.DISABLED
        elif txt.startswith('error'):
            return enums.MachineStateType.ERROR
        elif txt.startswith('offline'):
            return enums.MachineStateType.OFFLINE
        elif txt.startswith('idle'):
            return enums.MachineStateType.IDLE
        elif txt.startswith('running'):
            return enums.MachineStateType.RUNNING
        elif txt.startswith('diagnostic'):
            return enums.MachineStateType.DIAGNOSTIC
        elif txt.startswith('diag'):
            return enums.MachineStateType.DIAGNOSTIC
        else:
            return enums.MachineStateType.UNKNOWN
    
    @staticmethod
    def status_enum_to_txt(enum):
        if enum == -3:
            return "DISABLED"
        elif enum == -2:
            return 'ERROR'
        elif enum == -1:
            return 'OFFLINE'
        elif enum == 0:
            return 'IDLE'
        elif enum == 1:
            return "RUNNING"
        elif enum == -4:
            return 'DIAGNOSTIC'
        elif enum == -5:
            return 'UNKNOWN'
        elif enum == -11:
            return 'DUPLICATE'

    def __str__(self):
        return "{}: {}".format(self.slot, SlotState.status_enum_to_txt(self.slot_status))

    def get_readable_slot_status(self):
        return SlotState.status_enum_to_txt(self.slot_status)
        
class SlotStateError(models.Model):
    id = models.AutoField(primary_key=True)
    slot_state = models.ForeignKey(SlotState, on_delete=models.CASCADE)
    error_type = models.IntegerField(choices=enums.SlotErrorType.CHOICES)
    error_message = models.CharField(max_length=1000) 
    severity = models.IntegerField(null=True)
    is_reported = models.BooleanField(default=False)
    reported_time = models.DateTimeField(null=True,blank=True)
    
    class Meta:
        managed = True
        db_table = 'slot_state_error'
        unique_together = ['slot_state','error_type']

    def __str__(self):
        return '%s: %s' % (self.get_error_type_display(), self.id)

    def get_slot(self):
        return self.slot_state.slot

    def get_laundry_room(self):
        return self.slot_state.slot.laundry_room

    def get_local_slotstate_time(self):
        return self.slot_state.local_start_time

    def get_mlv_error(self):
        return self.slot_state.get_mlvmacherror_description_display()

    def get_status_text(self):
        string = self.slot_state.slot_status_text
        if string is None:
            string = ''
        return string


class CleanSlotStateTableLog(models.Model):
    start_date = models.DateTimeField()
    end_date = models.DateTimeField()
    success = models.BooleanField(default=False)
    timestamp = models.DateField(auto_now_add=True)

    def __str__(self) -> str:
        return f"Period: {self.start_date} - {self.end_date}. Successful: {self.success}"