# -*- coding: utf-8 -*-
# Generated by Django 1.11.23 on 2020-12-10 22:21
from __future__ import unicode_literals

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('roommanager', '0073_hardwarebundlechangeslog_location'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='laundryroom',
            name='latitude',
        ),
        migrations.RemoveField(
            model_name='laundryroom',
            name='longitude',
        ),
    ]
