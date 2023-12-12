# -*- coding: utf-8 -*-
# Generated by Django 1.11.23 on 2020-12-10 22:21
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('reporting', '0087_clientrevenuereportjobinfo_pdf_generation'),
    ]

    operations = [
        migrations.AddField(
            model_name='laundryroomextension',
            name='latitude',
            field=models.CharField(blank=True, max_length=50, null=True),
        ),
        migrations.AddField(
            model_name='laundryroomextension',
            name='longitude',
            field=models.CharField(blank=True, max_length=50, null=True),
        ),
    ]
