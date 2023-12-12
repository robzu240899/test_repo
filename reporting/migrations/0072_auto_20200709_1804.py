# -*- coding: utf-8 -*-
# Generated by Django 1.11.23 on 2020-07-09 18:04
from __future__ import unicode_literals

from django.db import migrations, models
import storages.backends.s3boto3


class Migration(migrations.Migration):

    dependencies = [
        ('reporting', '0071_auto_20200629_1752'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='pricingreportjobinfo',
            name='report_pickle_file',
        ),
        migrations.AddField(
            model_name='pricingreportjobinfo',
            name='report_html_file',
            field=models.FileField(blank=True, null=True, storage=storages.backends.s3boto3.S3Boto3Storage(bucket='pricing-changes-singles'), upload_to=''),
        ),
    ]
