# -*- coding: utf-8 -*-
# Generated by Django 1.11.23 on 2019-12-19 22:58
from __future__ import unicode_literals

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('roommanager', '0024_auto_20191219_1939'),
    ]

    operations = [
        migrations.RenameField(
            model_name='technicianemployeeprofile',
            old_name='codereadr_id',
            new_name='codereadr_username',
        ),
    ]