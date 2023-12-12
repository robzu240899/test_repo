# -*- coding: utf-8 -*-
# Generated by Django 1.11.23 on 2019-12-23 20:28
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('roommanager', '0031_machine_created'),
    ]

    operations = [
        migrations.AlterField(
            model_name='hardwarebundle',
            name='card_reader',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='roommanager.CardReaderAsset'),
        ),
        migrations.AlterField(
            model_name='hardwarebundle',
            name='machine',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='roommanager.Machine'),
        ),
        migrations.AlterField(
            model_name='hardwarebundle',
            name='slot',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='roommanager.Slot'),
        ),
    ]
