# Generated by Django 3.1.1 on 2021-12-25 17:41

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('reports', '0018_auto_20211225_1651'),
    ]

    operations = [
        migrations.AlterField(
            model_name='transactionreportconfig',
            name='last_activity_lookback',
            field=models.IntegerField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name='transactionreportconfig',
            name='last_activity_lookback_time_units',
            field=models.CharField(blank=True, choices=[('days', 'days'), ('weeks', 'weeks'), ('months', 'months'), ('years', 'years')], max_length=30, null=True),
        ),
    ]
