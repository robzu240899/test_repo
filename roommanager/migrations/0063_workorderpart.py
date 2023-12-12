# -*- coding: utf-8 -*-
# Generated by Django 1.11.23 on 2020-09-17 20:34
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('roommanager', '0062_auto_20200822_1754'),
    ]

    operations = [
        migrations.CreateModel(
            name='WorkOrderPart',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('upkeep_id', models.CharField(blank=True, max_length=30, null=True)),
                ('serial', models.CharField(blank=True, max_length=30, null=True)),
                ('details', models.CharField(blank=True, max_length=200, null=True)),
                ('quantity', models.IntegerField(default=0)),
                ('name', models.CharField(blank=True, max_length=30, null=True)),
                ('area', models.CharField(blank=True, max_length=30, null=True)),
                ('created_by_upkeep_id', models.CharField(blank=True, max_length=30, null=True)),
                ('created_date', models.DateTimeField(blank=True, null=True)),
                ('updated_date', models.DateTimeField(blank=True, null=True)),
            ],
        ),
    ]