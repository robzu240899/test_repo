'''
Created on Dec 21, 2017

@author: tpk6
'''
from datetime import datetime, date , timedelta

from roommanager import models as roommanager_models
from roommanager import enums as roommanager_enums
from reporting import models as reporting_models
from reporting import enums as reporting_enums
from revenue import models as revenue_models
from revenue import enums as revenue_enums

import factory
from factory.declarations import LazyAttribute
from revenue.enums import AddValueSubType


class SmartIterators(object):

    INDEXES = {}

    @classmethod
    def _increment_index(cls, number, qry_id):
        try:
            cls.INDEXES[qry_id] += 1
        except KeyError:
            cls.INDEXES[qry_id] = 0
        if cls.INDEXES[qry_id] >= number:
            cls.INDEXES[qry_id] = 0


    @classmethod
    def get_related_object(cls, qry, qry_id):
        number = qry.count()
        cls._increment_index(number, qry_id)
        return qry[cls.INDEXES[qry_id]]

class TransactionTypeAdaptor(object):

    @classmethod
    def create_credit_vend_at_machine(cls, slot, amount, local_transaction_time, **extra):
        return LaundryTransactionFactory(
            slot = slot,
            credit_card_amount = amount, 
            cash_amount = 0,
            balance_amount = 0,
            local_transaction_time = local_transaction_time,
            transaction_type = revenue_enums.TransactionType.VEND, 
            trans_sub_type = None,
            **extra
        )

    @classmethod
    def create_credit_value_add_card_present(cls, laundry_room, amount, local_transaction_time):
        return LaundryTransactionFactory(laundry_room = laundry_room, slot = None, machine = None,
                                         credit_card_amount = amount, cash_amount = 0, balance_amount = 0,
                                         local_transaction_time = local_transaction_time,
                                         transaction_type = revenue_enums.TransactionType.ADD_VALUE, trans_sub_type = revenue_enums.AddValueSubType.CREDIT_AT_READER)

    @classmethod
    def create_credit_value_add_web(cls, laundry_room, amount, assigned_transaction_time):
        return LaundryTransactionFactory(laundry_room = None, slot = None, machine = None, assigned_laundry_room = laundry_room,
                                         credit_card_amount = amount, cash_amount = 0, balance_amount = 0,
                                         local_transaction_time = assigned_transaction_time-timedelta(days=2), assigned_local_transaction_time = assigned_transaction_time,
                                         transaction_type = revenue_enums.TransactionType.ADD_VALUE, trans_sub_type = revenue_enums.AddValueSubType.CREDIT_ON_WEBSITE)

    @classmethod
    def create_cash_value_add_at_kiosk(cls, laundry_room, amount, local_transaction_time):
        return LaundryTransactionFactory(laundry_room = laundry_room, slot = None, machine = None,
                                         credit_card_amount = 0, cash_amount = amount, balance_amount = 0,
                                         local_transaction_time = local_transaction_time,
                                         transaction_type = revenue_enums.TransactionType.ADD_VALUE, trans_sub_type = AddValueSubType.CREDIT_AT_READER) #NB: See enum notes about whatthis sub type means

    @classmethod
    def create_loyalty_card_vend_at_machine(cls, slot, amount, local_transaction_time):
        return LaundryTransactionFactory(slot = slot, balance_amount = amount, local_transaction_time = local_transaction_time,
                                         transaction_type = revenue_enums.TransactionType.VEND)

    @classmethod
    def create_check_deposit(cls, laundry_room, amount, local_transaction_time):
        return LaundryTransactionFactory(laundry_room = laundry_room, slot = None, machine = None,
                                         credit_card_amount = 0, cash_amount = amount, balance_amount = 0,
                                         local_transaction_time = local_transaction_time,
                                         transaction_type = revenue_enums.TransactionType.ADD_VALUE, trans_sub_type = AddValueSubType.CASH) #NB: See enum notes about whatthis sub type means


class LaundryGroupFactory(factory.django.DjangoModelFactory):

    display_name = factory.Sequence(lambda n: 'Laundry Group {0}'.format(n))

    class Meta:
        model = roommanager_models.LaundryGroup

