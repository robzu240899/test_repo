# -*- coding: utf-8 -*-
# Generated by Django 1.11.23 on 2019-12-20 17:54
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('roommanager', '0025_auto_20191219_2258'),
    ]

    operations = [
        migrations.AddField(
            model_name='slot',
            name='card_reader_tag',
            field=models.CharField(blank=True, max_length=50, null=True),
        ),
        migrations.AddField(
            model_name='slotmachinepairing',
            name='notify',
            field=models.BooleanField(default=False),
        ),
    ]
