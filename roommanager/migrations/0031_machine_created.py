# -*- coding: utf-8 -*-
# Generated by Django 1.11.23 on 2019-12-23 20:13
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('roommanager', '0030_auto_20191223_1939'),
    ]

    operations = [
        migrations.AddField(
            model_name='machine',
            name='created',
            field=models.DateTimeField(auto_now_add=True, null=True),
        ),
    ]
