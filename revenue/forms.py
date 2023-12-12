from decimal import Decimal
from django import forms
from fascard.api import FascardApi
from roommanager.models import LaundryRoom, Slot
from upkeep.enums import WorkOrderStatus
from main.utils import CustomDateInput
from .enums import TransactionType, RefundWizardTxType, RefundChannelChoices, FascardBalanceType, TX_TYPE_CHOICES
from .models import LaundryTransaction, FascardUser, AuthorizeCustomerProfile


REFUND_CHANNEL_CHOICES = (
    ('authorize', 'Authorize.net CC Refund'),
    ('fascard_adjust', 'Fascard Balance Adjust'),
    ('check', 'Check')
)


def get_user_by_loyalty_card(loyalty_card_number):
    api = FascardApi(1)
    user_fascard_response = api.get_loyalty_account(loyalty_card_number)
    fascard_user_id = user_fascard_response.get('ID')
    if fascard_user_id:
        user = FascardUser.objects.filter(fascard_user_account_id=fascard_user_id).first()
    else:
        user = None
    return user

class CustomModelChoiceField(forms.ModelChoiceField):

    def label_from_instance(self, obj):
        return "{}".format(obj.fascard_record_id)

class CustomFascardUserChoiceField(forms.ModelChoiceField):

    def label_from_instance(self, obj):
        return "{} -- ({})".format(
            obj.fascard_user_account_id,
            obj.name)


class BaseRefundForm(forms.Form):
    laundry_room = forms.ModelChoiceField(
        queryset=LaundryRoom.objects.filter(is_active=True),
        required=False
    )
    transaction_type = forms.ChoiceField(choices=TX_TYPE_CHOICES, required=True)
    fascard_user_id = forms.IntegerField(required=False)
    loyalty_card_number = forms.IntegerField(required=False)
    start_date = forms.DateField(input_formats=['%m/%d/%Y'], required=False)
    end_date = forms.DateField(input_formats=['%m/%d/%Y'], required=False)

    def clean(self, *args, **kwargs):
        laundry_room = self.cleaned_data.get('laundry_room')
        transaction_type = int(self.cleaned_data.get('transaction_type'))
        fascard_user_id = self.cleaned_data.get('fascard_user_id')
        loyalty_card_number = self.cleaned_data.get('loyalty_card_number')
        if not any([laundry_room, transaction_type, fascard_user_id, loyalty_card_number]):
            raise forms.ValidationError(
                "Need at least one combinations of fields to filter"
            )
        if fascard_user_id:
            user = FascardUser.objects.filter(fascard_user_account_id=fascard_user_id)
            if not user:
                raise forms.ValidationError(
                "Invalid Fascard User ID"
            )
        if fascard_user_id and loyalty_card_number:
            raise forms.ValidationError(
                "Fascard User ID and Loyalty Card Number are mutually exclusive. Provide only one"
            )
        if transaction_type == RefundWizardTxType.DIRECT_VEND and not laundry_room:
            raise forms.ValidationError(
                "Laundry Room is required when processing a Direct Credit Card Vend Transaction"
            )


class LoyaltyRefundForm(forms.Form):
    #external_fascard_user_id = forms.IntegerField()
    fascard_user = CustomFascardUserChoiceField(
        queryset = FascardUser.objects.all(),
        required=True,
        widget=forms.Select(),
    )
    transaction_type = forms.ChoiceField(
        choices = (
            (TransactionType.VEND, 'Loyalty Machine Start'),
            (TransactionType.ADD_VALUE, 'Loyalty Value Add'))
    )

    def __init__(self, *args, **kwargs):
        super(LoyaltyRefundForm, self).__init__(*args, **kwargs)
        init_data = kwargs.get('initial', None)
        if init_data:
            q_payload = {}
            fascard_user = init_data.get('fascard_user')
            loyalty_card_number = init_data.get('loyalty_card_number')
            fascard_user_ids = []
            if fascard_user:
                fascard_user_ids.append(fascard_user.id)
            elif loyalty_card_number:
                user = get_user_by_loyalty_card(loyalty_card_number)
                if user: fascard_user_ids.append(user.id)            
            else:
                if init_data.get('start_date'):
                    q_payload['local_transaction_date__gte'] = init_data.get('start_date')
                if init_data.get('end_date'):
                    q_payload['local_transaction_date__lte'] = init_data.get('end_date')
                if init_data.get('room_id'):
                    q_payload['assigned_laundry_room_id'] = init_data.get('room_id')
                q_payload['fascard_user__isnull'] = False
                fascard_user_ids = LaundryTransaction.objects.filter(
                    **q_payload
                ).values_list('fascard_user').distinct()
            self.fields['fascard_user'].queryset = FascardUser.objects.filter(
                id__in=fascard_user_ids)


class CustomSlotModelChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        machine = Slot.get_current_machine(obj)
        if machine: machine = machine.asset_code
        return (f"{str(obj)} - (Machine: {machine})")


class DirectVendRefundForm(forms.Form):
    slot = CustomSlotModelChoiceField(
        queryset=Slot.objects.all(),
        required=False,
        help_text='Leave Blank to Include All'
    )

    def __init__(self, *args, **kwargs):
        super(DirectVendRefundForm, self).__init__(*args, **kwargs)
        init_data = kwargs.get('initial', None)
        if init_data:
            self.fields['slot'].queryset = Slot.objects.filter(
                laundry_room_id=init_data.get('room_id')
            )

class TransactionsSelect(forms.Form):
    transaction = CustomModelChoiceField(
        queryset = LaundryTransaction.objects.all(),
        required=False,
        widget=forms.Select(attrs={'id':'select_transactions'}),
        help_text = "Select Transactions' IDs to refund",
    )

    def __init__(self, *args, **kwargs):
        super(TransactionsSelect, self).__init__(*args, **kwargs)
        init_data = kwargs.get('initial', None)
        assert init_data
        payload = init_data.get('filter_payload')
        self.fields['transaction'].queryset = LaundryTransaction.objects.filter(**payload)


class ConfirmationForm(forms.Form):
    is_right = forms.BooleanField(label='Confirm the information is CORRECT')
    refund_channel = forms.ChoiceField(choices=REFUND_CHANNEL_CHOICES)
    description = forms.CharField(widget=forms.Textarea)
    fascard_user_id = forms.IntegerField(
        required = False,
        help_text = 'Leave Blank if Refund Channel is Authorize' 
    )
    bonus_wipe = forms.BooleanField(label='Wipe Bonus Amount', required = False)
    check_recipient = forms.CharField(required=False, help_text="Used ONLY for Check Refunds")
    check_recipient_address = forms.CharField(required=False, help_text="Used ONLY for Check Refunds")
    refund_amount = forms.DecimalField(decimal_places=2)
    additional_bonus_amount = forms.DecimalField(decimal_places=2, required=False)
    work_order_status = forms.ChoiceField(choices=WorkOrderStatus.CHOICES)

    def __init__(self, *args, **kwargs):
        super(ConfirmationForm, self).__init__(*args, **kwargs)
        init_data = kwargs.get('initial', None)
        assert init_data
        self.ask_fascard_id = init_data.get('ask_fascard_id')
        self.fields['refund_channel'].choices = init_data.get('channel_choices')
        if not init_data.get('ask_fascard_id'):
            #self.fields['fascard_account_id'].required = False
            self.fields['fascard_user_id'].widget = forms.HiddenInput()
        else:
            if not init_data.get('fascard_user_id') and init_data.get('loyalty_card_number'):
                user = get_user_by_loyalty_card(init_data.get('loyalty_card_number'))
                if user:
                    self.initial['fascard_user_id'] = user.fascard_user_account_id
        if not init_data.get('ask_bonus_wipe'):
            self.fields['bonus_wipe'].widget = forms.HiddenInput()
        if not RefundChannelChoices.CHECK_CHOICE in init_data.get('channel_choices'):
            self.fields['check_recipient'].widget = forms.HiddenInput()
            self.fields['check_recipient_address'].widget = forms.HiddenInput()
        
    def clean(self, *args, **kwargs):
        refund_channel = int(self.cleaned_data.get('refund_channel'))
        fascard_user_id = self.cleaned_data.get('fascard_user_id')
        if refund_channel == RefundChannelChoices.FASCARD_ADJUST:
            if self.ask_fascard_id and not fascard_user_id:
                raise forms.ValidationError('Fascard Adjust requires a Fascard Account ID')
        bonus_wipe = self.cleaned_data.get('bonus_wipe')
        additional_bonus_amount = self.cleaned_data.get('additional_bonus_amount')
        if all([bonus_wipe, additional_bonus_amount]):
            raise forms.ValidationError('Cannot Wipe Bonus and Add money to bonus at the same time')
        if additional_bonus_amount:
            if self.ask_fascard_id and not fascard_user_id:
                raise forms.ValidationError('Must provide Fascard account id when adding additional funds to Bonus')
            if additional_bonus_amount < Decimal("0.00") or additional_bonus_amount > Decimal("100.00"):
                raise forms.ValidationError('Invalid Additional Bonus Amount')


