# -*- coding: utf-8 -*-
# Generated by Django 1.11.23 on 2019-12-23 19:39
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('roommanager', '0029_auto_20191223_1813'),
    ]

    operations = [
        migrations.AlterField(
            model_name='hardwarebundle',
            name='end_time',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
