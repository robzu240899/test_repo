# -*- coding: utf-8 -*-
# Generated by Django 1.11.23 on 2020-10-24 17:23
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('revenue', '0046_refundauthorizationrequest_work_order_status'),
    ]

    operations = [
        migrations.AddField(
            model_name='refund',
            name='authorization_request',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='revenue.RefundAuthorizationRequest'),
        ),
        migrations.AlterField(
            model_name='refundauthorizationrequest',
            name='work_order_status',
            field=models.CharField(blank=True, choices=[('Complete', 'complete'), ('On Hold', 'onHold'), ('Open', 'open'), ('In Progress', 'inProgress')], max_length=30, null=True),
        ),
    ]