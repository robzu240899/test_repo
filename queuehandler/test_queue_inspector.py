'''
Created on Apr 23, 2017

@author: Thomas
'''
import boto3 
from uuid import uuid1
from unittest import TestCase
from .queue import QueueInspector


class QueueInspectorTest(TestCase):
    
    def setUp(self):
        self.sqs_resource = boto3.resource('sqs')
        self.sqs_client = boto3.client('sqs')
        
        self.queue_name = str(uuid1()).replace("-","")   
        self.sqs_client.create_queue(QueueName=self.queue_name)
        self.queue_url = self.sqs_client.get_queue_url(QueueName=self.queue_name)['QueueUrl']
    
        self.dead_queue_name = str(uuid1()).replace("-","")   
        self.sqs_client.create_queue(QueueName=self.dead_queue_name)
        self.dead_queue_url = self.sqs_client.get_queue_url(QueueName=self.dead_queue_name)['QueueUrl']
           
        
        self.inspector = QueueInspector(queue_name=self.queue_name,dead_letter_queue_name=self.dead_queue_name)
             
    def test_is_finsiehd_with_zero_messages(self):
        is_finished = self.inspector.is_finished(initial_pause=0,number_retries=2,retry_pause=.001)
        self.assertTrue(is_finished)

    def test_has_errors_with_zero_mesasges_in_dead_letter_queue(self):
        has_errors = self.inspector.has_too_many_errors(0)
        self.assertFalse(has_errors)
        
    def test_is_finished_with_one_message(self):
        self.sqs_client.send_message(QueueUrl=self.queue_url,MessageBody='testmsg')        
        is_finished = self.inspector.is_finished(initial_pause=0,number_retries=2,retry_pause=.001)
        self.assertFalse(is_finished)
        
    def test_has_errors_with_one_mesasge_in_dead_letter_queue(self):
        self.sqs_client.send_message(QueueUrl=self.dead_queue_url,MessageBody='testmsg')        
        has_errors = self.inspector.is_finished(initial_pause=0,number_retries=2,retry_pause=.001)
        self.assertTrue(has_errors)        
        

    def tearDown(self):
        self.sqs_client.delete_queue(QueueUrl=self.queue_url)