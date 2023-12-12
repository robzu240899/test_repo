# -*- coding: utf-8 -*-
# Generated by Django 1.11.23 on 2020-08-21 11:51
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('roommanager', '0060_auto_20200811_1756'),
    ]

    operations = [
        migrations.CreateModel(
            name='EquipmentTypeSchedule',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('start_from', models.IntegerField()),
                ('end_at', models.IntegerField()),
                ('active', models.BooleanField()),
                ('equipment_type', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='schedules', to='roommanager.EquipmentType')),
                ('laundry_room', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='schedules', to='roommanager.LaundryRoom')),
            ],
        ),
    ]
