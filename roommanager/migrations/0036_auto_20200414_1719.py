# -*- coding: utf-8 -*-
# Generated by Django 1.11.23 on 2020-04-14 17:19
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('roommanager', '0035_hardwarebundlepairing_scan_type'),
    ]

    operations = [
        migrations.AddField(
            model_name='machine',
            name='asset_picture',
            field=models.CharField(blank=True, max_length=1000, null=True),
        ),
        migrations.AddField(
            model_name='machine',
            name='asset_serial_picture',
            field=models.CharField(blank=True, max_length=1000, null=True),
        ),
    ]
