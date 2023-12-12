'''
Created on Mar 9, 2015

@author: Tom
'''
import logging
import csv
import unidecode 
from datetime import datetime 

from django.db import transaction
from django.db.models.fields import DateField,DateTimeField, BooleanField,\
    NullBooleanField

logger = logging.getLogger(__name__)

class CSVIngestor():
    
    def __init__(self,OrmClass,file_name,headers_map=None,constants=None):
        self.OrmClass = OrmClass
        self.file_name = file_name 
        self.headers_map = headers_map
        self.constants = constants
    
    def ingest(self,date_format,datetime_format,precheck_function=None,post_processing_functions=[]):
        try:
            self._ingest(date_format, datetime_format,precheck_function,post_processing_functions)
        except Exception as e:
            err_str = 'Failed to execute _ingest function in CSV Ingestor: {}'.format(e)
            logger.info(err_str)
            raise Exception(e)
    
    #@transaction.atomic()
    def _ingest(self,date_format,datetime_format,precheck_function,post_processing_functions):
        field_names = get_field_names(self.OrmClass)
        with open(self.file_name, encoding='utf-8') as f:
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
                new_orm_obj = self.OrmClass(**kwargs)

                if precheck_function is not None:
                    if precheck_function(new_orm_obj) == False:
                        continue
                
                for fx in post_processing_functions:
                    fx[0](new_orm_obj,**fx[1])
                
                new_orm_obj.save()
        logger.info("Finished ingesting CSV file")
                

class CSVDumper():
    
    def __init__(self,OrmClass,file_name,delimiter=',',quotechar='"'):
        self.OrmClass = OrmClass
        self.file_name = file_name 
        self.delimiter = delimiter
        self.quotechar=quotechar 
        
    def dump(self):
        field_names = get_field_names(self.OrmClass)
        with open(self.file_name, 'wb') as f:
            output_writer = csv.writer(f, delimiter=self.delimiter, quotechar=self.quotechar)

            # Write header row
            row = []
            for field_name in field_names:
                row.append(field_name)
            output_writer.writerow(row)

            # Write data rows
            for obj in self.OrmClass.objects.all():
                row = []
                for field_name in field_names:
                    value = (obj.__dict__[field_name])
                    if type(value) == unicode:
                        row.append(unidecode.unidecode(value))
                    else:
                        row.append(value)
                output_writer.writerow(row)
                
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