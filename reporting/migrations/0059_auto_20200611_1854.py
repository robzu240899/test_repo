# -*- coding: utf-8 -*-
# Generated by Django 1.11.23 on 2020-06-11 18:54
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('reporting', '0058_upcomingmeterraisenotification'),
    ]

    operations = [
        migrations.AddField(
            model_name='billinggroup',
            name='lease_term_auto_renew',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='billinggroup',
            name='lease_term_auto_renew_length',
            field=models.IntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='billinggroup',
            name='lease_term_duration',
            field=models.IntegerField(blank=True, null=True),
        ),
    ]
