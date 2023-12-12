import logging
from datetime import datetime, date
from dateutil.relativedelta import relativedelta
from decimal import Decimal
from itertools import groupby
from formtools.wizard.views import SessionWizardView
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum, F
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.template.response import TemplateResponse
from django.utils.decorators import method_decorator
from django.views.generic import DetailView, View
from main.utils import FieldExtractor
from queuehandler.views import NightlyRunEnqueue
from roommanager.models import Slot
from revenue.threads import OndemandTransactionReingest, MachineRevenueThread
from revenue.enums import TransactionType
#from .authorize import AuthorizeManager
from .enums import TransactionType, RefundWizardTxType, RefundChannelChoices
from .forms import BaseRefundForm, LoyaltyRefundForm, DirectVendRefundForm, TransactionsSelect, ConfirmationForm, \
get_user_by_loyalty_card, CashOutForm, DamageRefundForm, ManualTxIngestForm, DownloadMachineRevenueForm
from .models import LaundryTransaction, RefundAuthorizationRequest, FascardUser, AuthorizeCustomerProfile, eCheckSubscription
from .refund import BaseClassHandler
from .services import CashoutRefundManager, DamageRefundManager


logger = logging.getLogger(__name__)


class SpecialRefundBaseView(DetailView):
    @method_decorator(login_required)
    def get(self,request):
        form = self.form_class()
        return TemplateResponse(request, self.template_name, {'form': form})

    @method_decorator(login_required)
    @transaction.atomic
    def post(self, request, *args, **kwargs):
        """
        Creates a fake transaction for the cashout request 
        so that we can simply re-use current refund workflow.
        """
        context = self.kwargs
        form = self.form_class(request.POST)
        if form.is_valid():
            try:
                successful = self.service_class().send_for_approval(form.cleaned_data, request.user)
                context['msg'] = 'Sent for approval'
            except Exception as e:
                raise Exception(e)
                context['msg'] = f'Failed sending request for approval: {e}'
        context['form'] = form
        return TemplateResponse(request, self.template_name, context)


class CashoutView(SpecialRefundBaseView):
    form_class = CashOutForm
    template_name = "cash_out_form.html"
    service_class = CashoutRefundManager


class DamageRefundView(SpecialRefundBaseView):
    form_class = DamageRefundForm
    template_name = "damage_refund.html"
    service_class = DamageRefundManager


def ajax_get_room_slots(request):
    if request.method == 'GET':
        room_id = request.GET.get('laundry_room', None)
        slots = Slot.objects.filter(laundry_room_id=room_id)
        if room_id:
            return JsonResponse({'slots':[{'id': slot.id, 'name': str(slot)} if slot else dict() for slot in slots]}) 
    else:
        data = {
            'errMessage': 'Method is not GET'
        }
        return JsonResponse(data)


class ConditionManager:
    """
    Helper for TransactionRefundWizard
    """

    @classmethod
    def loyalty_refund_form(cls, wizard):
        cleaned_data = wizard.get_cleaned_data_for_step('base')
        if cleaned_data:
            tx_type = cleaned_data.get('transaction_type', None)
            return int(tx_type) == RefundWizardTxType.LOYALTY
        else:
            return False

    @classmethod
    def credit_card_refund(cls, wizard):
        cleaned_data = wizard.get_cleaned_data_for_step('base')
        if cleaned_data:
            tx_type = cleaned_data.get('transaction_type', None)
            return int(tx_type) == RefundWizardTxType.DIRECT_VEND
        else:
            return False

