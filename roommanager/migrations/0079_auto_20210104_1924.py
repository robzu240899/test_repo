# -*- coding: utf-8 -*-
# Generated by Django 1.11.23 on 2021-01-04 19:24
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('roommanager', '0078_workorderrecord_available_in_api'),
    ]

    operations = [
        migrations.AlterField(
            model_name='workorderrecord',
            name='upkeep_id',
            field=models.CharField(max_length=30, unique=True),
        ),
    ]
