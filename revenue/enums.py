'''
Created on Apr 24, 2017

@author: Duong
'''

class PaymentType(): 
    CREDIT = 'CREDIT'
    LOYALTY = 'LOYALTY'
    EITHER = 'EITHER'
     
    CHOICES = ((CREDIT,CREDIT),(LOYALTY,LOYALTY),(EITHER,EITHER))


class ActivityType(): 
    MACHINE_START = 'MACHINE_START'
    VALUE_ADD = 'VALUE_ADD'
    EITHER = 'EITHER'
    SINGLE_CHOICES = ((MACHINE_START,MACHINE_START),(VALUE_ADD,VALUE_ADD))
    CHOICES = ((MACHINE_START,MACHINE_START),(VALUE_ADD,VALUE_ADD),(EITHER,EITHER))

class RefundType(): 
    FASCARD = 'Fascard'
    AUTHORIZEDOTNET = 'AuthorizeDotNet'
    
    CHOICES = ((FASCARD,FASCARD),(AUTHORIZEDOTNET,AUTHORIZEDOTNET))

class TransactionType():
    ADD_VALUE = 2
    ADMIN_ADJUST = 3
    VEND = 100
    COINS = 11
    CASHOUT_REQUEST = 101
    DAMAGE_REFUND_REQUEST = 201

    MAP = {
        2 : 'ADD_VALUE',
        3 : 'ADMIN_ADJUST',
        100 : 'VEND',
    }
    
    CHOICES = ((ADD_VALUE,ADD_VALUE),(VEND,VEND))

class AddValueSubType():
    CREDIT_AT_READER = 0  #This really means someone used the reader to add value.  It can be credit or cash
    CREDIT_ON_WEBSITE = 1 
    CASH = 2   #This is really an employee doing a value added to account adjustment  
    AUTO_RELOAD = 3
    FAKE = 500 #lame duck for fake transactionz

    MAP = {
        0 : 'Credit at Reader',
        1 : 'Credit on Website',
        2 : 'Cash',
        3 : 'Auto Reload'
    }
    
    CHOICES = ((CREDIT_AT_READER, CREDIT_AT_READER), (CREDIT_ON_WEBSITE, CREDIT_ON_WEBSITE ),
               (CASH, CASH), (AUTO_RELOAD, AUTO_RELOAD))
    

class TransactionTypeDisplay():

    dict_repr = {
        2: {
            'type' : 'Add Value',
            'sub_types' : (
                'Reader',
                'Credit Card via Web',
                'Cash to Employee',
                'Point of Sale'
            )
        },
        100: {
            'type' : 'Vend',
            'sub_types' : (
                'Machine',
                'Credit surcharge',
                'Point of Sale'
            )
        }
    }


class RefundWizardTxType:
    NONE = -100
    LOYALTY = 0
    DIRECT_VEND = 1

class RefundChannelChoices:
    AUTHORIZE = 0
    FASCARD_ADJUST = 1
    CHECK = 2
    
    AUTHORIZE_CHOICE = (AUTHORIZE, 'Authorize.net CC Refund')
    FASCARD_ADJUST_CHOICE = (FASCARD_ADJUST, 'Fascard Balance Adjust')
    CHECK_CHOICE = (CHECK, 'Check')

    DIRECT_VEND_CHOICES = (
        AUTHORIZE_CHOICE,
        FASCARD_ADJUST_CHOICE
    )

    CHOICES = (
        AUTHORIZE_CHOICE,
        FASCARD_ADJUST_CHOICE,
        CHECK_CHOICE
    )

TX_TYPE_CHOICES = (
    (RefundWizardTxType.LOYALTY, 'Loyalty machine starts or Loyalty value add'),
    (RefundWizardTxType.DIRECT_VEND, 'Direct Credit Card Machine Start'),
)

class RefundTypeChoices:
    TRANSACTION = 'Transaction'
    CASHOUT = 'Cashout'
    DAMAGE = 'Damage'

    CHOICES = (
        (TRANSACTION, TRANSACTION),
        (CASHOUT, CASHOUT),
        (DAMAGE, DAMAGE),
    )



class FascardBalanceType():
    BALANCE = 'Balance'
    BONUS = 'Bonus'

    CHOICES = (
        (BALANCE, BALANCE),
        (BONUS, BONUS)
    )