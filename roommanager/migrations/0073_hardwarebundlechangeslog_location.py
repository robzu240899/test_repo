# -*- coding: utf-8 -*-
# Generated by Django 1.11.23 on 2020-11-26 13:08
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('roommanager', '0072_hardwarebundlechangeslog'),
    ]

    operations = [
        migrations.AddField(
            model_name='hardwarebundlechangeslog',
            name='location',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='hardware_bundle_changes', to='roommanager.LaundryRoom'),
        ),
    ]
