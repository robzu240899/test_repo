# -*- coding: utf-8 -*-
# Generated by Django 1.10.2 on 2017-03-05 18:56
from __future__ import unicode_literals

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('roommanager', '0002_auto_20170305_1727'),
        ('revenue', '0001_initial'),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name='fascarduser',
            unique_together=set([('laundry_group', 'fascard_user_account_id')]),
        ),
    ]
