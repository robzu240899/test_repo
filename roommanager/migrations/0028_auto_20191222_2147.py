# -*- coding: utf-8 -*-
# Generated by Django 1.11.23 on 2019-12-22 21:47
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('roommanager', '0027_auto_20191222_2131'),
    ]

    operations = [
        migrations.CreateModel(
            name='HardwareBundle',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('start_time', models.DateTimeField(auto_now_add=True)),
                ('end_time', models.DateTimeField()),
                ('is_active', models.BooleanField(default=True)),
                ('card_reader', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='roommanager.CardReaderAsset')),
                ('machine', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='roommanager.Machine')),
            ],
        ),
        migrations.RenameField(
            model_name='slot',
            old_name='card_reader_tag',
            new_name='data_matrix_string',
        ),
        migrations.AddField(
            model_name='slot',
            name='hex_code',
            field=models.CharField(blank=True, max_length=50, null=True),
        ),
        migrations.AddField(
            model_name='hardwarebundle',
            name='slot',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='roommanager.Slot'),
        ),
    ]
