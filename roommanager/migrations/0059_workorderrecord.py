# -*- coding: utf-8 -*-
# Generated by Django 1.11.23 on 2020-08-11 10:10
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('roommanager', '0058_auto_20200723_1529'),
    ]

    operations = [
        migrations.CreateModel(
            name='WorkOrderRecord',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('asset_upkeep_id', models.CharField(blank=True, max_length=30, null=True)),
                ('assigned_by_upkeep_id', models.CharField(blank=True, max_length=30, null=True)),
                ('assigned_by_upkeep_username', models.CharField(blank=True, max_length=30, null=True)),
                ('assigned_to_upkeep_id', models.CharField(blank=True, max_length=30, null=True)),
                ('assigned_to_upkeep_username', models.CharField(blank=True, max_length=30, null=True)),
                ('category', models.CharField(blank=True, max_length=50, null=True)),
                ('completed_by_upkeep_id', models.CharField(blank=True, max_length=30, null=True)),
                ('completed_by_upkeep_username', models.CharField(blank=True, max_length=30, null=True)),
                ('completed_date', models.DateTimeField(blank=True, null=True)),
                ('created_date', models.DateTimeField(blank=True, null=True)),
                ('description', models.TextField(blank=True, max_length=1500, null=True)),
                ('location_upkeep_id', models.CharField(blank=True, max_length=30, null=True)),
                ('priority_level', models.IntegerField(blank=True, null=True)),
                ('status', models.CharField(blank=True, max_length=30, null=True)),
                ('timestamp', models.DateTimeField(auto_now_add=True)),
                ('title', models.CharField(blank=True, max_length=200, null=True)),
                ('upkeep_id', models.CharField(max_length=30)),
                ('updated_date', models.DateTimeField(blank=True, null=True)),
                ('work_order_no', models.CharField(blank=True, max_length=10, null=True)),
            ],
        ),
    ]
