import logging
import threading
import pandas as pd
from django.conf import settings
from django.core.mail import EmailMessage
from django.template.loader import render_to_string
from django.conf import settings
from main.utils import FieldExtractor
from maintainx.api import MaintainxAPI
from dateutil.relativedelta import relativedelta
from upkeep.api import UpkeepAPI


logger = logging.getLogger(__name__)


class RefundWorkOrderThread(threading.Thread):
    DEFAULT_UPKEEP_CATEGORY = 'Administrative'
    DEFAULT_MAINTAINX_CATEGORY = 'Standard Operating Procedure'
    refund_fields = (
        'amount',
        'timestamp',
        'get_refund_channel_display',
        'fascard_user_account_id',
        'transaction__id',
        'transaction__local_transaction_time'
    )

    STATUS_MAP = {
        'complete': 'DONE',
        'Complete': 'DONE',
        'On Hold': 'ON_HOLD',
        'onHold': 'ON_HOLD',
        'open': 'OPEN',
        'inProgress': 'IN_PROGRESS',
    }

    def __init__(self, instance, *args, **kwargs):
        self.instance = instance
        self.upkeep_api = UpkeepAPI()
        self.maintainx_api = MaintainxAPI()
        super(RefundWorkOrderThread, self).__init__(**kwargs)

    def email_notification(self, data, upkeep_id=None, maintainx_id=None):
        print ("sending wo email notification")
        url = None
        if upkeep_id and maintainx_id: raise Exception("Can't provide two cmms provider ids at once")
        if upkeep_id: url = f"https://app.onupkeep.com/web/work-orders/{upkeep_id}"
        if maintainx_id: url = f"https://app.getmaintainx.com/workorders/{maintainx_id}"
        if not url: return None
        rendered = render_to_string(
            'refund_work_order.html',
            {
                'data' : data,
                'url' : url
            }
        )
        creator = self.instance.authorization_request.created_by
        if creator and creator.email:
            email = EmailMessage(
                subject='Refund - Work Order',
                body=rendered,
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[creator.email]
            )
            email.content_subtype = "html"
            email.send(fail_silently=False)

    def run(self):
        tx = self.instance.transaction
        room = tx.assigned_laundry_room
        asset = tx.machine
        extracted_fields = FieldExtractor.extract_fields(self.refund_fields, self.instance)
        d = {}
        for i, field in enumerate(self.refund_fields):
            d[field] = extracted_fields[i]
        description = [f'{k}: {v}' for k,v in d.items()]
        self.upkeep_payload = {
            'title' : 'Refunded Transaction',
            'location' : getattr(room, 'upkeep_code', None),
            'category' : self.DEFAULT_UPKEEP_CATEGORY,
            'description' : '\n'.join(description),
            'priority' : 2
        }
        self.maintainx_payload = {
            'title' : 'Refunded Transaction',
            'categories': [self.DEFAULT_MAINTAINX_CATEGORY],
            'description' : '\n'.join(description),
            'priority' : "MEDIUM"
        }       
        if getattr(room, 'maintainx_id', None):
            self.maintainx_payload['locationId'] = int(getattr(room, 'maintainx_id'))
        if getattr(asset, 'upkeep_id', None):
            self.upkeep_payload['asset'] = getattr(asset, 'upkeep_id', None)
        if getattr(asset, 'maintainx_id', None):
            self.maintainx_payload['assetId'] = int(getattr(asset, 'maintainx_id'))
        try:
            upkeep_response = self.upkeep_api.create_work_order(self.upkeep_payload)
        except Exception as e:
            print('Failed creating work order for refund: {} {}'.format(self.upkeep_payload, e))
            logger.error('Failed creating work order for refund: {} {}'.format(self.upkeep_payload, e))
        try:
            maintainx_response = self.maintainx_api.create_work_order(self.maintainx_payload)
        except Exception as e:
            print('Failed creating work order for refund: {} {}'.format(self.maintainx_payload, e))
            logger.error('Failed creating work order for refund: {} {}'.format(self.maintainx_payload, e))        
        try:
            upkeep_order_id = upkeep_response['id']
            self.upkeep_update_payload = {'status' : self.instance.authorization_request.work_order_status}
            ur = self.upkeep_api.update_work_order(self.upkeep_update_payload, upkeep_order_id)
            self.email_notification(d, upkeep_id=upkeep_order_id)
        except Exception as e:
            logger.error('Failed updating work order for refund: {} - {} {}'.format(
                self.instance.id,self.upkeep_update_payload, e)
            )
        try:
            status = self.STATUS_MAP.get(self.instance.authorization_request.work_order_status)
            maintainx_order_id = maintainx_response['id']
            if status: mr = self.maintainx_api.update_work_order({'status' : status}, maintainx_order_id)
            self.email_notification(d, maintainx_id=maintainx_order_id)
        except Exception as e:
            logger.error('Failed updating work order for refund: {} - {} {}'.format(
                self.instance.id,{'status' : status}, e)
            )



