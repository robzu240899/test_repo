# -*- coding: utf-8 -*-
# Generated by Django 1.11.23 on 2020-10-04 20:52
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('roommanager', '0067_assetmapout_description'),
    ]

    operations = [
        migrations.AddField(
            model_name='assetmapout',
            name='needs_rescaning',
            field=models.BooleanField(default=False),
        ),
    ]
