# -*- coding: utf-8 -*-
# Generated by Django 1.11.23 on 2020-05-14 14:07
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('roommanager', '0040_machine_placeholder'),
    ]

    operations = [
        migrations.AlterField(
            model_name='hardwarebundlepairing',
            name='data_matrix_string',
            field=models.CharField(max_length=20),
        ),
    ]
