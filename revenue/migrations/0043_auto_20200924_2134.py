# -*- coding: utf-8 -*-
# Generated by Django 1.11.23 on 2020-09-24 21:34
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('revenue', '0042_auto_20200910_2056'),
    ]

    operations = [
        migrations.AlterField(
            model_name='refundauthorizationrequest',
            name='external_fascard_user_id',
            field=models.IntegerField(blank=True, null=True),
        ),
    ]
