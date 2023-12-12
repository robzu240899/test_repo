'''
Created on May 15, 2018

@author: tpk6
'''
import calendar
from datetime import date
from decimal import Decimal
from .revenuemap import RevenueMapFactory
from reporting.finance.clientreport.revenuesplitrule import RevenueRuleAdaptor


class RevenueSplitter(object):
    '''
        Responsible for handling the entire process of splitting revenue between aces and clients
        Steps in the process:
        1) Determine which Revenue split rules apply.  Determine how much revenue should be applied via each rule.
        Input:  Billing Group, start date, final date 
        Output: [(revenue split rule 1, applicable revenue 1), (revenue split rule 2, applicable revenue 2)...]
        2) Calculate the revenue split for each rule/revenue combination calculated in step 1
        Input: [(revenue split rule 1, applicable revenue 1), (revenue split rule 2, applicable revenue 2)...]
        Output: [(aces share of revenue 1, client share of revenue 1), (aces share of revenue 2, client share of revenue 2)...]
        3) Calculate total revenue splits 
        Input: [(aces share of revenue 1, client share of revenue 1), (aces share of revenue 2, client share of revenue 2)...]
        Output: aces share of revenue, client share of revenue 
    '''
    
    def __init__(self, billing_group, current_net_revenue, start_date, previous_gross_revenue):
        self.billing_group = billing_group
        self.current_net_revenue = current_net_revenue
        self.start_date = start_date 
        self.previous_gross_revenue = previous_gross_revenue
        self.prorate = False
        self.prorate_factor = 1
        self._load_revenue_maps()

    def _load_revenue_maps(self):
        self.revenue_maps = RevenueMapFactory.create_mapper(
            self.billing_group,
            self.current_net_revenue,
            self.start_date,
            self.previous_gross_revenue
        ).create_map()
        #TODO: change, timemapper may return more than one split_rule
        #Assuming only one revenue split rule is returned by RevenueMapFactory
        #Apparently we used to have support for multiple revenue split rules
        #at a time but that's no longer the case. Current revenue mappers always return
        #a single rule
        self.split_rule = self.revenue_maps[0].revenue_split_rule
        self.split_rule_applicable_revenue = self.revenue_maps[0].applicable_revenue

    def check_prorating(self):
        bg_operations_start = getattr(self.billing_group, 'operations_start_date', None)
        if bg_operations_start:
            bg_operation = list()
            start_date = list()
            for attr in ['year', 'month']:
                bg_operation.append(getattr(bg_operations_start, attr, None))
                start_date.append(getattr(self.start_date, attr, None))
            if bg_operation == start_date:
                self.days_in_month = calendar.monthrange(*tuple(start_date))[1]
                start_date.append(self.days_in_month)
                last_day_date = date(*tuple(start_date))
                self.operations_start = bg_operations_start
                self.operations_days = (last_day_date - self.operations_start).days + 1
                self.prorate_factor = self.operations_days / self.days_in_month
                self.prorate = True
        return (self.prorate, self.prorate_factor)
        

    def split_revenue(self):
        '''Returns client share of revenue (Decimal), aces share of revenue (Decimal)'''
        revenue_maps = self.revenue_maps
        if not revenue_maps:
            raise Exception("No applicalbe revenue split rules were found.")
        aces_share = Decimal('0.00')
        client_share = Decimal('0.00')
        self.base_rent = None
        revenue_shares = []
        for split_rule_map in revenue_maps:
            base_rent = getattr(split_rule_map.revenue_split_rule, 'base_rent', None)
            if base_rent:
                self.base_rent = base_rent
            if split_rule_map.split_rule_prorating:
                extra_kwargs = {
                    'prorate' : True,
                    'prorate_factor': split_rule_map.split_rule_prorate_factor
                }
                days_in_effect = split_rule_map.days_in_effect
            else:
                extra_kwargs = {}
                days_in_effect = None
                prorate, prorate_factor = self.check_prorating()
                if prorate:
                    extra_kwargs = {'prorate' : prorate, 'prorate_factor': prorate_factor}
            applicable_rule =  RevenueRuleAdaptor().create_rule(
                split_rule_map.revenue_split_rule,
                **extra_kwargs
            )
            client_sub_share, aces_sub_share = applicable_rule.calculate_split(
                split_rule_map.applicable_revenue)
            revenue_shares.append({
                'client_sub_share' : client_sub_share,
                'aces_sub_share' : aces_sub_share,
                'days_in_effect' : days_in_effect,
                'split_rule' : split_rule_map.revenue_split_rule
                }
            )                
            client_share += client_sub_share
            aces_share += aces_sub_share
        return revenue_shares
        #return client_share, aces_share
    
        
        
        
        
            