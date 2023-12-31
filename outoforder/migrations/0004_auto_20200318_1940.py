# -*- coding: utf-8 -*-
# Generated by Django 1.11.23 on 2020-03-18 19:40
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('outoforder', '0003_auto_20190821_1255'),
    ]

    operations = [
        migrations.AlterField(
            model_name='slotstate',
            name='mlvmacherror_description',
            field=models.IntegerField(blank=True, choices=[(0, 'Machine OK'), (1, 'Unable to communicate with machine'), (2, 'Machine leaking water'), (3, 'Machine stuck in cycle'), (4, 'Machine not filling'), (5, 'Machine not draining'), (6, 'Machine not heating'), (7, 'Machine door problem'), (100, 'Part or all of config was rejected'), (101, 'One or more messages timed out or were rejected'), (999, 'Unknown machine problem'), (1000, 'Machine code indicates error')], default=0, null=True),
        ),
        migrations.AlterField(
            model_name='slotstateerror',
            name='error_type',
            field=models.IntegerField(choices=[(-5, 'UNKNOWN'), (-4, 'DIAGNOSTIC'), (-3, 'DISABLED'), (-2, 'ERROR'), (-1, 'OFFLINE'), (-6, 'LONG_IDLE'), (-7, 'LONG_RUNNING'), (-8, 'SHORT_RUNNING'), (-9, 'FLICKERING'), (-10, -10)]),
        ),
    ]
