# -*- coding: utf-8 -*-
# Generated by Django 1.11.23 on 2021-04-20 20:46
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('roommanager', '0098_auto_20210419_1803'),
    ]

    operations = [
        migrations.AlterField(
            model_name='bundlechangeapproval',
            name='change_type',
            field=models.CharField(blank=True, choices=[('SLOT_CHANGE', 'SLOT_CHANGE'), ('MACHINE_CHANGE', 'MACHINE_CHANGE'), ('CARD_READER_CHANGE', 'CARD_READER_CHANGE'), ('NEW', 'NEW')], max_length=50, null=True),
        ),
        migrations.AlterField(
            model_name='hardwarebundlechangeslog',
            name='change_type',
            field=models.CharField(choices=[('SLOT_CHANGE', 'SLOT_CHANGE'), ('MACHINE_CHANGE', 'MACHINE_CHANGE'), ('CARD_READER_CHANGE', 'CARD_READER_CHANGE'), ('NEW', 'NEW')], max_length=30),
        ),
        migrations.AlterField(
            model_name='machine',
            name='equipment_type',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='machine', to='roommanager.EquipmentType'),
        ),
    ]
