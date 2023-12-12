# -*- coding: utf-8 -*-
# Generated by Django 1.10.2 on 2017-04-21 18:57
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('reporting', '0014_billinggroup_is_active'),
    ]

    operations = [
        migrations.AddField(
            model_name='laundryroomextension',
            name='building_type',
            field=models.CharField(choices=[(b'APARTMENTS', b'APARTMENTS'), (b'STUDENT HOUSING', b'STUDENT HOUSING'), (b'UNKNOWN', b'UNKNOWN'), (b'OTHER', b'OTHER')], default=b'UNKNOWN', max_length=255),
        ),
        migrations.AddField(
            model_name='laundryroomextension',
            name='ownership_type',
            field=models.CharField(choices=[(b'COOP', b'COOP'), (b'CONDO', b'CONDO'), (b'OTHER', b'OTHER'), (b'UNKNOWN', b'UNKNOWN')], default=b'UNKNOWN', max_length=255),
        ),
    ]
