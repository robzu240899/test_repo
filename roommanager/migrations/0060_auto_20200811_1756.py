# -*- coding: utf-8 -*-
# Generated by Django 1.11.23 on 2020-08-11 17:56
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('roommanager', '0059_workorderrecord'),
    ]

    operations = [
        migrations.AlterField(
            model_name='workorderrecord',
            name='description',
            field=models.TextField(blank=True, max_length=2000, null=True),
        ),
        migrations.AlterField(
            model_name='workorderrecord',
            name='title',
            field=models.CharField(blank=True, max_length=500, null=True),
        ),
    ]
