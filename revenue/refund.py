#from authorizenet.apicontrollers import *
import logging
import os, sys
from decimal import *
from authorizenet import apicontractsv1
from authorizenet.apicontrollers import *
from authorizenet.constants import *
from datetime import datetime
from decimal import Decimal
from io import BytesIO
from zipfile import ZipFile
from django.conf import settings
from django.core.mail import EmailMessage
from django.core.files.base import ContentFile
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum
from django.template.loader import render_to_string, get_template
from fascard.api import FascardApi
from fascard.refunds import RefundBrowser
from main.decorators import ProductionCheck
from main.utils import SecretManager
from .enums import RefundChannelChoices, TransactionType
from .exceptions import BalanceChangedException, TotalBalanceExceeded


logger = logging.getLogger(__name__)


class InvalidAmountException(Exception):
    pass


class BaseClassHandler():

    def refund(self):
        raise NotImplementedError

    @classmethod
    def get_total_refunds(cls, transaction):
        all_refunds = transaction.refunds.all()
        total_q = all_refunds.values('amount').aggregate(result=Sum('amount'))
        return total_q.get('result') or 0

    def _email_failure(self, subject: str="[ALERT] Failed Refund", err_msg='Refund Failed', html=False):
        recipient = [self.refund_request.created_by.email] + settings.IT_EMAIL_LIST
        message = EmailMessage(
            subject = subject,
            body = err_msg,
            to = recipient,
        )
        if html: message.content_subtype = "html"
        message.send()
        return True

    @classmethod
    def get_available_for_refunding(cls, tx, agg_params: list) -> Decimal:
        total = Decimal(0)
        for agg_param in agg_params: total += getattr(tx, agg_param)
        return total

    def save_refund(self):
        from .models import Refund
        self.fascard_user_id = self.refund_request.external_fascard_user_id
        tx =  self.refund_request.transaction
        if not self.fascard_user_id: self.fascard_user_id = getattr(tx, 'external_fascard_user_id')
        tx_state = Decimal(self.get_total_refunds(tx))
        total_available_for_refund = self.get_available_for_refunding(self.refund_request.transaction, self.refund_request.aggregator_param.split(','))
        refund = Decimal(self.refund_request.refund_amount)
        if (tx_state + refund) > total_available_for_refund: raise TotalBalanceExceeded(tx_state, refund, total_available_for_refund)
        try:
            refund_obj = Refund.objects.create(
                amount = self.refund_request.refund_amount,
                refund_channel = self.REFUND_TYPE,
                transaction = self.refund_request.transaction,
                fascard_user_account_id = self.fascard_user_id,
                authorization_request = self.refund_request
            )
            tx_state = Decimal(self.get_total_refunds(tx))
            if tx_state == total_available_for_refund:
                tx.is_refunded = True
                tx.save()
            return refund_obj
        #TODO add invalidamount except
        #except 
        except Exception as e:
            raise Exception(e)


