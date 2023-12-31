# -*- coding: utf-8 -*-
# Generated by Django 1.11.23 on 2021-04-19 17:56
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('roommanager', '0096_slotview'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='slotview',
            options={'verbose_name': 'Slot (With no MachineSlotMap History)', 'verbose_name_plural': 'Slots (With no MachineSlotMap History)'},
        ),
        migrations.AlterField(
            model_name='bundlechangeapproval',
            name='previous_bundle',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='roommanager.HardwareBundle'),
        ),
    ]
