# -*- coding: utf-8 -*-
# Generated by Django 1.10.2 on 2019-08-06 16:49
from __future__ import unicode_literals

import django.core.files.storage
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('reporting', '0034_auto_20190806_1549'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='clientrevenuefullreportjobinfo',
            name='billing_groups',
        ),
        migrations.AddField(
            model_name='clientrevenuefullreportjobinfo',
            name='billing_groups',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, to='reporting.BillingGroup'),
        ),
        migrations.AlterField(
            model_name='clientrevenuefullreportjobinfo',
            name='generated_file',
            field=models.FileField(blank=True, null=True, storage=django.core.files.storage.FileSystemStorage(location=b'/home/eljach/apps/laundry_system/tmp'), upload_to=b''),
        ),
    ]