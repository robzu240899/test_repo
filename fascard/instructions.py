'''
Created on Apr 13, 2014

@author: Tom
'''


class FormInstruction():
    
    def __init__(self,formFind,fields,vals,expected_url):
        self.FormFind = formFind
        self.Fields = fields 
        self.Vals = vals
        self.Expected = expected_url