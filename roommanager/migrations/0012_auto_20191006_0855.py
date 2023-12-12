# -*- coding: utf-8 -*-
# Generated by Django 1.11.23 on 2019-10-06 08:55
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('roommanager', '0011_auto_20190903_0946'),
    ]

    operations = [
        migrations.AddField(
            model_name='laundryroom',
            name='upkeep_code',
            field=models.CharField(blank=True, max_length=20, null=True),
        ),
        migrations.AlterField(
            model_name='equipmenttype',
            name='equipment_start_check_method',
            field=models.CharField(choices=[('STANDARD', 'STANDARD'), ('DOUBLE', 'DOUBLE')], default='STANDARD', max_length=100),
        ),
        migrations.AlterField(
            model_name='equipmenttype',
            name='machine_type',
            field=models.IntegerField(choices=[(-1, 'UNKNOWN'), (0, 'WASHER'), (1, 'DRYER')]),
        ),
        migrations.AlterField(
            model_name='laundryroom',
            name='time_zone',
            field=models.CharField(choices=[('US/Eastern', 'US/Eastern'), ('US/Western', 'US/Western')], default='US/Eastern', max_length=255),
        ),
        migrations.AlterField(
            model_name='machine',
            name='machine_type',
            field=models.IntegerField(choices=[(-1, 'UNKNOWN'), (0, 'WASHER'), (1, 'DRYER')]),
        ),
        migrations.AlterField(
            model_name='slot',
            name='slot_type',
            field=models.CharField(choices=[('STANDARD', 'STANDARD'), ('DOUBLE', 'DOUBLE')], default='STANDARD', max_length=100),
        ),
    ]