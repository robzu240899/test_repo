from rest_framework import serializers
from revenue.models import LaundryTransaction
from roommanager.serializers import (
    LaundryRoomSerializer,
    MachineSerializer,
    SlotSerializer)
from decimal import Decimal


class LaundryTransactionSerializer(serializers.ModelSerializer):
    laundry_room = LaundryRoomSerializer()
    machine = MachineSerializer()
    slot = SlotSerializer()
    card_number = serializers.SerializerMethodField()
    amount = serializers.SerializerMethodField()
    
    def get_card_number(self, tx):
        if tx.loyalty_card_number:
            return tx.loyalty_card_number
        elif tx.last_four:
            return tx.last_four
        else:
            return "Unknown"
    
    def get_amount(self,tx):
        x = (tx.credit_card_amount or Decimal('0.00')) + (tx.balance_amount or Decimal('0.00')) + (tx.cash_amount or Decimal('0.00'))
        x = round(x,2)
        return x

    class Meta:
        model = LaundryTransaction
        fields = ['id', 'laundry_room', 'slot', 'machine', 'card_number', 'amount', 'is_refunded', 'dirty_name']
