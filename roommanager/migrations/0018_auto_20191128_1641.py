# -*- coding: utf-8 -*-
# Generated by Django 1.11.23 on 2019-11-28 16:41
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('roommanager', '0017_auto_20191128_1559'),
    ]

    operations = [
        migrations.CreateModel(
            name='TechnicianEmployeeProfile',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('full_name', models.CharField(max_length=200)),
                ('jotform_username', models.CharField(max_length=50)),
                ('notifications_email', models.EmailField(max_length=254)),
            ],
        ),
        migrations.AddField(
            model_name='failedslotmachinepairing',
            name='notification_sent',
            field=models.BooleanField(default=False),
        ),
    ]