class CashOutForm(forms.Form):
    fascard_user_id = forms.IntegerField()
    cashout_amount = forms.DecimalField(max_digits=5, decimal_places=2)
    check_payee_name = forms.CharField()
    check_recipient_address = forms.CharField()
    description = forms.CharField(widget=forms.Textarea)
    cashout_balance_type = forms.ChoiceField(choices=FascardBalanceType.CHOICES)
 
    def clean(self, *args, **kwargs):
        fascard_user_id = self.cleaned_data.get('fascard_user_id')
        cashout_balance_type = self.cleaned_data.get('cashout_balance_type') #Balance or Bonus
        cashout_amount = self.cleaned_data.get('cashout_amount')
        try:
            fascard_api = FascardApi()
            user_info = fascard_api.get_user_account(user_account_id=fascard_user_id)[0]
        except Exception as e:
            raise forms.ValidationError(
                f"Couldn't get the user's {cashout_balance_type} from fascard: {e}"
            )
        current_balance_amount = user_info.get(cashout_balance_type)
        if not float(cashout_amount) <= float(current_balance_amount):
            raise forms.ValidationError(
                f"Cash out amount exceeds current {cashout_balance_type}: ${current_balance_amount}"
            )


class DamageRefundSlotField(forms.ModelChoiceField):

    def clean(self, value):
        return Slot.objects.get(id=value)


class DamageRefundForm(forms.Form):
    fascard_user_id = forms.IntegerField(required=False)
    refund_amount = forms.DecimalField(max_digits=5, decimal_places=2)
    check_payee_name = forms.CharField(required=False, help_text="Leave blank if refund channel is Fascard Balance Adjust")
    description = forms.CharField(widget=forms.Textarea)
    refund_channel = forms.ChoiceField(choices=(RefundChannelChoices.FASCARD_ADJUST_CHOICE, RefundChannelChoices.CHECK_CHOICE))
    charge_damage_to_landlord = forms.ChoiceField(
        choices = ((True, 'Yes'), (False, 'No')),
        required=False
    )
    force = forms.BooleanField(required=False, help_text="Check if you want to force the choice above, regardless of billing group configuration")
    laundry_room = forms.ModelChoiceField(queryset=LaundryRoom.objects.all())
    slot = DamageRefundSlotField(queryset=Slot.objects.all().values_list('id', flat=True), required=False)
    slot.widget.attrs.update({'hidden': True})

    def clean(self, *args, **kwargs):
        fascard_user_id = self.cleaned_data.get('fascard_user_id')
        check_payee_name = self.cleaned_data.get('check_payee_name') #Balance or Bonus
        refund_channel = self.cleaned_data.get('refund_channel')
        if refund_channel == RefundChannelChoices.FASCARD_ADJUST and not fascard_user_id:
            raise forms.ValidationError("A Fascard Balance Adjust requires a fascard user id")
        if refund_channel == RefundChannelChoices.CHECK and not check_payee_name:
            raise forms.ValidationError("A Check Refund requires a Check Payee Name")

class ManualTxIngestForm(forms.Form):
    action = forms.ChoiceField(choices=(('Run', 'Run Transaction Ingest'),))

class eCheckStart(forms.Form):
    loyalty_card_number = forms.IntegerField(required=False)


class eCheckSettings(forms.Form):
    name = forms.CharField()
    email_address = forms.EmailField() 
    balance_minimum_treshold = forms.DecimalField(decimal_places=2)
    balance_recharge = forms.DecimalField(decimal_places=2)

    def __init__(self, *args, **kwargs):
        super(eCheckSettings, self).__init__(*args, **kwargs)
        initial = kwargs.get('initial')
        fascard_user = initial.get('fascard_user')
        if not fascard_user:
            raise forms.ValidationError("Account not found")
        

class DownloadMachineRevenueForm(forms.Form):
    room = forms.ModelChoiceField(
        queryset=LaundryRoom.objects.filter(is_active=True),
        required=False
    )
    start_date = forms.DateField(widget=CustomDateInput)
    end_date = forms.DateField(widget=CustomDateInput)