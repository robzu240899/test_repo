'''
Created on Mar 22, 2017
 
@author: Thomas
'''
 
from django import test
from .enums import ParameterType
from .queue_instructions import QueueParameterInstruction, QueueJobInstruction
 
class TestQueueParameterInstruction(test.TestCase): 
     
    def test_string(self):
        #Make sure we create the correct parameter
        parameter_name = 'testparameter'
        parameter_type = ParameterType.STRING
        argument_name = 'test_argument'
        instruction = QueueParameterInstruction(parameter_name,parameter_type,argument_name)
        self.assertEqual(instruction.parameter_name, parameter_name)
        self.assertEqual(instruction.parameter_type,parameter_type)
      
    def test_integer(self):
        parameter_name = 'testparameter'
        parameter_type = ParameterType.INTEGER
        argument_name = 'test_argument'
        instruction = QueueParameterInstruction(parameter_name,parameter_type,argument_name)
        self.assertEqual(instruction.parameter_name, parameter_name)
        self.assertEqual(instruction.parameter_type,parameter_type)
      
    def test_invalid_name_underscore(self):
        parameter_name = 'test_parameter'
        parameter_type = ParameterType.INTEGER
        argument_name = 'test_argument'
        self.assertRaises(Exception, QueueParameterInstruction,(parameter_name,parameter_type,argument_name))
         
    def test_invalid_name_uppercase(self):
        parameter_name = 'TestParameter'
        parameter_type = ParameterType.INTEGER
        argument_name = 'test_argument'
        self.assertRaises(Exception, QueueParameterInstruction,(parameter_name,parameter_type,argument_name))
 
    def test_invalid_name_number(self):
        parameter_name = 'testparameter1'
        parameter_type = ParameterType.INTEGER
        argument_name = 'test_argument'
        self.assertRaises(Exception, QueueParameterInstruction,(parameter_name,parameter_type,argument_name))
     
    def test_invalid_parameter_type(self):
        parameter_name = 'TestParameter'
        parameter_type = 'INVALID PARAMETER'
        argument_name = 'test_argument'
        self.assertRaises(Exception, QueueParameterInstruction,(parameter_name,parameter_type,argument_name))
     
class TestQueueJobInstruction(test.TestCase):
     
    def test_creation(self):
        job_name  = 'testjob'
        processing_function = None 
        instruction = QueueJobInstruction(job_name,processing_function)
        self.assertEqual(instruction.job_name, job_name)
        self.assertEqual(instruction.processing_function,processing_function)
         
    def test_creation_invalid_name(self):
        job_name  = 'test_job'
        processing_function = None 
        self.assertRaises(Exception,QueueJobInstruction,(job_name,processing_function))
 
    def test_add_parameter(self):
        job_name  = 'testjob'
        processing_function = None 
        instruction = QueueJobInstruction(job_name,processing_function)        
        instruction.add_parameter_instruction('testparameter', ParameterType.STRING,'test_argument')
     
    def test_add_duplicate_parameter(self):
        job_name  = 'testjob'
        processing_function = None 
        instruction = QueueJobInstruction(job_name,processing_function)        
        instruction.add_parameter_instruction('testparameter', ParameterType.STRING,'test_argument')  
        self.assertRaises(Exception,instruction.add_parameter_instruction,('testparameter', ParameterType.STRING,'test_argument_two'))  
    
    def test_add_duplicate_argument(self):
        job_name  = 'testjob'
        processing_function = None 
        instruction = QueueJobInstruction(job_name,processing_function)        
        instruction.add_parameter_instruction('testparameter', ParameterType.STRING,'test_argument')  
        self.assertRaises(Exception,instruction.add_parameter_instruction,('testparametertwo', ParameterType.STRING,'test_argument'))  
        
     
     
     
     
     
            