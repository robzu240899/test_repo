# -*- coding: utf-8 -*-
# Generated by Django 1.10.2 on 2017-03-05 17:27
from __future__ import unicode_literals

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('roommanager', '0001_initial'),
    ]

    operations = [
        migrations.RenameField(
            model_name='laundryroom',
            old_name='fascar_code',
            new_name='fascard_code',
        ),
        migrations.AlterUniqueTogether(
            name='laundryroom',
            unique_together=set([('laundry_group', 'fascard_code')]),
        ),
    ]