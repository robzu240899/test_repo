# -*- coding: utf-8 -*-
# Generated by Django 1.11.23 on 2020-02-26 23:23
from __future__ import unicode_literals

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('revenue', '0022_transactionspool'),
    ]

    operations = [
        migrations.RenameField(
            model_name='transactiongaps',
            old_name='processed',
            new_name='fully_processed',
        ),
        migrations.RenameField(
            model_name='transactionspool',
            old_name='ids_file',
            new_name='transaction_ids',
        ),
    ]
