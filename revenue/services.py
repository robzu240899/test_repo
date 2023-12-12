import logging
import hashlib
from datetime import datetime
from .models import FascardUser, LaundryTransaction, RefundAuthorizationRequest
from .matcher import WebBasedMatcher, StandardMatcher
from .enums import TransactionType, AddValueSubType, RefundChannelChoices, RefundTypeChoices

logger = logging.getLogger(__name__)

class SpecialRefundBase:

    def _compute_new_fake_id(self):
        unix_timestamp = str(datetime.utcnow().timestamp())
        string = f"{self.CODE}{unix_timestamp}".encode()
        return hashlib.md5(string).hexdigest()

    def _match_tx(self, tx):
        try:
            WebBasedMatcher(tx.id).match()
        except Exception as e:
            logger.error(f"Failed WVA-matching fake transaction with id: {tx.id}")

    def create_fake_transaction(self, tx_amount, fascard_user_id=None):
        external_fascard_id = self._compute_new_fake_id()
        kwargs = {self.agg_param : tx_amount}
        for param in set(['cash_amount', 'balance_amount', 'credit_card_amount']) - set([self.agg_param]):
            kwargs[param] = 0
        if fascard_user_id:
            kwargs['external_fascard_user_id'] = fascard_user_id
            fascard_user = FascardUser.objects.filter(fascard_user_account_id=fascard_user_id).first()
            if fascard_user: kwargs['fascard_user'] = fascard_user
        tx = LaundryTransaction.objects.create(
            external_fascard_id = external_fascard_id,
            fascard_record_id = f"{external_fascard_id}-86",
            transaction_type = self.transaction_type,
            trans_sub_type = self.trans_sub_type,
            local_transaction_time = datetime.now(),
            utc_transaction_time = datetime.utcnow(),
            fake=True,
            **kwargs
        )
        return tx


class CashoutRefundManager(SpecialRefundBase):
    CODE = 101
    agg_param = 'balance_amount'
    transaction_type = TransactionType.CASHOUT_REQUEST
    trans_sub_type = AddValueSubType.FAKE

    def send_for_approval(self, cleaned_data, requestor) -> RefundAuthorizationRequest:
        fake_tx = self.create_fake_transaction(cleaned_data.get('cashout_amount'), cleaned_data.get('fascard_user_id'))
        self._match_tx(fake_tx)
        refund_approval_request = RefundAuthorizationRequest.objects.create(
            check_recipient = cleaned_data.get('check_payee_name'),
            check_recipient_address = cleaned_data.get('check_recipient_address'),
            aggregator_param = self.agg_param,
            external_fascard_user_id = cleaned_data.get('fascard_user_id'),
            description = "{}".format(cleaned_data.get('description')),
            transaction = fake_tx,
            created_by = requestor,
            refund_amount = cleaned_data.get('cashout_amount'),
            refund_channel = RefundChannelChoices.CHECK,
            cashout_type = cleaned_data.get('cashout_balance_type'),
            refund_type_choice = RefundTypeChoices.CASHOUT
        )
        return refund_approval_request


class DamageRefundManager(SpecialRefundBase):
    CODE = 201
    transaction_type = TransactionType.DAMAGE_REFUND_REQUEST
    agg_param = 'balance_amount'
    trans_sub_type = AddValueSubType.FAKE

    def send_for_approval(self, cleaned_data, requestor) -> RefundAuthorizationRequest:
        fake_tx = self.create_fake_transaction(
            cleaned_data.get('refund_amount'),
            cleaned_data.get('fascard_user_id')
        )
        slot = cleaned_data.get('slot')
        machine = slot.get_current_machine(slot) if slot else None
        fake_tx.slot = slot
        fake_tx.machine = machine
        fake_tx.laundry_room = cleaned_data.get('laundry_room') or None #overrides web-based matcher
        fake_tx.save()
        StandardMatcher().match_tx(fake_tx)
        fake_tx.refresh_from_db()
        refund_approval_request = RefundAuthorizationRequest.objects.create(
            check_recipient = cleaned_data.get('check_payee_name'),
            aggregator_param = self.agg_param,
            external_fascard_user_id = cleaned_data.get('fascard_user_id'),
            description = "{}".format(cleaned_data.get('description')),
            transaction = fake_tx,
            created_by = requestor,
            refund_amount = cleaned_data.get('refund_amount'),
            charge_damage_to_landlord = cleaned_data.get('charge_damage_to_landlord'),
            force_charge_landlord_choice = cleaned_data.get('force'),
            refund_channel = cleaned_data.get('refund_channel'),
            cashout_type = cleaned_data.get('cashout_balance_type'),
            refund_type_choice = RefundTypeChoices.DAMAGE
        )
        return refund_approval_request








