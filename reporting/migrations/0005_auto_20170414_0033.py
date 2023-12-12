# -*- coding: utf-8 -*-
# Generated by Django 1.10.2 on 2017-04-14 00:33
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('reporting', '0004_auto_20170413_1504'),
    ]

    operations = [
        migrations.CreateModel(
            name='BillingGroupExpenseTypeMap',
            fields=[
                ('id', models.AutoField(primary_key=True, serialize=False)),
                ('default_amount', models.FloatField()),
                ('billing_group', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='reporting.BillingGroup')),
            ],
            options={
                'db_table': 'laundry_room_expense_expense_type_map',
                'managed': True,
            },
        ),
        migrations.CreateModel(
            name='ExpenseType',
            fields=[
                ('id', models.AutoField(primary_key=True, serialize=False)),
                ('display_name', models.CharField(max_length=100, unique=True)),
                ('description', models.CharField(blank=True, max_length=1000, null=True)),
                ('expense_type', models.CharField(choices=[(b'STANDARD', b'STANDARD'), (b'CREDIT CARD SPLIT', b'CREDIT CARD SPLIT')], max_length=100)),
            ],
            options={
                'db_table': 'expense_type',
                'managed': True,
            },
        ),
        migrations.AddField(
            model_name='billinggroupexpensetypemap',
            name='expense_type',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='reporting.ExpenseType'),
        ),
        migrations.AlterUniqueTogether(
            name='billinggroupexpensetypemap',
            unique_together=set([('billing_group', 'expense_type')]),
        ),
    ]