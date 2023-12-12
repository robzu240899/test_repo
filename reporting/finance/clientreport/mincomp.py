import logging
from decimal import Decimal

logger = logging.getLogger(__name__)

class MinimumCompensationRule(object):
    
    def __init__(self, billing_group, split_rule, aces_share, client_share, number_days):
        self.billing_group = billing_group 
        self.split_rule = split_rule
        self.aces_share = aces_share 
        self.client_share = client_share 
        self.total_revenue = self.aces_share + self.client_share
        self.number_of_days = number_days
        self.rule_applied = None 
        self.aces_share_after_mincomp = None 
        self.client_share_after_mincomp = None 
    
    def calculate(self):
        if self.split_rule.min_comp_per_day:
            min_compensation_per_day = self.split_rule.min_comp_per_day
        else:
            min_compensation_per_day = self.billing_group.min_compensation_per_day
            logging.info("No min_compensation_per_day in revenue split rule. Using Billing group's: {}".format(
                self.billing_group
            ))
        if min_compensation_per_day and self.aces_share < min_compensation_per_day * self.number_of_days:
            self.rule_applied = True
            self.aces_share_after_mincomp = Decimal(str(min_compensation_per_day * self.number_of_days))
            self.aces_share_after_mincomp = min(self.aces_share_after_mincomp, self.total_revenue)
            self.client_share_after_mincomp = self.total_revenue - self.aces_share_after_mincomp
        else:
            self.rule_applied = False
            self.aces_share_after_mincomp = self.aces_share
            self.client_share_after_mincomp = self.client_share