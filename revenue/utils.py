from datetime import date
from decimal import Decimal
from django.db.models import Sum
from django.core.exceptions import ValidationError
from roommanager.models import Slot
from reporting.enums import LocationLevel
from revenue.models import LaundryTransaction, RefundAuthorizationRequest

class MergeTransactionsCount():
    """
        As indicated by Daniel: We loop through all the machineslotmaps that are
        associated to a given slot. Count the transactions assigned to all
        machine placeholder records and assign them to the first real machine asset (with a tag)
        that was associated to the slot
    """

    def merge(self, query):
        for slot in query:
            placeholders = slot.machineslotmap_set.filter(machine__placeholder=True).values('machine')
            transactions_count = LaundryTransaction.objects.filter(
                machine__in = placeholders,
                transaction_type = "100"
            ).count()
            
            msm = slot.machineslotmap_set.filter(
                machine__placeholder=False
            ).order_by('start_time').first()

            if msm:
                first_real_machine = msm.machine
            else:
                continue

            meter = getattr(first_real_machine, 'meter', None)
            if not meter:
                print ("No meter for: {}".format(slot))
                continue
            meter.transactions_counter += transactions_count
            meter.save()
            print ("Updated Machine: {}".format(first_real_machine.asset_code))

    def run(self):
        query = Slot.objects.filter(is_active=True)
        return self.merge(query)


class LocationRefunds():

    def __init__(self, location_level, location_id, start_date=None, end_date=None):
        self.location_level = location_level
        self.location_id = location_id
        self.start_date = start_date
        self.end_date = end_date

    def get_refunds(self):
        d = {'approved':True}
        if self.start_date:
            assert isinstance(self.start_date, date)
            d['timestamp__date__gte'] = self.start_date
        if self.end_date:
            assert isinstance(self.start_date, date)
            d['timestamp__date__lte'] = self.end_date
        if self.location_level == LocationLevel.LAUNDRY_ROOM:
            d['transaction__assigned_laundry_room_id'] = self.location_id
        elif self.location_level == LocationLevel.MACHINE:
            d['transaction__machine_id'] = self.location_id
        else:
            raise ValidationError('Invalid Location type')
        return RefundAuthorizationRequest.objects.filter(**d)


    def get_total_refunds(self):
        refunds = self.get_refunds()
        total = refunds.values('refund_amount').aggregate(result=Sum('refund_amount'))
        return total.get('result') or Decimal('0.0')
