# -*- coding: utf-8 -*-
# Generated by Django 1.11.23 on 2020-08-10 12:22
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('reporting', '0077_billinggroup_operations_start_date'),
    ]

    operations = [
        migrations.AddField(
            model_name='clientreportbasicstoredfile',
            name='file_type',
            field=models.CharField(choices=[(('html',), ('html',)), ('pdf', 'pdf')], default=('html',), max_length=20),
        ),
    ]
