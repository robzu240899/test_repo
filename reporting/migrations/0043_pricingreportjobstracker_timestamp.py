# -*- coding: utf-8 -*-
# Generated by Django 1.11.23 on 2019-08-29 14:37
from __future__ import unicode_literals

from django.db import migrations, models
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ('reporting', '0042_pricingreportjobinfo_job_tracker'),
    ]

    operations = [
        migrations.AddField(
            model_name='pricingreportjobstracker',
            name='timestamp',
            field=models.DateTimeField(default=django.utils.timezone.now),
        ),
    ]
