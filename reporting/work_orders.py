from datetime import date, datetime
from django.conf import settings
from django.core.mail import EmailMessage
from dateutil.relativedelta import relativedelta
from maintainx.api import MaintainxAPI
from maintainx.enums import MaintainxDefaultCategories


class MeterRaiseWorkOrder():

    @classmethod
    def _email_failure(cls, meter_raise, err_msg):
        message = EmailMessage(
            '[ALERT] Failed creating Work Order for Meter Raise',
            f"{err_msg} for meter raise (id: {meter_raise.id}) with schedule date {meter_raise.scheduled_date}",
            settings.DEFAULT_FROM_EMAIL,
            settings.IT_EMAIL_LIST
        )
        message.send(fail_silently=False)

    @classmethod
    def _sync_as_work_order(cls, meter_raise, due_date, start_date, title, description):
        api = MaintainxAPI()
        maintainx_payload = {
            'title' : title,
            'description' : description,
            'assignees' : [{"type": "TEAM","id": settings.MAINTAINX_PRICING_CHANGES_TEAM_ID}],
            'categories' : [MaintainxDefaultCategories.PRICING_CHANGES],
            'dueDate' : due_date.isoformat(),
            'startDate' : start_date.isoformat(),
            'priority' : "MEDIUM"
        }
        try: return api.create_work_order(maintainx_payload)
        except Exception as e: cls._email_failure(meter_raise, str(e))

    @classmethod
    def _sync_meter_raises_as_work_order(cls, meter_raise):
        due_date = datetime(
            meter_raise.scheduled_date.year,
            meter_raise.scheduled_date.month,
            meter_raise.scheduled_date.day
        )
        start_date = due_date + relativedelta(days=7)
        title = f'Pricing Change -- {meter_raise.scheduled_date} -- {meter_raise.billing_group.display_name}'
        description = f'Scheduled Date: {meter_raise.scheduled_date}. Raise Limit: {meter_raise.raise_limit}'
        return cls._sync_as_work_order(meter_raise,due_date, start_date, title, description)

    @classmethod
    def _sync_meter_raises_notifications_as_work_orders(cls, meter_raise):
        due_date = datetime(
            meter_raise.scheduled_date.year,
            meter_raise.scheduled_date.month,
            meter_raise.scheduled_date.day
        ) - relativedelta(days=45)
        start_date = due_date
        title = f'Send Pricing Change Notification -- {meter_raise.scheduled_date} -- {meter_raise.billing_group.display_name}'
        description = f"""

        *Email Notification Template*

        Hello [[name]],

        I hope everything is well with you.
        We wanted to send this email as a brief remainder that we'll be raising meters as stated in our lease agreement:
        
        Scheduled Date: {meter_raise.scheduled_date}. Raise Limit: {meter_raise.raise_limit}.

        Best regards,
        Daniel + Aces Laundry      
        """
        return cls._sync_as_work_order(meter_raise,due_date, start_date, title, description)
        