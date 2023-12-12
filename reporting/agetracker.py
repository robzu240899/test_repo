'''
Created on Apr 17, 2017

@author: Thomas
'''

class AgeTracker(object):
    
    def __init__(self):
        self.metrics_ages = {}
        self.__worst = None 
        self.__worst_time = None 
        
    def add(self,metric):
        self.metrics_ages[metric.id] = metric.calcuation_time
        if self.__worst_time is None or metric.calcuation_time < self.__worst_time:
            self.__worst_time = metric.calcuation_time
            self.__worst = metric.id 
        
    def get_worst(self,metric):
        return self.__worst_time, self.__worst