class LaundryRoomFactory(factory.django.DjangoModelFactory):

    laundry_group = factory.Iterator(roommanager_models.LaundryGroup.objects.all()) #TODO: change to new method
    display_name =  factory.Sequence(lambda n: 'Laundry Room {0}'.format(n))
    fascard_code =  factory.Sequence(lambda n: n)
    time_zone = roommanager_enums.TimeZoneType.EASTERN

    class Meta:
        model = roommanager_models.LaundryRoom

class PirceHistoryFactory(factory.django.DjangoModelFactory):

    class Meta:
        model = reporting_models.PriceHistory

class SlotFactory(factory.django.DjangoModelFactory):

    laundry_room = factory.Iterator(roommanager_models.LaundryRoom.objects.all()) #TODO: change to new method

    idle_cutoff_seconds = 10000
    is_active = True
    slot_type = factory.Iterator(roommanager_enums.SlotType.CHOICES, getter=lambda c: c[0])
    slot_fascard_id = factory.Sequence(lambda n: 'Slot Fascard ID: {0}'.format(n)) 
    web_display_name = factory.Sequence(lambda n: 'Web Display Name: {0}'.format(n))
    clean_web_display_name = factory.LazyAttribute(lambda slot: slot.web_display_name)
    last_run_time = datetime(2017,2,1,10,11,13)

    class Meta:
        model = roommanager_models.Slot

class MachineSlotMap(factory.django.DjangoModelFactory):


    is_active = True
    start_time = datetime(2017,2,1,10,11)
    end_time = None

    class Meta:
        model = roommanager_models.MachineSlotMap

class MachineFactory(factory.django.DjangoModelFactory):


    machine_type = factory.Iterator(roommanager_enums.MachineType.CHOICES, getter=lambda c: c[0])
    purchase_date = date(2017,1,1)
    make = "Test Make"
    machine_text = "Machine Text"
    is_active = True
    machine_description = "Machine Description"

    class Meta:
        model = roommanager_models.Machine

class FascardUserFactory(factory.django.DjangoModelFactory):

    name = factory.Sequence(lambda n: "Name {0}".format(n))
    laundry_group = LazyAttribute(lambda user: SmartIterators.get_related_object(roommanager_models.LaundryGroup.objects.all(),'fuflaundrygroup'))
    fascard_user_account_id = factory.Sequence(lambda n: n)
    is_employee = False

    class Meta:
        model = revenue_models.FascardUser

class LaundryTransactionFactory(factory.django.DjangoModelFactory):

    external_fascard_id = factory.Sequence(lambda n: '{0}'.format(n))
    laundry_room = factory.LazyAttribute(lambda tx: tx.slot.laundry_room)
    fascard_code = factory.LazyAttribute(lambda tx: tx.slot.laundry_room.fascard_code if tx.slot else tx.laundry_room.fascard_code if tx.laundry_room else 0)
    slot = factory.Sequence(lambda _ : SmartIterators.get_related_object(roommanager_models.Slot.objects.all(), 'ltfslot'))
    machine = LazyAttribute(lambda tx: SmartIterators.get_related_object(roommanager_models.MachineSlotMap.objects.filter(is_active=True, slot = tx.slot), 'ltfmachine').machine)
    web_display_name = factory.LazyAttribute(lambda tx: tx.slot.web_display_name if tx.slot else None)
    first_name = factory.Sequence(lambda n: "First Name {0}".format(n))
    last_name = factory.Sequence(lambda n: "Last Name {0}".format(n))
    local_transaction_date = factory.LazyAttribute(lambda tx: tx.local_transaction_time.date())
    utc_transaction_date = None #We never use this, so we want it to cause issues if we try to.
    #transaction type Should always be defined
    credit_card_amount = 0
    cash_amount = 0
    balance_amount = 0
    last_four = None
    card_number = None
    card_type = None
    local_transaction_time = factory.Iterator([datetime(2017,1,1), datetime(2017,1,2), datetime(2017,2,1), datetime(2017,2,2)])
    utc_transaction_time = factory.LazyAttribute(lambda tx: tx.local_transaction_time - timedelta(hours=4))
    fascard_user = factory.Sequence(lambda _ : SmartIterators.get_related_object(revenue_models.FascardUser.objects.all(), 'ltffascarduser'))
    external_fascard_user_id = factory.LazyAttribute(lambda tx: tx.fascard_user.fascard_user_account_id)
    #external_fascard_user_id = foo
    dirty_name = factory.Sequence(lambda n: "Dirty Name {0}".format(n))
    loyalty_card_number = None #not used
    authorizedotnet_id = None #Not used
    additional_info = None #Not used
    root_transaction_id = None #Not used
    bonus_amount = None  #Not used
    new_balance = None  #Not used
    new_bonus = None  #Not used
    new_free_starts = None  #Not used
    new_loyalty_points = None  #Not used
    loyalty_points = None   #Not used
    employee_user_id = None
    trans_sub_type = None  #Not used
    free_starts = None  #Not used
    unfunded_amount = 0
    sys_config_id = None  #Not used
    assigned_laundry_room = factory.LazyAttribute(lambda tx: tx.laundry_room)
    assigned_utc_transaction_time = factory.LazyAttribute(lambda tx: tx.utc_transaction_time)
    assigned_local_transaction_time = factory.LazyAttribute(lambda tx: tx.local_transaction_time)

    class Meta:
        model = revenue_models.LaundryTransaction

