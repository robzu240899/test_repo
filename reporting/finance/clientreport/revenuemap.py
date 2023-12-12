import calendar
from decimal import Decimal
from datetime import date, timedelta
from django.db.models import Q
from ...models import RevenueSplitRule
from ...enums import RevenueSplitScheduleType


class SplitRuleMap():

    def __init__(self, split_rule, applicable_revenue, split_rule_prorating=False, split_rule_prorate_factor=1, days_in_effect=None):
        self.revenue_split_rule = split_rule
        self.applicable_revenue = applicable_revenue
        self.split_rule_prorating = split_rule_prorating
        self.split_rule_prorate_factor = split_rule_prorate_factor
        self.days_in_effect = days_in_effect


class RevenueMapFactory():
    
    @classmethod 
    def create_mapper(cls, billing_group, current_net_revenue, start_date, previous_gross_revenue):
        schedule_type = billing_group.schedule_type
        if schedule_type == RevenueSplitScheduleType.CONSTANT:
            return ConstantMapper(billing_group, current_net_revenue)
        elif schedule_type == RevenueSplitScheduleType.TIME:
            return TimeMapper(billing_group, current_net_revenue, **{'start_date': start_date})
        elif schedule_type == RevenueSplitScheduleType.GROSS_REVENUE:
            return GrossRevenueMapper(billing_group, current_net_revenue, **{'previous_gross_revenue': previous_gross_revenue})
        

class RevenueMapper(object):
    '''Maps revenue to the revenue split rule that should be applied to it.
       create_map returns a list of tuples, [(revenue split rule 1, applicable revenue 1, revenue split rule 2, applicable revenue 2)...]
       Note that the sum of applicable revenues should equal the current_net_revenue
    '''
    
    def __init__(self, billing_group, current_net_revenue, **kwargs):
        self.billing_group = billing_group 
        self.current_net_revenue = current_net_revenue
        
    def create_map(self):
        raise Exception("Not implemented error")
    
class ConstantMapper(RevenueMapper):
    """
    Only one revenue split rule is used for the entire lease term.
    """
    
    def create_map(self):
        '''Return the single revenue split rule associate with the billing group along with the current net revenue'''
        split_rule_map = SplitRuleMap(
            RevenueSplitRule.objects.get(billing_group = self.billing_group),
            self.current_net_revenue
        ) 
        return [split_rule_map]
    
class TimeMapper(RevenueMapper):
    """
    The revenue split rule changes based on scheduled date.
    After update, one month may have more than one revenue split rules in effect, so revenue
    split gets prorated respectively.
    """
    
    def __init__(self, *args, **kwargs):
        super(TimeMapper, self).__init__(*args)
        self.start_date = kwargs['start_date']
        
    def create_map(self):
        revenue_map = []
        end_of_month = date(
                self.start_date.year,
                self.start_date.month,
                calendar.monthrange(*tuple([self.start_date.year, self.start_date.month,]))[1]
            )
        timeQ = (Q(start_date__lte=self.start_date) & Q(end_date__gt=self.start_date)) | \
                (Q(start_date__lte=self.start_date) & Q(end_date=None)) | \
                (Q(start_date__gte=self.start_date) & Q(start_date__lte=end_of_month)) | \
                (Q(start_date=None)                 & Q(end_date__gt=self.start_date))  
        rules = RevenueSplitRule.objects.filter(timeQ,billing_group=self.billing_group).order_by('start_date')
        days_in_month = calendar.monthrange(*tuple([self.start_date.year, self.start_date.month]))[1]
        if rules.count()>1:
            results = []
            start = self.start_date
            for i, split_rule in enumerate(rules):
                days_in_effect = (min(split_rule.end_date, end_of_month) - start)
                if i == rules.count() - 1:
                    days_in_effect += timedelta(days=1)
                attributable_revenue = (self.current_net_revenue / days_in_month) * days_in_effect.days
                split_rule_prorate = days_in_effect.days / days_in_month
                split_rule_map = SplitRuleMap(
                    split_rule,
                    attributable_revenue,
                    split_rule_prorating = True,
                    split_rule_prorate_factor = split_rule_prorate,
                    days_in_effect = days_in_effect.days)
                results.append(split_rule_map)
                start = split_rule.end_date
            return results
        else:
            revenue = self.current_net_revenue
            return [SplitRuleMap(rules.first(), revenue)]


class GrossRevenueMapper(RevenueMapper):
    """
    The Revenue attribution changes based on BEFORE revenue metric.
    I.e: the total lifetime revenue of the laundry room determines which revenue_split_rule should be in effect.
    """
    
    def __init__(self, *args, **kwargs):
        super(GrossRevenueMapper, self).__init__(*args)
        self.previous_gross_revenue = kwargs['previous_gross_revenue']  
    
    def create_map(self):
        '''Any net revenue that falls in between a split rule x's gross revenue start and gross revenue end should be associated with split rule x.
           Also, x's billing group must be self.billing_gorup'''
        retval = []
        revenue_start = self.previous_gross_revenue
        revenue_end = self.previous_gross_revenue + self.current_net_revenue
        for rule in RevenueSplitRule.objects.filter(billing_group=self.billing_group):
            if rule.start_gross_revenue:
                schedule_startpoint = rule.start_gross_revenue
            else:
                schedule_startpoint = Decimal('0.00')
            #NB: If the rule has no end point, use the revenue to date
            if rule.end_gross_revenue:
                schedule_endpoint = rule.end_gross_revenue
            else:
                schedule_endpoint = revenue_end
            revenue = min(schedule_endpoint, revenue_end) - max(schedule_startpoint, revenue_start)
            if revenue > 0:
                split_rule_map = SplitRuleMap(rule, revenue)
                retval.append(split_rule_map)
        return retval