# -*- coding: utf-8 -*-
# Generated by Django 1.11.23 on 2020-02-22 13:36
from __future__ import unicode_literals

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('revenue', '0020_auto_20200222_1321'),
    ]

    operations = [
        migrations.RenameField(
            model_name='transactiongaps',
            old_name='finished',
            new_name='processed',
        ),
    ]