'''
Created on Apr 21, 2017

@author: Thomas
'''
from ...enums import InternalDerivedMetricCalcRule
from collections import namedtuple
    

    
class RevenueConfig():
    RevenueConfigInstruction = namedtuple('RevenueConfigInstruction', ['calc_type','column_name','metric_name','multiplier'])
    CALCULATED_METRICS = [#RevenueConfigInstruction(InternalDerivedMetricCalcRule.DIVIDE_BY_REVENUE,'num_units',"Revenue Per Unit",1),
                          RevenueConfigInstruction(InternalDerivedMetricCalcRule.BOOLEAN,'laundry_in_unit',"Has Laundry In Units ",1),
                          RevenueConfigInstruction(InternalDerivedMetricCalcRule.PLAIN,'num_units',"Total Units",1),
                          RevenueConfigInstruction(InternalDerivedMetricCalcRule.PLAIN,'legal_structure',"Legal Structure",1),
                          RevenueConfigInstruction(InternalDerivedMetricCalcRule.PLAIN,'building_type',"Building Type",1),
                          #RevenueConfigInstruction(InternalDerivedMetricCalcRule.DIVIDE_BY_REVENUE,'square_feet_residential','Revenue Per 100 Res. Sq. Ft.',100),
                          RevenueConfigInstruction(InternalDerivedMetricCalcRule.BOOLEAN,'has_elevator',"Has Elevator",1),
                          RevenueConfigInstruction(InternalDerivedMetricCalcRule.BOOLEAN,'is_outdoors',"Is Outdoors",1)
                          ]
