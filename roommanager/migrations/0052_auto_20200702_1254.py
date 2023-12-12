# -*- coding: utf-8 -*-
# Generated by Django 1.11.23 on 2020-07-02 12:54
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('roommanager', '0051_cardreadermeter'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='cardreadermeter',
            name='machine',
        ),
        migrations.AddField(
            model_name='cardreadermeter',
            name='card_reader',
            field=models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='meter', to='roommanager.CardReaderAsset'),
        ),
    ]