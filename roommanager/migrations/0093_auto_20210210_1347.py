# -*- coding: utf-8 -*-
# Generated by Django 1.11.23 on 2021-02-10 13:47
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('roommanager', '0092_auto_20210210_1347'),
    ]

    operations = [
        migrations.AlterField(
            model_name='hardwarebundlepairing',
            name='combostack',
            field=models.BooleanField(default=False),
        ),
    ]