# -*- coding: utf-8 -*-
# Generated by Django 1.11.23 on 2021-04-15 20:41
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('revenue', '0057_authorizecustomerprofile_timestamp'),
    ]

    operations = [
        migrations.CreateModel(
            name='TxLastIDLog',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('timestamp', models.DateTimeField(auto_now_add=True)),
                ('last_id', models.CharField(max_length=30)),
            ],
        ),
    ]