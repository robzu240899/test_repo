# -*- coding: utf-8 -*-
# Generated by Django 1.11.23 on 2020-12-19 09:57
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('roommanager', '0074_auto_20201210_2221'),
    ]

    operations = [
        migrations.AlterField(
            model_name='cardreaderasset',
            name='card_reader_tag',
            field=models.CharField(max_length=50, unique=True),
        ),
    ]
