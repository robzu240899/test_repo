# -*- coding: utf-8 -*-
# Generated by Django 1.11.23 on 2019-08-15 17:31
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('roommanager', '0009_auto_20190815_1628'),
    ]

    operations = [
        migrations.AddField(
            model_name='equipmenttype',
            name='equipment_start_check_method',
            field=models.CharField(choices=[(b'STANDARD', b'STANDARD'), (b'DOUBLE', b'DOUBLE')], default=b'STANDARD', max_length=100),
        ),
    ]
