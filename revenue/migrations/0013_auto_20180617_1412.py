# -*- coding: utf-8 -*-
# Generated by Django 1.10.2 on 2018-06-17 14:12
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('revenue', '0012_auto_20180303_0000'),
    ]

    operations = [
        migrations.AddField(
            model_name='laundrytransaction',
            name='fascard_record_id',
            field=models.CharField(default=-1, max_length=20),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name='laundrytransaction',
            name='external_fascard_id',
            field=models.CharField(max_length=65, unique=True),
        ),
    ]
