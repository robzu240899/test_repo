# -*- coding: utf-8 -*-
# Generated by Django 1.11.23 on 2021-03-16 21:23
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('reporting', '0093_auto_20210217_1434'),
    ]

    operations = [
        migrations.AddField(
            model_name='clientrevenuereportjobinfo',
            name='html_generation',
            field=models.BooleanField(default=True),
        ),
    ]