class AuthorizeDotNetRefund(BaseClassHandler):
    #Sandbox creds: 9Nz9x8w2C63, 6f2Ja94ukC3hNk2s
    SANDBOX_API_LOGIN = SecretManager('LaundrySystem/AUTHORIZE_SANDBOX_LOGIN').get_secret_value()
    SANDBOX_KEY = SecretManager('LaundrySystem/AUTHORIZE_SANDBOX_KEY').get_secret_value()
    API_LOGIN_ID = SecretManager('LaundrySystem/AUTHORIZE_PROD_LOGIN').get_secret_value()
    TRANSACTION_KEY = SecretManager('LaundrySystem/AUTHORIZE_PROD_KEY').get_secret_value()
    SECRET_KEY = 'Simon'
    TRANSACTION_TYPE = 'refundTransaction'
    REFUND_TYPE = RefundChannelChoices.AUTHORIZE
    FAILED_CAPTURE_TX = 'failed_capture_transaction.html'
    #API_LOGIN_ID = '2j6xG8Ta'
    #TRANSACTION_KEY = '6Z5QJ595d8dkr7D6'
    #SECRET_KEY = '2D0530EB0E0B7BD39A9A05570DC03754DDD4956DBD99CA3DF93BE6261766AE999C0C141A82BBEE0EF7C69BB955CD365E00E8AC9CF2E1336E669FC0283D01CC29'

    def get_crendentials(self):
        if settings.IS_PRODUCTION:
            return (self.API_LOGIN_ID, self.TRANSACTION_KEY)
        else:
            return (self.SANDBOX_API_LOGIN, self.SANDBOX_KEY)

    def _report_capture_failure(self) -> bool:
        """
        If an Authorize parent transaction for the transaction being refunded was not found, send an email
        notification to the users involved
        """
        to = settings.IT_EMAIL_LIST.copy()
        if getattr(self.refund_request.created_by, 'email', None):
            to.append(self.refund_request.created_by.email)
        if getattr(self.refund_request.approved_by, 'email', None):
            to.append(self.refund_request.approved_by.email)
        rendered = render_to_string('failed_capture_transaction.html', {'refund_request' : self.refund_request})
        message = EmailMessage(
            subject = '[ALERT] An Authorize.net refund was not completed',
            body = rendered,
            to = to,
        )
        message.content_subtype = "html"
        message.send(fail_silently=False)
        return True

    @ProductionCheck
    def refund(self, refund_request):
        self.refund_request = refund_request
        if getattr(self.refund_request, 'refund_object', None):
            if self.refund_request.refund_object.refund_completed:
                return self.refund_request.refund_object
        tx = self.refund_request.transaction
        if not getattr(tx, 'credit_card_amount') > 0:
            raise Exception(
                'You are trying to refund via Authorize.net a transaction where credit_card_amount is Zero'
            )
        assert tx.is_refunded is False
        #assert getattr(tx, 'transaction_type') == TransactionType.VEND
        merchantAuth = apicontractsv1.merchantAuthenticationType()
        creds = self.get_crendentials()
        merchantAuth.name = creds[0]
        merchantAuth.transactionKey = creds[1]

        creditCard = apicontractsv1.creditCardType()
        creditCard.cardNumber = getattr(tx, 'last_four')
        creditCard.expirationDate = "XXXX"

        payment = apicontractsv1.paymentType()
        payment.creditCard = creditCard

        transactionrequest = apicontractsv1.transactionRequestType()
        transactionrequest.retail = apicontractsv1.transRetailInfoType()
        transactionrequest.retail.marketType = '2'
        transactionrequest.retail.deviceType = '2'
        transactionrequest.transactionType = "refundTransaction"
        #transactionrequest.amount = Decimal ('2.55')
        logger.info(f"Started processing refund to credit card: {getattr(tx, 'last_four')}", exc_info=True)
        
        #self.amount_refunded = getattr(tx, 'credit_card_amount')
        self.amount_refunded = self.refund_request.refund_amount
        self.fascard_user_id = getattr(self.refund_request.transaction, 'external_fascard_user_id')
        self.aggregator_param = 'credit_card_amount'
        transactionrequest.amount = self.amount_refunded
        #set refTransId to transId of a settled transaction
        capture_tx = self.refund_request._get_capture_transaction()
        if not capture_tx:
            self._report_capture_failure()
            msg = f"""The system could not find a parent Authorize transaction for the transaction
            with RefundAuthorization request ID: {self.refund_request.id}"""
            raise Exception(msg)
        authorize_id = capture_tx.additional_info.split('/')[0]
        transactionrequest.refTransId =str(authorize_id)
        transactionrequest.payment = payment

        createtransactionrequest = apicontractsv1.createTransactionRequest()

        createtransactionrequest.merchantAuthentication = merchantAuth
        createtransactionrequest.refId = getattr(tx, 'external_fascard_id')
        #createtransactionrequest.refId = "MerchantID-0001"

        createtransactionrequest.transactionRequest = transactionrequest
        createtransactioncontroller = createTransactionController(createtransactionrequest)
        createtransactioncontroller.setenvironment(constants.PRODUCTION)
        createtransactioncontroller.execute()

        err_str = f'Failed Refund. Refund Auth Request(ID: {self.refund_request.id})'
        try:
            with transaction.atomic():
                refund_obj = self.save_refund()
                response = createtransactioncontroller.getresponse()
                if response is not None:
                    if response.messages.resultCode == "Ok":
                        if hasattr(response.transactionResponse, 'messages') == True:
                            refund_obj.refund_completed = True
                            refund_obj.save()
                            logger.info("Sucessfully Refunded Transaction: {}".format(tx.fascard_record_id))
                            return refund_obj
                        else:
                            if hasattr(response.transactionResponse, 'errors') == True:
                                err_str += 'Error Code:  %s' % str(response.transactionResponse.errors.error[0].errorCode)
                                err_str += 'Error message: %s' % response.transactionResponse.errors.error[0].errorText
                            logger.error(err_str, exc_info=True)
                            self._email_failure(err_str)
                            raise Exception(err_str)
                    else:
                        err_str = f'Failed Refund Request. Refund Auth Request(ID: {self.refund_request.id})'
                        if hasattr(response, 'transactionResponse') == True and hasattr(response.transactionResponse, 'errors') == True:
                            err_str += 'Error Code: %s' % str(response.transactionResponse.errors.error[0].errorCode)
                            err_str += 'Error message: %s' % response.transactionResponse.errors.error[0].errorText
                        else:
                            err_str += 'Error Code: %s' % response.messages.message[0]['code'].text
                            err_str += 'Error message: %s' % response.messages.message[0]['text'].text
                        logger.error(err_str, exc_info=True)
                        self._email_failure(err_str)
                        raise Exception(err_str)
                else:
                    raise Exception('Null Response.')
        except Exception as e:
            logger.error(err_str, exc_info=True)
            url = f"http://system.aceslaundry.com/admin/revenue/refundauthorizationrequest/{self.refund_request.id}/change/"
            error_msg = """<html><body><p>Exception: %s</p>. Link to RefundRequest: <a href='%s'>Refund Authorization Request</a> </body></html>""" % (str(e), url)
            self._email_failure(err_msg=error_msg, html=True)
            raise Exception(e)


