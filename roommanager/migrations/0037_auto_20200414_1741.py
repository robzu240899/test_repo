# -*- coding: utf-8 -*-
# Generated by Django 1.11.23 on 2020-04-14 17:41
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('roommanager', '0036_auto_20200414_1719'),
    ]

    operations = [
        migrations.AddField(
            model_name='hardwarebundlepairing',
            name='asset_picture',
            field=models.CharField(blank=True, max_length=1000, null=True),
        ),
        migrations.AddField(
            model_name='hardwarebundlepairing',
            name='asset_serial_picture',
            field=models.CharField(blank=True, max_length=1000, null=True),
        ),
    ]