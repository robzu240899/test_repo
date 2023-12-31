# -*- coding: utf-8 -*-
# Generated by Django 1.11.23 on 2020-09-10 20:56
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('revenue', '0041_refundauthorizationrequest_wait_for_settlement'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='laundrytransaction',
            name='refund',
        ),
        migrations.RemoveField(
            model_name='refundauthorizationrequest',
            name='transactions',
        ),
        migrations.AddField(
            model_name='refund',
            name='transaction',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='refunds', to='revenue.LaundryTransaction'),
        ),
        migrations.AddField(
            model_name='refundauthorizationrequest',
            name='transaction',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='revenue.LaundryTransaction'),
        ),
    ]
