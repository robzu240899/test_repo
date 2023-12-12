# -*- coding: utf-8 -*-
# Generated by Django 1.11.23 on 2019-12-23 18:13
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('roommanager', '0028_auto_20191222_2147'),
    ]

    operations = [
        migrations.RenameField(
            model_name='hardwarebundlepairing',
            old_name='fascard_reader_code',
            new_name='card_reader_code',
        ),
        migrations.RemoveField(
            model_name='slot',
            name='data_matrix_string',
        ),
        migrations.RemoveField(
            model_name='slot',
            name='hex_code',
        ),
        migrations.AddField(
            model_name='hardwarebundle',
            name='location',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='roommanager.LaundryRoom'),
        ),
    ]
