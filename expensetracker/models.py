'''
Created on Mar 28, 2017

@author: Duong
'''
import decimal
from django.db import models
from django.core.exceptions import ValidationError

from expensetracker import enums

from roommanager.models import LaundryRoom, Machine


class Job(models.Model):
    id = models.AutoField(primary_key=True)
    laundry_room = models.ForeignKey(LaundryRoom, on_delete=models.SET_NULL, blank=True,null=True)
    machine = models.ForeignKey(Machine, on_delete=models.SET_NULL, blank=True,null=True)
    job_type = models.CharField(choices=enums.JobType.CHOICES,max_length=255)
    status = models.CharField(choices=enums.JobStatus.CHOICES,max_length=255)
    start_date = models.DateField()
    final_date = models.DateField(null=True)
    description = models.CharField(max_length=1000,null=True,blank=True)

    class Meta:
        managed = True
        db_table = 'job'

    def clean(self):
        if not self.laundry_room and not self.machine:
            raise ValidationError(("At least one machine or laundry room must be filled in."))

        if self.status == enums.JobStatus.CLOSED:
            if not self.final_date:
                raise ValidationError(("Final date must be filled in for status closed."))

    def save(self,*args,**kwargs):
        self.clean()
        super(Job,self).save(*args,**kwargs)


class Technician(models.Model):
    id = models.AutoField(primary_key=True)
    first_name = models.CharField(max_length=100,null=True,blank=True)
    last_name = models.CharField(max_length=100,null=True,blank=True)
    employment_type = models.CharField(choices=enums.EmploymentType.CHOICES,max_length=255)
    hourly_rate = models.DecimalField(max_digits=10,decimal_places=2,blank=True,null=True)

    class Meta:
        managed = True
        db_table = 'technician'

    def clean(self):
        if self.employment_type == enums.EmploymentType.EMPLOYEE:
            if not self.hourly_rate:
                raise ValidationError(("Employee requires hourly rate."))
        elif self.employment_type == enums.EmploymentType.CONTRACTOR:
            if self.hourly_rate is not None:
                raise ValidationError(("Contractor's hourly rate must be null."))

    def save(self,*args,**kwargs):
        self.clean()
        super(Technician,self).save(*args,**kwargs)


class LineItem(models.Model):
    id = models.AutoField(primary_key=True)
    job = models.ForeignKey(Job,on_delete=models.SET_NULL, null=True, related_name="line_items")
    technician = models.ForeignKey(Technician,on_delete=models.SET_NULL, blank=True,null=True)
    line_item_type = models.CharField(choices=enums.LineItemType.CHOICES,max_length=255)
    status = models.CharField(choices=enums.LineItemStatus.CHOICES,max_length=255)
    description = models.CharField(max_length=1000,null=True,blank=True)
    start_date = models.DateField(null=True)
    finish_date = models.DateField(null=True)
    time = models.IntegerField(null=True,blank=True)
    cost = models.DecimalField(max_digits=10,decimal_places=2,blank=True,null=True)

    class Meta:
        managed = True
        db_table = 'line_item'

    def clean(self):
        if self.line_item_type == enums.LineItemType.LABOR:
            if not self.technician:
                raise ValidationError(("Technician must be filled in for type labor."))
        elif self.line_item_type == enums.LineItemType.PART:
            if self.technician is not None:
                raise ValidationError(("Technician must be null for type part."))

        if self.status == enums.LineItemStatus.CLOSED:
            if not self.start_date:
                raise ValidationError(("Start date must be filled in."))
            if not self.finish_date:
                raise ValidationError(("Finish date must be filled in."))
        elif self.status == enums.LineItemStatus.IN_PROGRESS:
            if not self.start_date:
                raise ValidationError(("Start date must be filled in."))
        elif self.status == enums.LineItemStatus.CREATED:
            if self.start_date is not None:
                raise ValidationError(("Start date must be null."))

        if self.line_item_type == enums.LineItemType.LABOR:
            if self.technician:
                if self.technician.employment_type == enums.EmploymentType.EMPLOYEE:
                    if not self.time:
                        raise ValidationError(("Time must be filled in."))
                else:
                    if self.time:
                        raise ValidationError(("Time must be null."))
                    if not self.cost:
                        raise ValidationError(("Cost must be filled in."))
            else:
                if self.time:
                    raise ValidationError(("Time must be null."))
                if not self.cost:
                    raise ValidationError(("Cost must be filled in."))
        else:
            if self.time:
                raise ValidationError(("Time must be null."))
            if not self.cost:
                raise ValidationError(("Cost must be filled in."))

    def save(self,*args,**kwargs):
        self.clean()
        if self.line_item_type == enums.LineItemType.LABOR:
            if self.technician:
                if self.technician.employment_type == enums.EmploymentType.EMPLOYEE:
                    self.cost = (self.time / decimal.Decimal(60.0)) * self.technician.hourly_rate
        super(LineItem,self).save(*args,**kwargs)
