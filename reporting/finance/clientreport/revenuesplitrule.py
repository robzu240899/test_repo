from ... import enums 
from decimal import Decimal
class RevenueRuleAdaptor():
    
    def create_rule(self,revenue_rule, *args, **kwargs):
        '''
        @revenue_rule RevenueSplitRule (django) object 
        @returns BreakpointRule

        General Breakpoint:

            -base_rent: Simple amount of rent that we pay the landlord every month
            -Breakpoint: Net revenue number above which we will pay the landlord a percentage rent
                -If net_revenue < breakpoint we don't pay any percentage rent. The landlord will only
                receive base_rent in this case.
                    -Landlord may not receive base_rent if the room didn't earn enough so that net_revenue > min_comp + base_rent
                -Special case: Percentage rent deals where we set the breakpoint to $0

        '''
        
        if revenue_rule.revenue_split_formula == enums.RevenueSplitFormula.PERCENT:
            return BreakpointRule(base_rent=0.0,
                                  landloard_split_percent=revenue_rule.landloard_split_percent,
                                  breakpoint=0.0, *args, **kwargs)
        elif revenue_rule.revenue_split_formula == enums.RevenueSplitFormula.GENERAL_BREAKPOINT:
            return BreakpointRule(base_rent=revenue_rule.base_rent,
                                  landloard_split_percent=revenue_rule.landloard_split_percent,
                                  breakpoint=revenue_rule.breakpoint, *args, **kwargs)
        # elif revenue_rule.revenue_split_formula == enums.RevenueSplitFormula.NATURAL_BREAKPOINT:
        #     return BreakpointRule(base_rent=revenue_rule.base_rent,
        #                           landloard_split_percent=revenue_rule.landloard_split_percent,
        #                           breakpoint=revenue_rule.base_rent, *args, **kwargs)  #TODO: verify with dan
        else:
            raise Exception("Undefined/Not Implemented BreakpointRule type")

class BreakpointRule():
    
    def __init__(self,base_rent,landloard_split_percent,
                 breakpoint, prorate=False, prorate_factor=1):
        self.base_rent = Decimal(str(base_rent))
        self.landloard_split_percent = Decimal(str(landloard_split_percent)) 
        self.breakpoint = Decimal(str(breakpoint))
        self.prorate = prorate
        self.prorate_factor = Decimal(str(prorate_factor))

    def calculate_split(self,revenue):
        if self.prorate: assert self.prorate_factor > 0
        base_rent = self.base_rent * self.prorate_factor
        breakpoint_ = self.breakpoint * self.prorate_factor
        client_share = base_rent + max(Decimal('0.00'),self.landloard_split_percent*(Decimal(str(revenue))-breakpoint_))
        aces_share = revenue - client_share
        return client_share,aces_share