@method_decorator(login_required, 'dispatch')
class TransactionRefundWizard(SessionWizardView, LoginRequiredMixin):
    """
    For an undertanding of how each method gets called, refer to formtools documentation
    """
    form_list = [('base', BaseRefundForm), 
                 ('loyalty_refund_form', LoyaltyRefundForm),
                 ('credit_card_form', DirectVendRefundForm),
                 ('transactions_select', TransactionsSelect),
                 ('confirmation_step', ConfirmationForm)]
    condition_dict = {
        'loyalty_refund_form' : ConditionManager.loyalty_refund_form,
        'credit_card_form' : ConditionManager.credit_card_refund
    }
    template_name  = 'tx_refund_wizard.html'
    refund_approval_fields = (
        'refund_channel',
        'created_by',
        'description',
        'refund_amount',
        'external_fascard_user_id',
        'aggregator_param',
        'wipe_bonus_amount',
        'transaction',
        'additional_bonus_amount',
        'work_order_status',
        'check_recipient',
        'check_recipient_address'
    )

    def process_step(self, form):
        if isinstance(form, BaseRefundForm):
            base_data = self.get_form_step_data(form)
            end_date = base_data.get('base-end_date')
            if end_date:
                date_obj = datetime.strptime(end_date, "%m/%d/%Y")
                latest_tx = LaundryTransaction.objects.all().order_by('-id').first()
                if latest_tx.local_transaction_date and date_obj.date() >= latest_tx.local_transaction_date:
                    OndemandTransactionReingest(match=True).start()
        return self.get_form_step_data(form)


    def create_approval_request(self):
        """
        Every refund attempt is saved and queued for later approval in the admin dashboard
        """
        d = {}
        fields = self.refund_approval_fields
        for f in fields:
            d[f] = getattr(self, f, None)
        obj = RefundAuthorizationRequest.objects.create(**d)
        #obj.transactions.add(self.transaction)
        if self.refund_channel == RefundChannelChoices.AUTHORIZE:
            if self.transaction.assigned_local_transaction_time.date() == date.today():
                obj.wait_for_settlement = True
        obj.save()
        return obj
        
    def get_final_queryset(self):
        assert hasattr(self, 'filter_payload')
        return LaundryTransaction.objects.filter(**self.filter_payload)

    def get_refund_amount(self, tx, loyalty_data=None, credit_card_data=None, ignore_previous=False):
        if loyalty_data is None:
            loyalty_data = self.get_cleaned_data_for_step('loyalty_refund_form')
        if credit_card_data is None:
            credit_card_data = self.get_cleaned_data_for_step('credit_card_form')
        amount_field = None
        if loyalty_data:
            loyalty_tx_type = loyalty_data.get('transaction_type')
            amount_field = 'balance_amount'
            if int(loyalty_tx_type) == TransactionType.VEND: amount_field = 'credit_card_amount,balance_amount,bonus_amount'
        elif credit_card_data:
            amount_field = 'credit_card_amount'
        # result = txs.aggregate(
        #         total_result = amount_field
        #     )
        available_for_refund = BaseClassHandler.get_available_for_refunding(tx, amount_field.split(','))
        if not ignore_previous:
            previous_refunds = Decimal(BaseClassHandler.get_total_refunds(tx))
            available_for_refund = available_for_refund - previous_refunds
        return available_for_refund

    def get_form_initial(self, step):
        if step == 'credit_card_form':
            base_data = self.get_cleaned_data_for_step('base')
            room = base_data.get('laundry_room')
            return {
                'room_id' : getattr(room, 'id', None)
            }
        
        if step == 'loyalty_refund_form':
            base_data = self.get_cleaned_data_for_step('base')
            room = base_data.get('laundry_room')
            if base_data.get('fascard_user_id'):
                fascard_user = FascardUser.objects.get(fascard_user_account_id=base_data.get('fascard_user_id'))
            else:
                fascard_user = None
            return {
                'room_id' : getattr(room, 'id', None), 
                'start_date' : base_data.get('start_date'),
                'end_date' : base_data.get('end_date'),
                'fascard_user' : fascard_user,
                'loyalty_card_number' : base_data.get('loyalty_card_number')
            }

        if step == 'transactions_select':
            base_data = self.get_cleaned_data_for_step('base')
            loyalty_data = self.get_cleaned_data_for_step('loyalty_refund_form')
            credit_card_data = self.get_cleaned_data_for_step('credit_card_form')
            laundry_room = base_data.get('laundry_room')
            self.filter_payload = {'is_refunded' : False,}
            if laundry_room:
                self.filter_payload['assigned_laundry_room_id'] = laundry_room.id,
            if base_data.get('start_date'):
                self.filter_payload['local_transaction_date__gte'] = base_data.get('start_date')
            if base_data.get('end_date'):
                self.filter_payload['local_transaction_date__lte'] = base_data.get('end_date')
            if loyalty_data:
                loyalty_tx_type = loyalty_data.get('transaction_type')
                fascard_user = loyalty_data.get('fascard_user')
                filter_payload = {
                    'external_fascard_user_id' : getattr(fascard_user, 'fascard_user_account_id'),
                    'transaction_type' : loyalty_tx_type
                }
                filter_payload['balance_amount__gt'] = 0
                #if int(loyalty_tx_type) == TransactionType.VEND:
                #    filter_payload['credit_card_amount'] = 0
                #NOTE: Above is commented out since now we are taking the summation of all money columns for a vend loyalty transaction
                #as the maximun amount available for refunding
                self.filter_payload.update(filter_payload)
            elif credit_card_data:
                slot = credit_card_data.get('slot')
                #one_day_ago = date.today() - relativedelta(day=1)
                if slot:
                    self.filter_payload['slot'] = slot
                self.filter_payload['credit_card_amount__gt'] = 0
                self.filter_payload['transaction_type'] = TransactionType.VEND
                current_end_date = self.filter_payload.get('local_transaction_date__lte', None)
                #if not current_end_date or current_end_date > one_day_ago:
                #    self.filter_payload['local_transaction_date__lte'] = one_day_ago
            return {'filter_payload' : self.filter_payload}

        if step == 'confirmation_step':
            base_data = self.get_cleaned_data_for_step('base')
            fascard_user_id = base_data.get('fascard_user_id')
            loyalty_card_number = base_data.get('loyalty_card_number')
            tx_type = base_data.get('transaction_type')
            ask_fascard_id = False
            ask_bonus_wipe = False
            fascard_user_name = None
            if int(tx_type) == RefundWizardTxType.LOYALTY:
                ask_bonus_wipe = True
                loyalty_data = self.get_cleaned_data_for_step('loyalty_refund_form')
                fascard_user = loyalty_data.get('fascard_user')
                if not fascard_user_id:
                    fascard_user_id = fascard_user.fascard_user_account_id
                fascard_user_name = getattr(fascard_user, 'name', '')
                loyalty_tx_type = int(loyalty_data.get('transaction_type'))
                if loyalty_tx_type == TransactionType.ADD_VALUE:
                    channel_choices = (
                        RefundChannelChoices.AUTHORIZE_CHOICE,
                        RefundChannelChoices.CHECK_CHOICE
                    )
                elif loyalty_tx_type == TransactionType.VEND:
                    channel_choices = (RefundChannelChoices.FASCARD_ADJUST_CHOICE,)
            elif int(tx_type) == RefundWizardTxType.DIRECT_VEND:
                ask_fascard_id = True
                channel_choices = RefundChannelChoices.DIRECT_VEND_CHOICES                    
            loyalty_data = self.get_cleaned_data_for_step('loyalty_refund_form')
            credit_card_data = self.get_cleaned_data_for_step('credit_card_form')
            selected_transactions = self.get_cleaned_data_for_step('transactions_select')
            tx = selected_transactions.get('transaction')
            result = self.get_refund_amount(tx, loyalty_data=loyalty_data, credit_card_data=credit_card_data)
            return {
                'channel_choices' : channel_choices, 
                'ask_fascard_id' : ask_fascard_id,
                'ask_bonus_wipe' : ask_bonus_wipe,
                'refund_amount' : result,
                'check_recipient' : fascard_user_name,
                'fascard_user_id' : fascard_user_id,
                'loyalty_card_number' : loyalty_card_number
            }

    def get_context_data(self, form, **kwargs):
        context = super().get_context_data(form=form, **kwargs)
        if self.steps.current == 'transactions_select':
            prev = self.get_prev_step(self.steps.current)
            prev_data = self.get_cleaned_data_for_step(prev)
            context['final_queryset'] = self.get_final_queryset()
            context['prev_data'] = prev_data
        if self.steps.current == 'confirmation_step':
            selected_transactions = self.get_cleaned_data_for_step('transactions_select')
            loyalty_data = self.get_cleaned_data_for_step('loyalty_refund_form')
            credit_card_data = self.get_cleaned_data_for_step('credit_card_form')
            tx = selected_transactions.get('transaction')
            if loyalty_data:
                fascard_user = loyalty_data.get('fascard_user')
                external_fascard_user_id = getattr(fascard_user, 'fascard_user_account_id')
                name = fascard_user.name or 'Unknwon'
                email = fascard_user.email_address or 'Unknown'
                context.update(
                    {
                        'user_name' : name,
                        'user_email' : email,
                        'location' : tx.assigned_laundry_room,
                        'account_id' : external_fascard_user_id,
                        'transaction_credit_card_amount' : tx.credit_card_amount,
                        'transaction_bonus_amount' : tx.bonus_amount,
                        'transaction_balance_amount' : tx.balance_amount
                    }
                )
                loyalty_tx_type = int(loyalty_data.get('transaction_type'))
                if loyalty_tx_type == TransactionType.ADD_VALUE:
                    context.update({'last_four' : tx.last_four, 'dirty_name' : tx.dirty_name})
            elif credit_card_data:
                #context_fields = ('last_four', 'dirty_name', 'fascard_user__name', 'fascard_user')
                #context['tx'] = FieldExtractor.extract_fields(context_fields, tx)
                context['tx'] = tx
            context['original_amount'] = self.get_refund_amount(
                tx,
                loyalty_data=loyalty_data,
                credit_card_data=credit_card_data,
                ignore_previous=True)
            all_refunds = tx.refunds.all()
            context['all_refunds'] = all_refunds
            result = self.get_refund_amount(tx, loyalty_data=loyalty_data, credit_card_data=credit_card_data)
            context['total_refund'] = result
        return context

    def done(self, *args, **kwargs):
        """
        populates current instance with data for fields described in class attr refund_approval_fields
        """
        transactions_step = kwargs['form_dict']['transactions_select']
        confirmation = kwargs['form_dict']['confirmation_step']
        loyalty_data = self.get_cleaned_data_for_step('loyalty_refund_form')
        credit_card_data = self.get_cleaned_data_for_step('credit_card_form')
        self.transaction = transactions_step.cleaned_data.get('transaction')
        refund_channel = int(confirmation.cleaned_data.get('refund_channel'))
        custom_refund_amount = confirmation.cleaned_data.get('refund_amount')
        self.wipe_bonus_amount = confirmation.cleaned_data.get('bonus_wipe')
        refunded = False
        err_msg = None
        self.refund_channel = refund_channel
        if loyalty_data:
            refund_obj = False
            fascard_user = loyalty_data.get('fascard_user')
            self.external_fascard_user_id = getattr(fascard_user, 'fascard_user_account_id')
            loyalty_tx_type = loyalty_data.get('transaction_type')
            self.aggregator_param = 'balance_amount'
            if int(loyalty_tx_type) == TransactionType.VEND: self.aggregator_param = 'credit_card_amount,balance_amount,bonus_amount'
        elif credit_card_data:
            self.external_fascard_user_id = confirmation.cleaned_data.get('fascard_user_id')
            self.aggregator_param = 'credit_card_amount'
        #tx_amount = getattr(self.transaction, self.aggregator_param)
        tx_amount = BaseClassHandler.get_available_for_refunding(self.transaction, self.aggregator_param.split(','))
        if custom_refund_amount:
            if custom_refund_amount > tx_amount: return HttpResponse("The refund amount cannot exceed the transaction value")
            self.refund_amount = Decimal(custom_refund_amount)
        else:
            self.refund_amount = tx_amount
        all_refunds = BaseClassHandler.get_total_refunds(self.transaction)
        all_refunds = Decimal(all_refunds)
        if (all_refunds + self.refund_amount) > Decimal(tx_amount): return HttpResponse("Total Refunds Exceed Max amount in Transaction")
        self.description = confirmation.cleaned_data.get('description')
        self.check_recipient = confirmation.cleaned_data.get('check_recipient')
        self.check_recipient_address = confirmation.cleaned_data.get('check_recipient_address')
        self.additional_bonus_amount = confirmation.cleaned_data.get('additional_bonus_amount')
        self.work_order_status = confirmation.cleaned_data.get('work_order_status')
        self.created_by = self.request.user
        r = self.create_approval_request()
        if err_msg:
            return HttpResponse("Error: {}".format(err_msg))
        if r:
            return HttpResponse("Sucessful Refund Request. Waiting for approval")
        else:
            return HttpResponse("Wrong Request")



