# -*- coding: utf-8 -*-
# Generated by Django 1.11.23 on 2020-06-11 18:56
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('reporting', '0059_auto_20200611_1854'),
    ]

    operations = [
        migrations.AlterField(
            model_name='billinggroup',
            name='lease_term_duration',
            field=models.IntegerField(blank=True, help_text='In Months', null=True),
        ),
    ]
