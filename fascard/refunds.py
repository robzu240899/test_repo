'''
Created on Mar 6, 2018

@author: tpk6
'''
import time 

from .fascardghost import FascardGhostBrowser


class RefundBrowser(object):
    
    def __init__(self, fascard_user, amount):
        self.fascard_user = fascard_user 
        self.amount = amount 
        
    def __enter__(self):
        self.browser =  _RefundBrowser(self.fascard_user, self.amount)
        return self.browser
    
    def __exit__(self, exception_type, exception_value, traceback):
        self.browser.quit()

class _RefundBrowser(FascardGhostBrowser):
    
    BALLANCE_BOX_ID = "txtBonus"
    SUBMIT_XPATH = ".//button[@value='Adjust Credit']"
    
    def __init__(self,fascard_user, amount):
        self.fascard_user = fascard_user 
        self.refund_amount = amount 
        super(_RefundBrowser, self).__init__(self.fascard_user.laundry_group.id)
        self.account_url = "https://admin.fascard.com/%s/LoyaltyAccounts?recid=%s" % (self.url_number, self.fascard_user.fascard_user_account_id)
        self.login()
        
    def refund(self):
        self.open(self.account_url, self.account_url, True)
        balance_box = self.driver.find_element_by_id(self.BALLANCE_BOX_ID)
        current_balance = round(float(balance_box.get_attribute('value')),2)
        new_balance = round(current_balance + self.refund_amount,2)
        balance_box.clear()
        balance_box.send_keys(str(new_balance))         
        submit_button = self.driver.find_element_by_xpath(self.SUBMIT_XPATH)
        submit_button.click()
        time.sleep(5)
        #Check to bake sure balance is correct 
        self.open(self.account_url, self.account_url, True)
        balance_box = self.driver.find_element_by_id(self.BALLANCE_BOX_ID)
        reloaded_balance = round(float(balance_box.get_attribute('value')),2)
        if reloaded_balance != new_balance:
            return False 
        else:
            return True 
    