# #TODO: Add login required mixin
# class ListTransactions(View):
#     form_class = BaseRefundForm

# #    def get(self, request, *args, **kwargs):


#     def post(self, request, *args, **kwargs):
#         form = self.form_class(request.POST)
#         if form.is_valid():
#             laundry_room = form.cleaned_data.get('laundry_room')
#             transaction_type = form.cleaned_data.get('transaction_type')
#             if 
#                 #first step
#                 new_form = self.form_class(laundry_room=laundry_room, activate_extra_fields=True)
#             else:
#                 #second step - all fielfs filled
#                 tx_query = LaundryTransaction.objects.filter(
#                     transaction_type = form.cleaned_data.get('transaction_type')
#                 )
#                 payment_type = form.cleaned_data.get('payment_type')
#                 activity_type = form.cleaned_data.get('activity_type')

class Transaction(View):
    
    @method_decorator(login_required)
    def get(self,request):
        return render(request, "transaction/index.html")


class ManualTransactionIngest(View):
    template_name = "manual_tx_ingest.html"
    form_class = ManualTxIngestForm

    @method_decorator(login_required)
    def get(self,request):
        form = self.form_class()
        return TemplateResponse(request, self.template_name, {'form': form})

    @method_decorator(login_required)
    def post(self, request, *args, **kwargs):
        context = self.kwargs
        form = self.form_class(request.POST)
        if form.is_valid():
            try:
                NightlyRunEnqueue._enqueue(**{'jobname':'tiedrun','stepstorun':'transaction_ingest,match'})
                context['msg'] = 'Enqueued Ingest'
            except Exception as e:
                context['msg'] = f'Failed enqueing transactions ingest: {e}'
        context['form'] = form
        return TemplateResponse(request, self.template_name, context)
    

