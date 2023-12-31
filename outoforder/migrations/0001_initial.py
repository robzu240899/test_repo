# -*- coding: utf-8 -*-
# Generated by Django 1.10.2 on 2017-04-06 04:30
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('roommanager', '0002_auto_20170305_1727'),
    ]

    operations = [
        migrations.CreateModel(
            name='SlotState',
            fields=[
                ('id', models.AutoField(primary_key=True, serialize=False)),
                ('start_time', models.DateTimeField()),
                ('end_time', models.DateTimeField(null=True)),
                ('local_start_time', models.DateTimeField()),
                ('local_end_time', models.DateTimeField(null=True)),
                ('duration', models.BigIntegerField(null=True)),
                ('slot_status', models.IntegerField(choices=[(-4, -4), (-3, -3), (-1, -1), (0, 0), (1, 1), (-2, -2), (-5, -5), (-6, -6)])),
                ('recorded_time', models.DateTimeField()),
                ('local_recorded_time', models.DateTimeField()),
                ('error_checking_complete', models.BooleanField(default=False)),
                ('certified_error_free', models.BooleanField(default=False)),
                ('has_endtime_guess', models.BooleanField(default=False)),
                ('is_filler_state', models.BooleanField(default=False)),
                ('is_guess_state', models.BooleanField(default=False)),
                ('state_order', models.IntegerField(blank=True, null=True)),
                ('slot', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='slot_set', to='roommanager.Slot')),
            ],
            options={
                'db_table': 'slot_state',
                'managed': True,
            },
        ),
        migrations.CreateModel(
            name='SlotStateError',
            fields=[
                ('id', models.AutoField(primary_key=True, serialize=False)),
                ('error_type', models.IntegerField(choices=[(-5, b'UNKNOWN'), (-4, b'DIAGNOSTIC'), (-3, b'DISABLED'), (-2, b'ERROR'), (-1, b'OFFLINE'), (-6, b'LONG_IDLE'), (-7, b'LONG_RUNNING'), (-8, b'SHORT_RUNNING'), (-9, b'FLICKERING'), (-10, -10)])),
                ('error_message', models.CharField(max_length=1000)),
                ('severity', models.IntegerField(null=True)),
                ('is_reported', models.BooleanField(default=False)),
                ('reported_time', models.DateTimeField(blank=True, null=True)),
                ('slot_state', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='outoforder.SlotState')),
            ],
            options={
                'db_table': 'slot_state_error',
                'managed': True,
            },
        ),
    ]
