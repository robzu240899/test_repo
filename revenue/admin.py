from django import forms
from django.contrib import admin
from revenue.models import LaundryTransaction, Refund, RefundAuthorizationRequest, \
FailedTransactionMatch, FascardUser
from .enums import RefundChannelChoices


class RefundAuthorizationAdminForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super(RefundAuthorizationAdminForm, self).__init__(*args, **kwargs)
        obj = kwargs.get('instance')
        if obj:
            if not obj.refund_channel == RefundChannelChoices.CHECK:
                self.fields['check_recipient'].widget = forms.HiddenInput()
            if not obj.refund_channel == RefundChannelChoices.FASCARD_ADJUST:
                self.fields['additional_bonus_amount'].widget = forms.HiddenInput()
                self.fields['wipe_bonus_amount'].widget = forms.HiddenInput()
            if obj.approved: self.fields['rejected'].widget = forms.HiddenInput()
            if obj.rejected: self.fields['approved'].widget = forms.HiddenInput()
        #self.fields['check_recipient'].help_text = 'Only used on Check Refunds'

    def clean(self, *args, **kwargs):
        approved = self.cleaned_data.get('approved')
        rejected = self.cleaned_data.get('rejected')
        if approved and rejected:
            raise forms.ValidationError('Cannot approve and reject at the same time')
        #make sure that either relative duration or lease end date is specified
        #if no lease end date is specified make sure that either one from month and days is greater than zero
        return self.cleaned_data
    
    class Meta:
        labels ={
            'refund_amount' : 'Refund Amount $'
        }

class RefundAuthorizationAdmin(admin.ModelAdmin):
    form = RefundAuthorizationAdminForm
    readonly_fields = (
        'fascard_user',
        'get_machine',
        'created_by',
        'cashout_type',
        'charge_damage_to_landlord',
        'refund_type_choice',
        'transaction',
        'transaction__transaction_type',
        'transaction__trans_sub_type',
        'transaction__credit_card_amount',
        'transaction__cash_amount',
        'transaction__balance_amount',
        'transaction__loyalty_card_number',
        'transaction__additional_info',
        'transaction__local_transaction_time',
        'wait_for_settlement',
        'approved_by')
    exclude = (
        'aggregator_param',
    )
    list_display = [
        '__str__',
        'approved',
        'rejected',
        'timestamp'
    ]
    list_filter = ('approved',)
    # fields = (
    #     'approved',
    #     'approval_time',
    #     'description',
    #     'external_fascard_user_id',
    #     'fascard_user',
    #     'refund_type',
    #     'refund_amount',
    #     'wipe_bonus_amount',
    #     'additional_bonus_amount',
    #     'get_machine',
    #     'work_order_status',
    # )

    def transaction__transaction_type(self, instance):
        return instance.transaction.get_trans_type_verbose()

    def transaction__trans_sub_type(self, instance):
        return instance.transaction.get_trans_subtype_verbose()

    def transaction__credit_card_amount(self, instance):
        return instance.transaction.credit_card_amount

    def transaction__cash_amount(self, instance):
        return instance.transaction.cash_amount

    def transaction__balance_amount(self, instance):
        return instance.transaction.balance_amount

    def transaction__loyalty_card_number(self, instance):
        return instance.transaction.loyalty_card_number

    def transaction__additional_info(self, instance):
        return instance.transaction.additional_info

    def transaction__local_transaction_time(self, instance):
        return instance.transaction.local_transaction_time

    def get_machine(self, obj):
        return obj.transaction.machine
    get_machine.short_description = "Transaction's Machine"

    def save_model(self, request, obj, form, change):
        obj.approved_by = request.user
        super(RefundAuthorizationAdmin, self).save_model(request, obj, form, change)


class FascardUserAdmin(admin.ModelAdmin):
    search_fields = ('fascard_user_account_id', 'name')
    list_display = [
        '__str__',
        'name',
        'email_address',
        'fascard_user_account_id'
    ]

# Register your models here.
#admin.site.register(LaundryTransaction)
#admin.site.register(FascardUser, FascardUserAdmin)
admin.site.register(Refund)
admin.site.register(RefundAuthorizationRequest, RefundAuthorizationAdmin)
admin.site.register(FailedTransactionMatch)
