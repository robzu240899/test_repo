# -*- coding: utf-8 -*-
# Generated by Django 1.11.23 on 2020-10-03 22:35
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('roommanager', '0066_assetmapout'),
    ]

    operations = [
        migrations.AddField(
            model_name='assetmapout',
            name='description',
            field=models.TextField(blank=True, null=True),
        ),
    ]
