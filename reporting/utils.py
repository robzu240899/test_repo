
from reporting.models import PricingPeriod
from roommanager.models import EquipmentType


class PricingPeriodDataStructure():
    def __init__(self, pricing_period):
        self.pricing_period = pricing_period
        self.data = {self.pricing_period: {'Equipments': {}}}

    def set_equipment(self, equipment):
        self.data[self.pricing_period]['Equipments'][equipment] = {
            'Cycles':[]
        }

    def add_cycle(self, equipment, cycle):
        self.data[self.pricing_period]['Equipments'][equipment]['Cycles'].append(cycle)

    def update(self, obj, dict_data):
        """
        Adds new items to the current pricing period
        """
        if not obj:
            raise Exception('Did not receive a proper obj to be updated')
        if isinstance(dict_data, dict):
            is_pricing_period = isinstance(obj, PricingPeriod)
            is_equipment = isinstance(obj, EquipmentType)
            for k,v in dict_data.items():
                if is_pricing_period and k not in self.data[self.pricing_period]:
                        self.data[self.pricing_period][k] = v
                elif is_equipment and k not in self.data[self.pricing_period]['Equipments'][obj]:
                        self.data[self.pricing_period]['Equipments'][obj][k] = v
                else:
                    raise Exception('{} already exist. No duplicates allowed'.format(k))
        else:
            raise Exception('Can not update pricing period. Data is on a dict')

    def get_data(self):
        return self.data

    def delete_equipment(self, equipment):
        del self.data[self.pricing_period]['Equipments'][equipment]

class EquipmentDataStructure():
    def __init__(self, equipment):
        self.equipment = equipment
        self.data = {
            self.equipment : {
                'Pricing Periods': {},
            }
        }

    def set_pricing_period(self, pricing_period):
        self.data[self.equipment]['Pricing Periods'][pricing_period] = {
            'Cycles':[],
        }

    def add_cycle(self, pricing_period, cycle):
        self.data[self.equipment]['Pricing Periods'][pricing_period]['Cycles'].append(cycle)

    def update(self, obj, dict_data):
        """
        Adds new items to the current pricing period
        """
        if not obj:
            raise Exception('Did not receive a proper obj to be updated')
        if isinstance(dict_data, dict):
            is_pricing_period = isinstance(obj, PricingPeriod)
            is_equipment = isinstance(obj, EquipmentType)
            for k,v in dict_data.items():
                if is_pricing_period and k not in self.data[self.equipment]['Pricing Periods'][obj]:
                        self.data[self.equipment]['Pricing Periods'][obj][k] = v
                elif is_equipment and k not in self.data[self.equipment]:
                        self.data[self.equipment][k] = v
                else:
                    raise Exception('{} already exist. No duplicates allowed'.format(k))
        else:
            raise Exception('Can not update pricing period. Data is on a dict')

    def get_data(self):
        return self.data


class CyclePlaceholder:

    def __init__(self, cycle_type, price):
        self.cycle_type = cycle_type
        self.price = price

    def get_price(self):
        result = self.price/100.0
        return ("%.2f (same as previous)" % result)

    @property
    def is_placeholder(self):
        return True