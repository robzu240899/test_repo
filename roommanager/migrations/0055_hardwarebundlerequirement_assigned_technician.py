# -*- coding: utf-8 -*-
# Generated by Django 1.11.23 on 2020-07-02 20:25
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('roommanager', '0054_technicianemployeeprofile_upkeep_id'),
    ]

    operations = [
        migrations.AddField(
            model_name='hardwarebundlerequirement',
            name='assigned_technician',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='roommanager.TechnicianEmployeeProfile'),
        ),
    ]