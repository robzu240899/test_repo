# -*- coding: utf-8 -*-
# Generated by Django 1.11.23 on 2020-09-12 17:34
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('reporting', '0085_clientreportfullstoredfile_report_type'),
    ]

    operations = [
        migrations.AddField(
            model_name='billinggroup',
            name='allow_cashflow_refunds_deduction',
            field=models.BooleanField(default=False),
        ),
    ]
