# -*- coding: utf-8 -*-
# Generated by Django 1.11.23 on 2020-06-11 20:10
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('reporting', '0061_auto_20200611_1916'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='billinggroup',
            name='lease_term_duration',
        ),
        migrations.AddField(
            model_name='billinggroup',
            name='lease_term_duration_days',
            field=models.IntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='billinggroup',
            name='lease_term_duration_months',
            field=models.IntegerField(blank=True, null=True),
        ),
    ]