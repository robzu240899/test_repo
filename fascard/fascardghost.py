'''
Created on Dec 19, 2017

@author: tpk6
'''
import logging
from selenium import webdriver
from main import settings 
from .config import FascardSeleniumLoginConfig

logger = logging.getLogger(__name__)

class FascardGhostBrowser(object):
    
    def __init__(self, building_group_id):
        self.building_group_id = building_group_id

        #setup credentails 
        credentials = settings.FASCARD_CREDENTIALS[str(building_group_id).lower().strip()]
        self.username = credentials[0]
        self.password = credentials[1]
        self.url_number = credentials[2]
        
        #Setup Selenium Browser
        se_kwargs = {}
        if settings.PHANTOM_JS_LOG_PATH:
            se_kwargs['service_log_path'] = settings.PHANTOM_JS_LOG_PATH
        if settings.PHANTOM_JS_PATH:
            se_kwargs['executable_path'] = settings.PHANTOM_JS_PATH
        self.driver = webdriver.PhantomJS(**se_kwargs)


    def login(self):
        login_url = FascardSeleniumLoginConfig.LOGIN_URL 
        self.open(login_url, expected_url = login_url,  must_match = True, try_login_on_failture = False)
        username = self.driver.find_element_by_id(FascardSeleniumLoginConfig.USERNAME_ID)
        password = self.driver.find_element_by_id(FascardSeleniumLoginConfig.PASSWORD_ID)
        username.send_keys(self.username)
        password.send_keys(self.password)
        submit = self.driver.find_element_by_xpath(FascardSeleniumLoginConfig.SUBMIT_XPATH)
        submit.click()
        expected_post_click_url = FascardSeleniumLoginConfig.EXPECTED_POSTLOGIN_URL % self.url_number
        if expected_post_click_url != self.driver.current_url:
            exception_string = "Url mimatch. Expected %s but got %s" % (expected_post_click_url, expected_post_click_url)
            logger.error(exception_string)
            raise Exception (exception_string)

        
    def open(self, url, expected_url = None, must_match = True, try_login_on_failture = True):
        if not expected_url:
            expected_url = url 
        self.driver.get(url)
        if must_match and self.driver.current_url != expected_url:
            if try_login_on_failture == True:
                self.login()
                self.open(url, expected_url, True, False)
            else:
                exception_string = "Url mimatch. Expected %s but got %s" % (url, expected_url) 
                logger.error(exception_string)
                raise Exception (exception_string)
            
    def quit(self):
        try:
            self.driver
        except NameError:
            return 
        self.driver.quit()
         
    

            