import logging
import random
import time
from datetime import datetime, date
from dateutil.relativedelta import relativedelta
from django.core.mail import EmailMessage
from django.template.loader import get_template
from queuehandler.utils import Aurora
from roommanager.models import LaundryRoom
from revenue.models import LaundryTransaction


logger = logging.getLogger(__name__)


class TimeUsageReport():
    report_template = 'time_usage_report.html'

    def __init__(self, send_to, days, months, rooms):
        assert send_to
        self.send_to = send_to
        self.days = days
        self.months = months
        self.rooms = rooms

    def email_report(self):
        assert hasattr(self, 'filename')
        html_response = self.render_template()
        message = EmailMessage(
            subject = 'Time Usage Report Completed',
            body = 'Find attached the time usage report',
            to = [self.send_to]
        )
        message.attach(self.filename, html_response)
        message.send(fail_silently=False)

    def generate_filename(self):
        self.filename = 'TimeUsageReport-{}.html'.format(str(datetime.today()))

    def render_template(self):
        assert hasattr(self, 'dataset')
        template = get_template(self.report_template)
        context = {
            'dataset' : self.dataset
        }
        return template.render(context).encode(encoding='UTF-8')

    def _get_random_dates(self):
        start_from = date.today() - relativedelta(months=self.months)
        days_delta = (date.today() - start_from).days
        dates_to_consider = []
        for i in range(self.days):
            temp_date =  date.today() - relativedelta(days=random.randint(1, days_delta))
            dates_to_consider.append(temp_date)
        return dates_to_consider

    def run(self):
        #Aurora().increase_aurora_capacity(4)
        logger.info("Running TimeUsageReport")
        self.dataset = {'random_dates' : [], 'rooms': {}}
        dates = self._get_random_dates()
        logger.info(f"Random Dates: {dates}")
        #start_from = date.today() - relativedelta(months=self.months)
        #base_q = LaundryTransaction.objects.filter(local_transaction_date__gte=start_from)
        if self.rooms: active_rooms = self.rooms
        else: active_rooms = LaundryRoom.objects.filter(is_active=True)
        for room in active_rooms:
            start = time.time()
            self.dataset['rooms'][room] = {}
            room_q = LaundryTransaction.objects.filter(assigned_laundry_room=room)
            room_data_array = [0]*24
            for date in dates:
                date_q = room_q.filter(local_transaction_date=date)
                for i in range(24):
                    room_data_array[i] += date_q.filter(
                        local_transaction_time__hour__gte=i,
                        local_transaction_time__hour__lt=i+1
                    ).count()
                if not date in self.dataset['random_dates']: self.dataset['random_dates'].append(date)
            self.dataset['rooms'][room]['data_array'] = room_data_array
            self.dataset['rooms'][room]['volume'] = sum(room_data_array)
            room_extension = room.laundryroomextension_set.all().last()
            self.dataset['rooms'][room]['characteristics'] = {
                "Has Elevator" : getattr(room_extension, 'has_elevator', None),
                "Is Outdoors" : getattr(room_extension, 'is_outdoors', None),
                "Building Type" : getattr(room_extension, 'building_type', None),
                "Legal Structure" : getattr(room_extension, 'legal_structure', None),
            }
            end = time.time()
            logger.info(f"Processing room {room} took {end-start} seconds")
            print (f"Processing room {room} took {end-start} seconds")

        self.generate_filename()
        self.email_report()
        #Aurora().modify_aurora_cluster_min_capacity(1)

    @classmethod
    def run_job(cls, send_to, days, months, rooms):
        ins = TimeUsageReport(send_to, days, months, rooms)
        ins.run()