from django.core.exceptions import ValidationError

class BalanceChangedException(Exception):
    
    def __init__(self, balance_type, msg=None):
        msg = f"The user's {balance_type} changed and this request is no longer valid"
        super(BalanceChangedException, self).__init__(msg)

class TotalBalanceExceeded(ValidationError):

    def __init__(self, tx_state, requested_refund, available_for_refund, msg=None):
        msg = f"Total refunds to date: ${tx_state}. New requested refund: ${requested_refund}. Balance available for refund: ${available_for_refund}"
        super(TotalBalanceExceeded, self).__init__(msg)