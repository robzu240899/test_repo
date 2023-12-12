# from reporting.finance.clientreport.report import *
# from reporting.models import *
# from roommanager.models import *
# bg = BillingGroup.objects.get(id=47)

# from datetime import date
# dt = date(2019,8,1)

# jobs_tracker = ClientRevenueJobsTracker.objects.create(user_requested_email="juaneljach10@gmail.com")

# ClientRevenueFullReport(bg, dt, jobs_tracker).create()


from revenue.enums import *
from revenue.models import LaundryTransaction
from reporting.enums import LocationLevel, MetricType, DurationType
from roommanager.models import *
from datetime import datetime
from dateutil.relativedelta import relativedelta


from django.db.models import Q


start = datetime.today() - relativedelta(days=35)
end_report_date = start + relativedelta(months=1)
number_days = (end_report_date-start).days

days_left = number_days

laundry_room = LaundryRoom.objects.get(pk=157)

location_type = LocationLevel.LAUNDRY_ROOM
next_start_date = start

for day in range(days_left):
    q = LaundryTransaction.objects.all()
    end_date = next_start_date + relativedelta(days=1)
    print ("Date: {}".format(next_start_date))
    custom_filters = [~Q(cash_amount=0) | ~Q(credit_card_amount=0)]
    transaction_type_filters = [Q(transaction_type=TransactionType.ADD_VALUE) | Q(transaction_type=TransactionType.VEND)]
    standard_filters = [Q(fascard_user__is_employee=False) | Q(fascard_user=None)]

    for standard_filter in standard_filters:
        q = q.filter(standard_filter)


    for transaction_type_filter in transaction_type_filters:
        q = q.filter(transaction_type_filter)

    q = q.filter(assigned_laundry_room_id=laundry_room.id)

    q = q.filter(assigned_local_transaction_time__date__gte=next_start_date)
    q = q.filter(assigned_local_transaction_time__date__lt=end_date)

    print ("Queryset: {} -- {}".format(q, q.count()))

    next_start_date = next_start_date + relativedelta(days=1)