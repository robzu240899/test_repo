# -*- coding: utf-8 -*-
# Generated by Django 1.10.2 on 2017-05-10 18:32
from __future__ import unicode_literals

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('queuehandler', '0002_nightlyruntracker_run_type'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='nightlyruntracker',
            name='run_type',
        ),
    ]
