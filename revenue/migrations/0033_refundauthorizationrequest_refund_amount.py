# -*- coding: utf-8 -*-
# Generated by Django 1.11.23 on 2020-08-24 14:39
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('revenue', '0032_auto_20200824_1407'),
    ]

    operations = [
        migrations.AddField(
            model_name='refundauthorizationrequest',
            name='refund_amount',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=10),
            preserve_default=False,
        ),
    ]