class UnassignedLaundryTransactionFactory(LaundryTransactionFactory):

    assigned_laundry_room = None
    assigned_utc_transaction_time = None
    assigned_local_transaction_time = None

    class Meta:
        model = revenue_models.LaundryTransaction

#Depricated
class WebValueAddTransactionFactory(LaundryTransactionFactory):
    '''Don't pass in laundry room, slot or machine!  Use assigned_laundry_room'''
    laundry_room = None
    slot = None
    machine = None
    fascard_code = 0
    web_display_name = None
    local_transaction_time = None
    local_transaction_date = None
    transaction_type = revenue_enums.TransactionType.ADD_VALUE


class BillingGroupFactory(factory.django.DjangoModelFactory):

    display_name = factory.Sequence(lambda n: 'Display Name: {0}'.format(n))
    schedule_type = factory.Iterator(reporting_enums.RevenueSplitScheduleType.CHOICES, getter=lambda c: c[0])
    min_compensation_per_day = factory.Iterator([0, 3])
    aces_collects_cash = True
    is_active = True

    class Meta:
        model = reporting_models.BillingGroup

class LaundryRoomExtensionFactory(factory.django.DjangoModelFactory):

    #NB, need to specify Billing Group and LaundryRoom
    num_units = factory.Iterator([0,10,20,30,50])
    square_feet_residential = factory.Iterator([0,1000,2000,30000,50000])

    class Meta:
        model = reporting_models.LaundryRoomExtension


class EquipmentTypeFactory(factory.django.DjangoModelFactory):

    fascard_id = factory.Sequence(lambda n: '{0}'.format(n))
    laundry_group =  LazyAttribute(lambda _ : SmartIterators.get_related_object(roommanager_models.LaundryGroup.objects.all(), 'equipmenttypefactorylaundrygroup'))
    machine_text = factory.Sequence(lambda n: 'Machine Text {0}'.format(n))
    machine_type = factory.Iterator(roommanager_enums.MachineType.CHOICES, getter = lambda c: c[0])

    class Meta:
        model = roommanager_models.EquipmentType

class RevenueSplitRuleFactory(factory.django.DjangoModelFactory):

    class Meta:
        model = reporting_models.RevenueSplitRule

class MetricFacotry(factory.django.DjangoModelFactory):

    class Meta:
        model = reporting_models.MetricsCache


class ExpenseTypeFactory(factory.django.DjangoModelFactory):

    display_name = factory.Sequence(lambda n: 'Expense {0}'.format(n))
    description =  factory.Sequence(lambda n: 'Expense Desc {0}'.format(n))
    expense_type = factory.Iterator(reporting_enums.ExpenseType.CHOICES, getter = lambda c: c[0])

    class Meta:
        model = reporting_models.ExpenseType

class BillingGroupExpenseTypeMapFactory(factory.django.DjangoModelFactory):

    billing_group = LazyAttribute(lambda _ : SmartIterators.get_related_object(reporting_models.BillingGroup.objects.all(), 'billinggroupbillinggroupexpensetypemapfactory'))
    expense_type = LazyAttribute(lambda _ : SmartIterators.get_related_object(reporting_models.ExpenseType.objects.all(), 'expensetypebillinggroupexpensetypemapfactory'))
    default_amount = factory.Sequence(lambda n: n)

    class Meta:
        model = reporting_models.BillingGroupExpenseTypeMap
