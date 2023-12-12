'''
Created on Apr 17, 2017

@author: Thomas
'''

from decimal import Decimal

from ...enums import ExpenseType

class ExpenseManager(object):
    
    def __init__(self,expenses,credit_card_revenue):
        self.expenses = expenses
        self.credit_card_revenue = credit_card_revenue
        self.line_items = {}
        self.total = None
        
    def process(self):
        repeated_expense_name_memory = {}
        for line_item in self.expenses:
            expense_type = line_item['expense_type']
            expense_amount = line_item['expense_amount']
            if expense_type.expense_type == ExpenseType.STANDARD:
                line_item_val = Decimal(str(expense_amount))
            elif expense_type.expense_type == ExpenseType.CREDIT_CARD_SPLIT:
                line_item_val = Decimal(str(expense_amount)) * Decimal(str(self.credit_card_revenue))
            else:
                raise Exception("Unknown or Unimplemented Expense type found in ExpenseManager.process")
            if expense_type.display_name in self.line_items:
                if not expense_type.display_name in repeated_expense_name_memory:
                    repeated_expense_name_memory[expense_type.display_name] = 0
                repeated_expense_name_memory[expense_type.display_name] += 1
                line_item_name = f"{expense_type.display_name}-{repeated_expense_name_memory[expense_type.display_name]}"
            else:
                line_item_name = expense_type.display_name 
            self.line_items[line_item_name] = line_item_val
        self.total = sum([x for x in self.line_items.values()])