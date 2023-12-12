'''
Created on May 20, 2017

@author: Thomas
'''

import csv
import unidecode 
from datetime import datetime 

from django.db import transaction
from django.db.models.fields import DateField,DateTimeField, BooleanField,\
    NullBooleanField



class CSVTrasnformer():
    
    def __init__(self,OrmClass,file_name,headers_map=None,constants=None):
        self.OrmClass = OrmClass
        self.file_name = file_name 
        self.headers_map = headers_map
        self.constants = constants
    
    def unsaved_orm_objects(self,date_format,datetime_format):
        field_names = get_field_names(self.OrmClass)
        with open(self.file_name) as f:
            rows = csv.reader(f)
            headers = next(rows)
            for row in rows:
                kwargs = {}
                for field_position,header in enumerate(headers):
                    #get raw value
                    if self.headers_map and header in self.headers_map and self.headers_map[header] is not None:
                        field_name = self.headers_map[header]
                        val = null_if_blank(row[field_position])
                    elif header in field_names: 
                        val = null_if_blank(row[field_position])     
                        field_name = header
                    field = list(filter(lambda f: f.column==field_name, self.OrmClass._meta.fields))[0]
                    #massage value
                    if date_format and val and isinstance(field, DateField):
                        val = datetime.strptime(val,date_format).date()
                    elif datetime_format and val and isinstance(field, DateTimeField):
                        val = datetime.strptime(val,datetime_format)
                    elif isinstance(field, BooleanField) or isinstance(field, NullBooleanField):
                        val = convert_to_bool(val) 
                    #place value in dict
                    kwargs[field_name] = val
                
                if self.constants:
                    kwargs.update(self.constants)
                yield kwargs
                
def get_field_names(OrmClass):
        field_names = []
        for field in OrmClass._meta.fields:
            field_names.append(field.attname)
        return field_names 

def convert_to_bool(value):
    if value is None:
        return None 
    elif value == "TRUE" or value == "True" or value == "1" or value == 1:
        return True
    elif value == "FALSE" or value == "False" or value == "0" or value == 0:
        return False 
    else:
        return None 

def null_if_blank(value):
    if value == '' or value == 'NULL':
        return None 
    else:
        return value