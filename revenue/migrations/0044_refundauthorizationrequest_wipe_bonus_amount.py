# -*- coding: utf-8 -*-
# Generated by Django 1.11.23 on 2020-09-28 17:41
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('revenue', '0043_auto_20200924_2134'),
    ]

    operations = [
        migrations.AddField(
            model_name='refundauthorizationrequest',
            name='wipe_bonus_amount',
            field=models.BooleanField(default=False),
        ),
    ]
