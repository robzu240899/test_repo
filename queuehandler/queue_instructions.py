'''
Created on Mar 22, 2017

@author: Thomas
'''
import logging
import re 

from .enums import ParameterType

logger = logging.getLogger(__name__)

class QueueParameterInstruction(object):
    
    def __init__(self,parameter_name,parameter_type,argument_name):        
        ''' 
        @job_name string- must be all lower case letters
        @parameter_type ParameterType enum
        @argument_name string- name of the corresponding argument of the processing function.
        @returns none.
        @description Specifies instructions on serializing and deserializing parameters for SQS messages
        '''
        self.parameter_name = parameter_name
        self.parameter_type = parameter_type
        self.argument_name = argument_name
        if not re.match('[a-z]+',self.parameter_name):
            exception_str = "Parameter name must be all lower case and letters only. got %s"
            raise Exception(exception_str)
        if not parameter_type in [x[0] for x in ParameterType.CHOICES]:
            raise Exception("parameter_type is invalid: got %s" % parameter_type)

class QueueJobInstruction(object):
    
    def __init__(self,job_name,processing_function):
        ''' 
        @job_name string- must be all lower case letters
        @returns none.
        @description  Specifies instructions on creating and processing SQS messages 
        '''
        self.job_name = job_name 
        self.processing_function = processing_function
        self.parameter_instructions = {}
        self.__argument_names = []
        
    def add_parameter_instruction(self,parameter_name,parameter_type,argument_name):
        '''
        @job_name string- must be all lower case letters
        @parameter_type ParameterType enum
        @argument_name string- name of the corresponding argument of the processing function.
        '''
        parameter_instructions_keys = list(self.parameter_instructions.keys())
        if parameter_name == 'jobtype':
            raise Exception('jobtype is an invalid name for a parameter instruction.  it is specified via the QueueJobInstruction constructor')
        if parameter_name not in parameter_instructions_keys and argument_name not in self.__argument_names:
            self.parameter_instructions[parameter_name] = QueueParameterInstruction(parameter_name,parameter_type,argument_name)
            self.__argument_names.append(argument_name)
        else:
            raise Exception("parameter_name and argument_name must be unique")        


#TODO: Looks like unused code.  Investigate.
# class QueueManager():
# 
#     @classmethod
#     def enqueue(cls,job_type,parameters):
#         sqs = boto3.resource('sqs')
#         queue = sqs.get_queue_by_name(QueueName=cls.QUEUE_NAME) #TODO: change 
#         msg_attrs = {'jobtype':{'StringValue': str(job_type),'DataType': 'String'}} #TODO: deal with multiple data types
#         for k,v in parameters.items():
#             msg_attrs[k] = {'DataType':'String','StringValue':str(v)}   
#         queue.send_message(MessageBody='boto3', MessageAttributes=msg_attrs)
        
        
        
        
        