from .. import enums 
from decimal import Decimal
class RevenueRuleAdaptor():
    
    def create_rule(self,revenue_rule):
        '''
        @revenue_rule RevenueSplitRule (django) object 
        @returns BreakpointRule
        '''
        
        if revenue_rule.revenue_split_formula == enums.RevenueSplitFormula.PERCENT:
            return BreakpointRule(base_rent=0.0,
                                  landloard_split_percent=revenue_rule.landloard_split_percent,
                                  breakpoint=0.0)
        elif revenue_rule.revenue_split_formula == enums.RevenueSplitFormula.GENERAL_BREAKPOINT:
            return BreakpointRule(base_rent=revenue_rule.base_rent,
                                  landloard_split_percent=revenue_rule.landloard_split_percent,
                                  breakpoint=revenue_rule.breakpoint)
        # elif revenue_rule.revenue_split_formula == enums.RevenueSplitFormula.NATURAL_BREAKPOINT:
        #     return BreakpointRule(base_rent=revenue_rule.base_rent,
        #                           landloard_split_percent=revenue_rule.landloard_split_percent,
        #                           breakpoint=revenue_rule.base_rent)  #TODO: verify with dan
        else:
            raise Exception("Undefined/Not Implemented BreakpointRule type")

class BreakpointRule():
    
    def __init__(self,base_rent,landloard_split_percent,
                 breakpoint):
        self.base_rent = Decimal(str(base_rent))
        self.landloard_split_percent = Decimal(str(landloard_split_percent)) 
        self.breakpoint = Decimal(str(breakpoint))
    
    def calculate_split(self,revenue):
        client_share = self.base_rent + max(Decimal('0.00'),self.landloard_split_percent*(Decimal(str(revenue))-self.breakpoint))
        aces_share = revenue - client_share
        return client_share,aces_share        
        
        