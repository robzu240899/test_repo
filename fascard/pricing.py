'''
Created on Dec 20, 2017

@author: tpk6
'''
import logging
import time
from decimal import *
from datetime import datetime
from selenium.webdriver.support.ui import Select
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from django.db.transaction import atomic
from fascard.api import FascardApi
from reporting.models import PriceHistory
from roommanager.models import LaundryRoom
from .config import FascardSeleniumPricingConfig
from .fascardghost import FascardGhostBrowser

logger = logging.getLogger(__name__)

class PriceFetcher(object):
    
    def get_prices(self, fascard_location_id):
        laundry_group_id = 1 #TODO: cleanup
        api = FascardApi(laundry_group_id)
        dt = datetime.now() #TODO: change to getting utc time and then convert to eastern
        for api_price in api.get_pricing(fascard_location_id): 
            price = Price(laundry_room, machine_type, cycle_type, price)
            PriceToOrm().convert(price, dt)

class PriceScraperManager(object):

    @classmethod 
    def scrape(cls, laundry_room_id):
        with PriceBrowser(laundry_room_id) as browser:
            prices = browser.get_price_data()
        dt = datetime.now().date()
        for price in prices:
            PriceToOrm().convert(price, dt)

class Price(object):
    
    def __init__(self, laundry_room, machine_type, cycle_type, price):
        self.laundry_room = laundry_room
        self.cycle_type = cycle_type
        self.machine_type = self._clean_machine_type(machine_type)
        self.price = self._clean_price(price)
    
    def _clean_machine_type(self, machine_type):
        return machine_type.split("(")[0].strip().lower()
    
    def _clean_price(self, price):
        return Decimal(price.strip().replace("$",""))
    
    def _clean_cycle_typle(self,cycle_type):
        return cycle_type.strip().lower()
    
    def __str__(self):
        txt = 'Laundry Room: %s | Machine TYpe %s | Cycle Type %s | Price %s' % (self.laundry_room.display_name,
                            self.machine_type, self.cycle_type, self.price)
        return txt 

class PriceBrowser(object):
    
    def __init__(self, laundry_room_id):
        self.laundry_room_id = laundry_room_id
    
    def __enter__(self):
        self.browser =  _PriceBrowser(self.laundry_room_id)
        return self.browser
    
    def __exit__(self, exception_type, exception_value, traceback):
        self.browser.quit()
    

class _PriceBrowser(FascardGhostBrowser):
    
    def __init__(self, laundry_room_id):
        self.laundry_room = LaundryRoom.objects.get(pk = laundry_room_id)
        super(_PriceBrowser, self).__init__(self.laundry_room.laundry_group_id)
    
    def get_price_data(self):
        self.login()
        report_main_url = FascardSeleniumPricingConfig.REPORT_MAIN_URL % self.url_number
        self.open(report_main_url)
        self._select_pricing_report_from_dropdown()
        self._select_laundry_room()
        self._submit()
        return self._scrape_table()
    
    def _select_pricing_report_from_dropdown(self):
        self.driver.save_screenshot('D:\Daniel\testss.png')
        dropdown = Select(self.driver.find_element_by_name(FascardSeleniumPricingConfig.DROPDOWN_NAME)) 
        dropdown.select_by_visible_text(FascardSeleniumPricingConfig.DROPDOWN_PRICING_REPORT_TEXT)
        #Make sure the page loads.   NB: both pages are virtually the same.  There's just a refresh when you select the pricing report, and our next selections can't be erased.
        time.sleep(1) #Page has gone away
        WebDriverWait(self.driver, FascardSeleniumPricingConfig.POST_DROPDOWN_SELECT_DELAY_SECONDS).until(
            EC.presence_of_element_located((By.NAME, FascardSeleniumPricingConfig.POST_DROPDOWN_SELECT_WAIT_FOR_NAME))) #New page appears 
        
        
    def _select_laundry_room(self):
        checkbox = self.driver.find_element_by_xpath(FascardSeleniumPricingConfig.CHECKOX_XPATH % self.laundry_room.fascard_code)
        checkbox.click()
        #Make sure the page loads.   NB: both pages are virtually the same.  There's just a refresh when you select the pricing report, and our next selections can't be erased.
        time.sleep(1) #Page has gone away
        WebDriverWait(self.driver, FascardSeleniumPricingConfig.POST_CHECKBOX_SELECT_DELAY_SECONDS).until(
            EC.presence_of_element_located((By.NAME, FascardSeleniumPricingConfig.POST_CHECKBOX_SELECT_WAIT_FOR_NAME))) #New page appears    

    def _submit(self):
        submit_button = self.driver.find_element_by_id(FascardSeleniumPricingConfig.SUBMIT_BUTTON_ID)
        submit_button.click()
        WebDriverWait(self.driver, FascardSeleniumPricingConfig.POST_SUBMIT_DELAY_SECONDS).until(
            EC.presence_of_element_located((By.XPATH, FascardSeleniumPricingConfig.POST_SUBMIT_WAIT_FOR_XPATH))) #New page appears    
        time.sleep(1) #to be extra sure the page loaded

    def _scrape_table(self):
        retval = []
        cycle_types = []
        prices = []
        machine_type = None
        rows = self.driver.find_elements_by_xpath(FascardSeleniumPricingConfig.TABLE_ROWS_XAPTH)
        for i, row in enumerate(rows):
            if (i+1) % 3 == 1:  #We are in a pricing type headers row
                cycle_types = []
                for j, col in enumerate(row.find_elements_by_xpath("./th")):
                    if j != 0 and col.text and col.text.strip():
                        cycle_types.append(col.text)
            elif (i+1) % 3 == 2:  #We are looking a machine type row
                prices = []
                for j, col in enumerate(row.find_elements_by_xpath("./td")):
                    if j == 0:
                        machine_type = col.text 
                    elif col.text and col.text.strip():
                        prices.append(col.text)
                #create the price object
                if len(prices) == 0:
                    exception_string = "Blank row in prices found for %s" % self.laundry_room.display_name
                    logger.error(exception_string)
                    raise Exception(exception_string)
                elif len(prices) != len(cycle_types):
                    exception_string = "PricingScraper error: Mismatch in prices and cycle types length for room %s" % self.laundry_room.display_name
                    logger.error(exception_string)
                    raise Exception(exception_string)
                else:
                    for k in range(len(prices)):
                        retval.append(Price(self.laundry_room, machine_type, cycle_types[k], prices[k]))
            else:
                pass #blank row
        return retval
                    
class PriceToOrm(object):
    
    def __init__(self):
        pass 
    
    @atomic
    def convert(self, price, dt):       
        price_history = PriceHistory.objects.filter(laundry_room = price.laundry_room, machine_type = price.machine_type,
                                    cycle_type = price.cycle_type, price_date = dt).first()
        if price_history:
            price_history.price = price.price 
            price_history.save()
        else:
            price_history = PriceHistory.objects.create(laundry_room = price.laundry_room, machine_type = price.machine_type,
                                    cycle_type = price.cycle_type, price_date = dt, price = price.price)            
        
        
        
        
        