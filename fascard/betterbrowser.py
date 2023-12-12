'''
Created on Apr 13, 2014

@author: Tom
'''
import logging
from mechanize import Browser
from lxml import html

logger = logging.getLogger(__name__)

class WrongEndPointError(Exception):
    pass 

class BetterBrowser():
    
    def __init__(self,*args,**kwargs):
        self.Br = Browser()
        self.Br.set_handle_equiv(True)
        self.Br.set_handle_gzip(True)
        self.Br.set_handle_redirect(True)
        self.Br.set_handle_referer(True)
        self.Br.set_handle_robots(False)
        self.latest_response = None 
    
    #Open the page.  Optionally check if the response url matches / starts with the url we tried to open
    def open(self, url, must_match=True, expected_url = None):
        if not expected_url:
            expected_url = url
        self.latest_response = self.Br.open(url)
        if must_match and self.Br.geturl() != expected_url:
            self.login()
            self.latest_response = self.Br.open(url)
            if must_match and self.Br.geturl() != expected_url:
                exception_string = 'Wrong results page expected:%s  GOT:%s'% (url,self.Br.geturl())
                logger.error(exception_string)
                raise WrongEndPointError(exception_string)
        if self.latest_response.code != 200:
            exception_string = "The scrapper didn't get a 200 response"
            logger.error(exception_string)
            raise Exception(exception_string)
        
    #log into the system
    def login(self):
        self.open(self.login_url, must_match = True)
        self.process_form(self.login_ins, must_match = True)
        
    def process_form(self, ins, must_match = True):
        if type(ins.FormFind) is int:
            form = self.Br.form = list(self.Br.forms())[ins.FormFind] 
        else:
            form = self.Br.select_form(ins.FormFind)
        for field_lookup,browser_field_name in ins.Fields.items():
            field_value = ins.Vals[field_lookup]
            control = form.find_control(browser_field_name)   
            control.value = field_value
        self.latest_response = self.Br.submit()
        if must_match and self.Br.geturl() != ins.Expected:
            exception_string = 'Wrong results page expected:%s  GOT:%s' % (ins.Expected, self.Br.geturl())
            logger.error(exception_string)
            raise WrongEndPointError(exception_string)

    def get_tree(self):
        return html.document_fromstring(self.latest_response.read())

  