class FascardRefund(BaseClassHandler):
    LAUNDRY_GROUP_ID = 1
    REFUND_TYPE = RefundChannelChoices.FASCARD_ADJUST
    
    #@ProductionCheck
    @transaction.atomic()
    def refund(self, refund_request):
        self.refund_request = refund_request
        if self.refund_request.transaction.is_refunded:
            return True
        refund_obj = self.save_refund()
        api = FascardApi(self.LAUNDRY_GROUP_ID)
        fascard_user_id = self.refund_request.external_fascard_user_id
        if not fascard_user_id:
            fascard_user_id = getattr(self.refund_request.transaction, 'external_fascard_user_id')
        payload = {
            "Bonus" : str(self.refund_request.refund_amount),
            "TransType" : 3,
            "TransSubType" : 3,
            "AdditionalInfo" : refund_obj.authorization_request.description
        }
        try:
            response = api.refund_loyalty_account(fascard_user_id, payload)
            if response:
                refund_obj.refund_completed = True
                refund_obj.save()
        except Exception as e:
            err_msg = f'Error refunding refund auth request with id: {self.refund_request.id}: {e}'
            logger.error(err_msg, exc_info=True)
            self._email_failure(err_msg)
            raise Exception(e)
        return refund_obj


class CheckRefund(BaseClassHandler):
    REFUND_TYPE = RefundChannelChoices.CHECK
    LAUNDRY_GROUP_ID = 1

    def __init__(self):
        self.fascard_api = fascard_api = FascardApi()

    def _get_user_info(self):
        return self.fascard_api.get_user_account(user_account_id=self.refund_request.external_fascard_user_id)[0]

    def _check_current_balance(self):
        user_info = self._get_user_info()
        current_balance = user_info.get(self.refund_request.cashout_type)
        if current_balance < self.refund_request.refund_amount:
            msg = f"The user's {self.refund_request.cashout_type} changed and this request is no longer valid. \n"
            msg += f'Requested cash-out: {self.refund_request.refund_amount}. Current Balance : {current_balance}'
            body = render_to_string("failed_refund_approval.html", {'msg': msg, 'refund_request': self.refund_request})
            self._email_failure(subject = 'Failed refund request approval', err_msg = body, html=True)
            raise BalanceChangedException(self.refund_request.cashout_type)
        return current_balance

    def _pre_process(self):
        if int(self.refund_request.transaction.transaction_type) == TransactionType.CASHOUT_REQUEST:
            self._check_current_balance()

    def _post_process(self):
        if int(self.refund_request.transaction.transaction_type) == TransactionType.CASHOUT_REQUEST:
            current_balance = self._check_current_balance()
            new_balance_value = Decimal(current_balance) - Decimal(self.refund_request.refund_amount)
            payload = {
                self.refund_request.cashout_type : str(new_balance_value),
                "SetExactValue" : True,
                "TransType" : 3,
                "TransSubType" : 0, #NOTE: Since we can't mark it as 3, let's leave it as 0
                "AdditionalInfo" : self.refund_request.description
            }
            self.fascard_api.refund_loyalty_account(self.refund_request.external_fascard_user_id, payload)

    def generate_check(self):
        tx = self.refund_request.transaction
        room = tx.assigned_laundry_room or tx.laundry_room
        bg = room.get_billing_group() if room else None
        payee = ''
        if getattr(tx, 'loyalty_card_number'):
            user = getattr(tx, 'fascard_user')
            if user and getattr(user, 'name'):
                payee = getattr(user, 'name')
        elif getattr(tx, 'last_four'):
            payee = getattr(tx, 'dirty_name')
        elif self.refund_request.check_recipient:
            payee = self.refund_request.check_recipient
        purpose =  ['Laundry refund for']
        if int(tx.transaction_type) == TransactionType.ADD_VALUE:
            purpose.append('Value Add')
        elif int(tx.transaction_type) == TransactionType.VEND:
            purpose.append('Vend')
        elif int(tx.transaction_type) == TransactionType.CASHOUT_REQUEST:
            purpose.append('[CASHOUT]')
        elif int(tx.transaction_type) == TransactionType.DAMAGE_REFUND_REQUEST:
            purpose.append('[DAMAGES]')
        if bg: purpose.append(f"Billing Group: {bg}.")
        if room: purpose.append(f"Room: {room}.")
        purpose.append(getattr(self.refund_request, 'description'))
        company_name = [getattr(bg, 'display_name', ''), getattr(room, 'display_name', '')]
        lessee = getattr(bg, 'lessee', '')
        if lessee:
            company_name.insert(0, getattr(lessee, 'name', 'Aces Laundry'))
        if all([True if x=='' else False for x in company_name]):
            company_name = ['Aces Laundry']
        payload = {
            'company' : ' -- '.join(company_name),
            'date' : self.refund_request.timestamp,
            'payee' : payee,
            'payee_address' : self.refund_request.check_recipient_address or '',
            'amount' : self.refund_request.refund_amount,
            'purpose' : ' '.join(purpose),
            'requested_by' : self.refund_request.created_by,
            'refund_id' : self.refund_obj.id
        }
        #rendered = render_to_string('check_template.html',payload)
        template = get_template('check_template.html')
        rendered = template.render(payload).encode(encoding='UTF-8')
        filename = f'{payee}-{self.refund_request.timestamp}.html'
        return (filename, rendered)

    def zip_checks(self):
        s = BytesIO()
        zf = ZipFile(s, "w")
        for file_name, rendered_check in self.checks:
            zf.writestr(file_name, rendered_check)
        for file in zf.filelist:
            file.create_system = 0
        zf.close()
        self.zip_file_content = s.getvalue()

    def email_checks(self):
        recipient = [self.refund_request.created_by.email] or settings.IT_EMAIL_LIST
        message = EmailMessage(
            subject = 'Refund Checks Attached',
            body = 'Find attached the rendered check templates',
            to = recipient,
        )
        zip_file_name = 'RenderedRefundChecks-{}'.format(datetime.now())
        message.attach('{}.zip'.format(zip_file_name), self.zip_file_content)
        message.send(fail_silently=False)

    @transaction.atomic()
    def refund(self, refund_request):
        self.refund_request = refund_request
        #TODO: Stop taking amount from agg_param, use partial_value specified by user
        if refund_request.work_order_status:
            work_order_status = self.refund_request.work_order_status
        self._pre_process()
        self.refund_obj = self.save_refund()
        try:
            self._post_process()
        except Exception as e:
            msg = f"Couldn't change balance in Fascard: {e}"
            self._email_failure(
                subject = 'Failed refund request approval',
                err_msg = render_to_string("failed_refund_approval.html", {'msg': msg, 'refund_request': self.refund_request})
            )
            raise Exception(e)
        check = self.generate_check()
        if self.refund_obj and check:
            file_name, file_content = check
            binary_html= BytesIO(file_content)
            self.refund_obj.refund_file.save(file_name, ContentFile(binary_html.getvalue()))
        self.checks = [check]
        self.zip_checks()
        #self.email_checks() #sending checks moved to model so that emails are consolidated
        return self.refund_obj
        

