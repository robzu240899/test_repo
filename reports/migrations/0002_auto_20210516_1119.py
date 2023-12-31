# Generated by Django 3.1.1 on 2021-05-16 11:19

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('reports', '0001_initial'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='internalreportconfig',
            name='delivery_method',
        ),
        migrations.RemoveField(
            model_name='internalreportconfig',
            name='end_date',
        ),
        migrations.RemoveField(
            model_name='internalreportconfig',
            name='start_date',
        ),
        migrations.AddField(
            model_name='internalreportconfig',
            name='time_units',
            field=models.CharField(choices=[('days', 'days'), ('weeks', 'weeks'), ('months', 'months'), ('years', 'years')], default='months', max_length=30),
        ),
        migrations.AddField(
            model_name='internalreportconfig',
            name='time_units_lookback',
            field=models.IntegerField(default=1),
        ),
    ]
