# -*- coding: utf-8 -*-
# Generated by Django 1.11.23 on 2020-08-24 14:04
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('revenue', '0030_auto_20200824_1402'),
    ]

    operations = [
        migrations.AlterField(
            model_name='refundauthorizationrequest',
            name='approval_time',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]