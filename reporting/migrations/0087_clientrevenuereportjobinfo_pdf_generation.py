# -*- coding: utf-8 -*-
# Generated by Django 1.11.23 on 2020-09-15 23:03
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('reporting', '0086_billinggroup_allow_cashflow_refunds_deduction'),
    ]

    operations = [
        migrations.AddField(
            model_name='clientrevenuereportjobinfo',
            name='pdf_generation',
            field=models.BooleanField(default=False),
        ),
    ]
