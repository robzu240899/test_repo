# -*- coding: utf-8 -*-
# Generated by Django 1.11.23 on 2019-11-21 17:57
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('roommanager', '0013_auto_20191029_1436'),
    ]

    operations = [
        migrations.CreateModel(
            name='MachineMeter',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('start_time', models.DateTimeField()),
                ('end_time', models.DateTimeField(blank=True, null=True)),
                ('transactions_counter', models.PositiveIntegerField(default=0)),
                ('machine_slot_map', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, to='roommanager.MachineSlotMap')),
            ],
        ),
    ]
