# Generated by Django 3.1.1 on 2022-12-21 13:24

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('reporting', '0121_auto_20221123_1650'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='pricingreportjobinfo',
            name='revenue_data_granularity',
        ),
        migrations.RemoveField(
            model_name='pricingreportjobinfo',
            name='rolling_mean_periods',
        ),
        migrations.AddField(
            model_name='pricingperiod',
            name='reason',
            field=models.CharField(blank=True, max_length=100, null=True),
        ),
    ]
