# -*- coding: utf-8 -*-
# Generated by Django 1.11.23 on 2020-05-21 11:56
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('roommanager', '0042_auto_20200521_1016'),
    ]

    operations = [
        migrations.AddField(
            model_name='machinemeter',
            name='upkeep_id',
            field=models.CharField(blank=True, max_length=50, null=True),
        ),
    ]