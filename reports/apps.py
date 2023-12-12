from django.apps import AppConfig
from django.db.models.signals import post_delete
from reports import signals


class ReportsConfig(AppConfig):
    name = 'reports'

    def ready(self):
        post_delete.connect(signals.delete_event_rule, sender='reports.InternalReportConfig')
        post_delete.connect(signals.delete_event_rule, sender='reports.ClientRevenueReportConfig')
        post_delete.connect(signals.delete_event_rule, sender='reports.ClientFullRevenueReportConfig')
        post_delete.connect(signals.delete_event_rule, sender='reports.RentPaidReportConfig')
        post_delete.connect(signals.delete_event_rule, sender='reports.TransactionReportConfig')