class OndemandTransactionReingest(threading.Thread):

    def __init__(self, start_from_id=None, end_at_id=None, match=False, **kwargs):
        self.start_from_id = start_from_id
        self.end_at_id = end_at_id
        self.match = match
        super(OndemandTransactionReingest, self).__init__(**kwargs)
       
    def run(self) -> bool:
        from revenue.ingest import FascardTransactionSync
        FascardTransactionSync(1).sync_transactions(
            start_from_id = self.start_from_id,
            end_at_id = self.end_at_id
        )
        if self.match:
            from queuehandler.job_creator import RevenueCreator
            RevenueCreator.match_transactions()
        return True


class FetchMachineRevenue():

    @classmethod
    def fetch_revenue_timeseries(cls, machine, start_date, end_date):
        from reporting.metric.calculate import RevenueEarned
        from reporting.enums import LocationLevel, DurationType
        metrics_client = RevenueEarned
        days_left = (end_date - start_date).days
        next_start_date = end_date
        revenue_dict = {}
        for day in range(days_left):
            payload = {
                "location_type" : LocationLevel.MACHINE,
                "location_id" : machine.id,
                "duration" : DurationType.DAY,
                "start_date" : next_start_date
            }
            result = metrics_client(**payload).process()
            if result: result = float(result)
            else: result = 0.00
            revenue_dict[next_start_date] = result
            next_start_date = next_start_date - relativedelta(days=1)
        timeseries = pd.Series(revenue_dict)
        timeseries = timeseries[::-1]
        return timeseries


class MachineRevenueThread(threading.Thread):

    def __init__(self, room, start_from_date, end_at_date, user_email, **kwargs):
        self.room = room
        self.user_email = user_email
        self.start_from_date = start_from_date
        self.end_at_date = end_at_date
        super(MachineRevenueThread, self).__init__(**kwargs)

    def send_email(self, df):
        logger.info(f"Sending MachineRevenueThread email")
        try:
            subject = f"{self.room} Machines Revenue Time Series"
            msg = EmailMessage(
                subject=subject,
                body=subject,
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=self.user_email.split(',')
            )
            attachment_name = f'{self.room}_revenue_timeseries.csv'
            msg.attach(attachment_name, df.to_csv(), 'text/csv')
            msg.send(fail_silently=False)
        except Exception as e:
            raise Exception(e)
        logger.info("MachineRevenueThread Email sent")

    def run(self):
        logger.info(f"Running MachineRevenueThread")
        from reporting.reliability.anomaly_detection import VolatilityAnomalyDetector
        slots = self.room.slot_set.filter(is_active=True)
        data = {}
        for slot in slots:
            machine = slot.get_current_machine(slot)
            machine_time_series = FetchMachineRevenue.fetch_revenue_timeseries(
                machine,
                self.start_from_date,
                self.end_at_date
            )
            logger.info(f"Got timeseries for machine {machine}")
            data[machine.id] = machine_time_series
        self.send_email(pd.DataFrame(data))