class DownloadMachineRevenueView(View):
    TEMPLATE_NAME = 'download_revenue_data.html'

    @method_decorator(login_required)
    def get(self,request):
        msg = ""
        form = DownloadMachineRevenueForm()
        return render(request,self.TEMPLATE_NAME, {'msg':msg,'form':form})

    @method_decorator(login_required)
    def post(self,request):
        form = DownloadMachineRevenueForm(request.POST)
        to_email = request.user.email
        if form.is_valid(): 
            MachineRevenueThread(
                form.cleaned_data.get('room'),
                form.cleaned_data.get('start_date'),
                form.cleaned_data.get('end_date'),
                to_email
            ).start()
            msg = 'The report will be delivered via email'
        else:
            msg = "Please correct errors in the form."
        return render(request,self.TEMPLATE_NAME, {'msg':msg,'form':form})




# class eCheckForm(View):     

#     @method_decorator(login_required)
#     def get(self,request):
#         merchantAuth = apicontractsv1.merchantAuthenticationType()
#         #name, key ().get_crendentials()
#         merchantAuth.name = name
#         merchantAuth.transactionKey = key

#         # setting1 = apicontractsv1.settingType()
#         # setting1.settingName = apicontractsv1.settingNameEnum.hostedPaymentButtonOptions
#         # setting1.settingValue = "{\"text\": \"Pay\"}"

