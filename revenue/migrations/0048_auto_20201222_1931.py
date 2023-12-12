# -*- coding: utf-8 -*-
# Generated by Django 1.11.23 on 2020-12-22 19:31
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('revenue', '0047_auto_20201024_1723'),
    ]

    operations = [
        migrations.AddField(
            model_name='refundauthorizationrequest',
            name='additional_bonus_amount',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=6),
        ),
        migrations.AlterField(
            model_name='refundauthorizationrequest',
            name='refund_amount',
            field=models.DecimalField(decimal_places=2, max_digits=6),
        ),
        migrations.AlterField(
            model_name='refundauthorizationrequest',
            name='work_order_status',
            field=models.CharField(blank=True, choices=[('complete', 'Complete'), ('onHold', 'On Hold'), ('open', 'Open'), ('inProgress', 'In Progress')], max_length=30, null=True),
        ),
    ]
