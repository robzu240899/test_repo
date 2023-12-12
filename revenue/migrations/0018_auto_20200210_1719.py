# -*- coding: utf-8 -*-
# Generated by Django 1.11.23 on 2020-02-10 17:19
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('revenue', '0017_auto_20200207_1844'),
    ]

    operations = [
        migrations.RenameField(
            model_name='laundrytransaction',
            old_name='ballance_amount',
            new_name='balance_amount',
        ),
        migrations.AlterField(
            model_name='checkattributionmatch',
            name='employee',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='revenue.FascardUser'),
        ),
    ]