#         # setting2 = apicontractsv1.settingType()
#         # setting2.settingName = apicontractsv1.settingNameEnum.hostedPaymentOrderOptions
#         # setting2.settingValue = "{\"show\": false}"

#         # settings = apicontractsv1.ArrayOfSetting()
#         # settings.setting.append(setting1)
#         # settings.setting.append(setting2)

#         # transactionrequest = apicontractsv1.transactionRequestType()
#         # transactionrequest.transactionType = "authCaptureTransaction"
#         # transactionrequest.amount = Decimal(15)

#         # transactionrequest.profile = "1930157012"

#         # paymentPageRequest = apicontractsv1.getHostedPaymentPageRequest()
#         # paymentPageRequest.merchantAuthentication = merchantAuth
#         # paymentPageRequest.transactionRequest = transactionrequest
#         # paymentPageRequest.hostedPaymentSettings = settings

#         # paymentPageController = getHostedPaymentPageController(paymentPageRequest)

#         # paymentPageController.execute()

#         # paymentPageResponse = paymentPageController.getresponse()
#         setting = apicontractsv1.settingType()
#         setting.settingName = apicontractsv1.settingNameEnum.hostedProfileReturnUrl
#         setting.settingValue = "https://returnurl.com/return/"

#         settings = apicontractsv1.ArrayOfSetting()
#         settings.setting.append(setting)

#         profilePageRequest = apicontractsv1.getHostedProfilePageRequest()
#         profilePageRequest.merchantAuthentication = merchantAuth
#         profilePageRequest.customerProfileId = '1930157012'
#         profilePageRequest.hostedProfileSettings = settings

