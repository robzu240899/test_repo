# -*- coding: utf-8 -*-
# Generated by Django 1.10.2 on 2017-04-12 21:31
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('reporting', '0002_auto_20170412_1443'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='billinggroup',
            name='revenue_split_level',
        ),
        migrations.RemoveField(
            model_name='revenuesplitrule',
            name='laundry_room',
        ),
        migrations.AddField(
            model_name='laundryroomextension',
            name='laundry_in_bulding',
            field=models.NullBooleanField(),
        ),
        migrations.AlterField(
            model_name='revenuesplitrule',
            name='billing_group',
            field=models.ForeignKey(default=1, on_delete=django.db.models.deletion.CASCADE, to='reporting.BillingGroup'),
            preserve_default=False,
        ),
    ]