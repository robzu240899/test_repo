from __future__ import unicode_literals
from django.apps import AppConfig
from django.db.models.signals import post_save

class ReportingConfig(AppConfig):
    name = 'reporting'

    def ready(self):
        from reporting import signals
        post_save.connect(signals.trigger_metrics_compute, sender='reporting.BillingGroup')
        post_save.connect(signals.trigger_metrics_compute, sender='reporting.LaundryRoomExtension')
        post_save.connect(signals.room_work_order, sender='reporting.LaundryRoomExtension')