#         profilePageController = getHostedProfilePageController(profilePageRequest)

#         profilePageController.execute()

#         profilePageResponse = profilePageController.getresponse()

#         if profilePageResponse is not None:
#             if profilePageResponse.messages.resultCode == apicontractsv1.messageTypeEnum.Ok:
#                 print('Successfully got hosted profile page!')

#                 print('Token : %s' % profilePageResponse.token)

#                 if profilePageResponse.messages:
#                     print('Message Code : %s' % profilePageResponse.messages.message[0]['code'].text)
#                     print('Message Text : %s' % profilePageResponse.messages.message[0]['text'].text)
#             else:
#                 if profilePageResponse.messages:
#                     print('Failed to get batch statistics.\nCode:%s \nText:%s' % (profilePageResponse.messages.message[0]['code'].text,profilePageResponse.messages.message[0]['text'].text)) 

#         msg = ''
#         context = {}
#         if profilePageResponse is not None:
#             if profilePageResponse.messages.resultCode == apicontractsv1.messageTypeEnum.Ok:
#                 print('Successfully got hosted payment page!')
#                 print('Token : %s' % profilePageResponse.token)
#                 context['token'] = profilePageResponse.token
#             else:
#                 if profilePageResponse.messages is not None:
#                     msg = 'Failed to get token.\nCode:%s \nText:%s' % (profilePageResponse.messages.message[0]['code'].text,profilePageResponse.messages.message[0]['text'].text)
#         context['msg'] = msg
#         return render(request,"echeck_form.html", context)


# @method_decorator(login_required, 'dispatch')
# class eCheckWizard(SessionWizardView, LoginRequiredMixin):
#     form_list = [
#         ('base', eCheckStart),
#         ('settings', eCheckSettings),
#     ]

#     def get_form_initial(self, step):
#         if step == 'settings':
#             base_data = self.get_cleaned_data_for_step('base')
#             loyalty_card_number = base_data.get('loyalty_card_number')
#             print (f"Loyalty: {loyalty_card_number}")
#             self.fascard_user = get_user_by_loyalty_card(loyalty_card_number)
#             print (f"Fascard user: {self.fascard_user}")
#             data = {}
#             if self.fascard_user:
#                 fields = ['name', 'email_address']
#                 for field in fields:
#                     if getattr(self.fascard_user, field):
#                         data[field] = getattr(self.fascard_user, field)
#                 data['fascard_user'] = self.fascard_user
#             print (f"initializing settings with data: {data}")
#             return data

#     def done(self, *args, **kwargs):
#         base_data = self.get_cleaned_data_for_step('base')
#         settings_data = self.get_cleaned_data_for_step('settings')
#         loyalty_card_number = base_data.get('loyalty_card_number')
#         try:
#             profile = AuthorizeCustomerProfile.objects.filter(
#                 loyalty_card_number=loyalty_card_number).order_by('-timestamp').first()
#             customer_id = profile.authorize_customer_id
#         except:
#             #TODO Create profile on Authorize and fetch customer id.
#             customer_profile_payload = {
#                 'id' : str(loyalty_card_number),
#                 'name' : settings_data.get('name'),
#                 'email' : settings_data.get('email_address')
#             }
#             try:
#                 customer_id = AuthorizeManager().create_customer_profile(customer_profile_payload)
#             except Exception as e:
#                 return HttpResponse(
#                     'Could not create a customer profile for you on Authorize.\
#                     Please contact our customer support. Exception: {}'.format(e))
#             profile = AuthorizeCustomerProfile.objects.create(
#                 loyalty_card_number = loyalty_card_number,
#                 fascard_user = self.fascard_user,
#                 authorize_customer_id = customer_id
#             )
#         eCheckSubscription.objects.create(
#             customer_profile = profile,
#             balance_minimum_treshold = settings_data.get('balance_minimum_treshold'),
#             balance_recharge = settings_data.get('balance_recharge')
#         )
#         customer_authorize_form_context = AuthorizeManager().get_accepted_customer_profile_page(customer_id)
#         return render(self.request,"echeck_form.html", customer_authorize_form_context)

#         #TODO Need to integrate the form as an iframe/lightbox so that we can get a response
#         #back from authorize with the ID of the customer's payment profile just created.
#         #we need to store this id so that we charge this customerpaymentprofile 
