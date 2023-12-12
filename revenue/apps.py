from __future__ import unicode_literals
from django.apps import AppConfig
from django.db.models.signals import post_save
from .signals import refund_as_work_order

class RevenueConfig(AppConfig):
    name = 'revenue'

    def ready(self):
        post_save.connect(refund_as_work_order, sender='revenue.Refund')