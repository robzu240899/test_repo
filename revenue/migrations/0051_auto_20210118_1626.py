# -*- coding: utf-8 -*-
# Generated by Django 1.11.23 on 2021-01-18 16:26
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('revenue', '0050_auto_20210112_1642'),
    ]

    operations = [
        migrations.RemoveIndex(
            model_name='laundrytransaction',
            name='laundry_tra_local_t_7491a4_idx',
        ),
        migrations.RenameField(
            model_name='refundauthorizationrequest',
            old_name='custom_user_name',
            new_name='check_recipient',
        ),
        migrations.AddIndex(
            model_name='laundrytransaction',
            index=models.Index(fields=['local_transaction_date', 'local_transaction_time'], name='laundry_tra_local_t_ea75b0_idx'),
        ),
    ]
