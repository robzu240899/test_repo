# Generated by Django 3.1.1 on 2021-05-17 11:02

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('reporting', '0097_auto_20210515_1410'),
        ('reports', '0004_auto_20210516_2217'),
    ]

    operations = [
        migrations.AlterField(
            model_name='internalreportconfig',
            name='billing_groups',
            field=models.ManyToManyField(blank=True, null=True, to='reporting.BillingGroup'),
        ),
        migrations.CreateModel(
            name='ClientRevenueReportConfig',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('time_units_lookback', models.IntegerField(default=1)),
                ('time_units', models.CharField(choices=[('days', 'days'), ('weeks', 'weeks'), ('months', 'months'), ('years', 'years')], default='months', max_length=30)),
                ('pdf_generation', models.BooleanField(default=False)),
                ('html_generation', models.BooleanField(default=False)),
                ('include_zero_rows', models.BooleanField(default=False)),
                ('billing_groups', models.ManyToManyField(blank=True, null=True, to='reporting.BillingGroup')),
            ],
        ),
    ]
