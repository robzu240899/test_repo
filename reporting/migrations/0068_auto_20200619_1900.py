# -*- coding: utf-8 -*-
# Generated by Django 1.11.23 on 2020-06-19 19:00
from __future__ import unicode_literals

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('reporting', '0067_clientrevenuejobstracker_clientrevenuereportjobinfo'),
    ]

    operations = [
        migrations.RenameModel(
            old_name='ClientReportStoredFile',
            new_name='ClientReportFullStoredFile',
        ),
    ]
