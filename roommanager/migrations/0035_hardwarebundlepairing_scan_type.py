# -*- coding: utf-8 -*-
# Generated by Django 1.11.23 on 2020-01-07 16:27
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('roommanager', '0034_auto_20200107_0847'),
    ]

    operations = [
        migrations.AddField(
            model_name='hardwarebundlepairing',
            name='scan_type',
            field=models.CharField(blank=True, choices=[('STACKDRYER', 'STACKDRYER'), ('SINGLE', 'SINGLE')], max_length=20, null=True),
        ),
    ]
