# -*- coding: utf-8 -*-
# Generated by Django 1.11.23 on 2021-01-10 16:04
from __future__ import unicode_literals

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('roommanager', '0082_oprhanedpiecerequiredanswer'),
    ]

    operations = [
        migrations.RenameModel(
            old_name='OprhanedPieceRequiredAnswer',
            new_name='OrphanedPieceRequiredAnswer',
        ),
    ]
