# -*- coding: utf-8 -*-
# Generated by Django 1.11.23 on 2020-08-22 11:31
from __future__ import unicode_literals

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('reporting', '0083_auto_20200822_1128'),
    ]

    operations = [
        migrations.RenameField(
            model_name='laundryroomextension',
            old_name='building_type_choice',
            new_name='building_type',
        ),
        migrations.RenameField(
            model_name='laundryroomextension',
            old_name='legal_structure_choice',
            new_name='legal_structure',
        ),
    ]