class WipeBonus():
    LAUNDRY_GROUP_ID = 1

    def wipe_bonus(self, tx):
        api = FascardApi(self.LAUNDRY_GROUP_ID)
        fascard_user_id = getattr(tx, 'external_fascard_user_id')
        user_account = api.get_user_account(fascard_user_id)
        account_bonus_amount = Decimal(user_account[0]['Bonus'])
        tx_bonus = Decimal(tx.bonus_amount if hasattr(tx, 'bonus_amount') else 0)
        if tx_bonus > 0:
            new_bonus = account_bonus_amount - tx_bonus
            payload = {
                "Bonus" : str(new_bonus),
                "TransType" : 3,
                "TransSubType" : 0, #Admin adjust
                'SetExactValue' : True
            }
            response = api.refund_loyalty_account(fascard_user_id, payload)
        return response


class AdditionalBonus(BaseClassHandler):
    LAUNDRY_GROUP_ID = 1

    def __init__(self, refund_request):
        self.refund_request = refund_request

    def add(self):
        api = FascardApi(self.LAUNDRY_GROUP_ID)
        fascard_user_id = self.refund_request.external_fascard_user_id
        if not fascard_user_id:
            fascard_user_id = getattr(self.refund_request.transaction, 'external_fascard_user_id')
        amount = self.refund_request.additional_bonus_amount
        if not amount: return True
        if amount == Decimal("0.00"): return True
        if amount < Decimal("0.00") or amount > Decimal("100.00"): return False #Invalid Amount
        payload = {
            "Bonus" : str(self.refund_request.additional_bonus_amount),
            "TransType" : 3,
            "TransSubType" : 3
        }
        r = api.refund_loyalty_account(fascard_user_id, payload)
        #TODO: Test bad reunds
        return True


class RefundFactory(object):

    def __init__(self, refund_type):
        if refund_type == enums.RefundType.AUTHORIZEDOTNET:
            self.refunder = AuthorizeDotNetRefund()
        elif refund_type == enums.RefundType.FASCARD:
            self.refunder = FascardRefund()
        else:
            raise Exception("Refund type not found")