# -*- coding: utf-8 -*-
# Generated by Django 1.11.23 on 2020-10-05 21:47
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('revenue', '0044_refundauthorizationrequest_wipe_bonus_amount'),
    ]

    operations = [
        migrations.AddField(
            model_name='refundauthorizationrequest',
            name='custom_user_name',
            field=models.CharField(blank=True, max_length=50, null=True),
        ),
    ]
