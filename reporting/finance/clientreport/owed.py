'''
Created on May 17, 2018

@author: tpk6
'''

class OwedCalculator(object):
    
    def __init__(self,client_share, aces_share, aces_collects_cash, cash_amount, client_name):
        self.client_share = client_share 
        self.aces_share = aces_share 
        self.aces_collects_cash = aces_collects_cash
        self.cash_amount = cash_amount 
        self.client_name = client_name
        
    def calculate(self):
        '''
        Returns how much money aces owes to the client
        Note we assume that aces collects everything besides the cash amount in all cases.  If aces_collects_cash = True, aces also collects the cash
        '''
        if self.aces_collects_cash == True:
            owed = self.client_share
        else:
            owed = self.client_share - self.cash_amount
        if owed >= 0:
            txt = "Aces Owes %s" % self.client_name
        else:
            txt = "%s Owes Aces" % self.client_name
        return owed, txt