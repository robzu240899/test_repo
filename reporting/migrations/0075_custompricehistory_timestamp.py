# -*- coding: utf-8 -*-
# Generated by Django 1.11.23 on 2020-07-25 20:27
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('reporting', '0074_auto_20200724_1524'),
    ]

    operations = [
        migrations.AddField(
            model_name='custompricehistory',
            name='timestamp',
            field=models.DateTimeField(auto_now_add=True, null=True),
        ),
    ]
