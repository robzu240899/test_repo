# -*- coding: utf-8 -*-
# Generated by Django 1.11.23 on 2019-10-30 11:25
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion
import storages.backends.s3boto3


class Migration(migrations.Migration):

    dependencies = [
        ('reporting', '0043_pricingreportjobstracker_timestamp'),
    ]

    operations = [
        migrations.CreateModel(
            name='Client',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100)),
                ('address1', models.CharField(max_length=100)),
                ('address2', models.CharField(blank=True, max_length=100)),
                ('phone', models.CharField(max_length=15)),
            ],
        ),
        migrations.AlterField(
            model_name='billinggroup',
            name='schedule_type',
            field=models.CharField(choices=[('CONSTANT', 'Constant'), ('GROSS_REVENUE', 'Gross Revenue'), ('TIME', 'Time- NOT YET IMPLEMENTED')], max_length=1000),
        ),
        migrations.AlterField(
            model_name='clientreportstoredfile',
            name='report_file',
            field=models.FileField(blank=True, null=True, storage=storages.backends.s3boto3.S3Boto3Storage(bucket='tmp-revenue-report-files'), upload_to=''),
        ),
        migrations.AlterField(
            model_name='expensetype',
            name='expense_type',
            field=models.CharField(choices=[('STANDARD', 'STANDARD'), ('CREDIT CARD SPLIT', 'CREDIT CARD SPLIT')], max_length=100),
        ),
        migrations.AlterField(
            model_name='laundryroomextension',
            name='building_type',
            field=models.CharField(choices=[('APARTMENTS', 'APARTMENTS'), ('STUDENT HOUSING', 'STUDENT HOUSING'), ('UNKNOWN', 'UNKNOWN'), ('OTHER', 'OTHER')], default='UNKNOWN', max_length=255),
        ),
        migrations.AlterField(
            model_name='laundryroomextension',
            name='legal_structure',
            field=models.CharField(choices=[('COOP', 'COOP'), ('CONDO', 'CONDO'), ('OTHER', 'OTHER'), ('UNKNOWN', 'UNKNOWN')], default='UNKNOWN', max_length=255),
        ),
        migrations.AlterField(
            model_name='metricscache',
            name='duration',
            field=models.CharField(blank=True, choices=[('DAY', 'DAY'), ('MONTH', 'MONTH'), ('YEAR', 'YEAR'), ('BEFORE', 'BEFORE')], max_length=255, null=True),
        ),
        migrations.AlterField(
            model_name='metricscache',
            name='location_level',
            field=models.CharField(blank=True, choices=[('LAUNDRY ROOM', 'LAUNDRY ROOM'), ('MACHINE', 'MACHINE'), ('BILLING GROUP', 'BILLING GROUP')], max_length=255, null=True),
        ),
        migrations.AlterField(
            model_name='metricscache',
            name='metric_type',
            field=models.CharField(blank=True, choices=[('REVENUE FUNDS', 'REVENUE FUNDS'), ('REVENUE_FUNDS_CREDIT', 'REVENUE_FUNDS_CREDIT'), ('REVENUE_FUNDS_CREDIT_PRESENT_ADD_VALUE', 'REVENUE_FUNDS_CREDIT_PRESENT_ADD_VALUE'), ('REVENUE_FUNDS_CREDIT_WEB_ADD_VALUE', 'REVENUE_FUNDS_CREDIT_WEB_ADD_VALUE'), ('REVENUE_FUNDS_CREDIT_DIRECT_VEND', 'REVENUE_FUNDS_CREDIT_DIRECT_VEND'), ('REVENUE_FUNDS_CASH', 'REVENUE_FUNDS_CASH'), ('REVENUE_FUNDS_CHECK', 'REVENUE_FUNDS_CHECK'), ('REVENUE_EARNED', 'REVENUE_EARNED'), ('FASCARD_REVENUE_FUNDS', 'FASCARD_REVENUE_FUNDS'), ('REVENUE_NUM_ZERO_DOLLAR_TRANSACTIONS', 'REVENUE_NUM_ZERO_DOLLAR_TRANSACTIONS'), ('REVENUE_NUM_NO_DATA_DAYS', 'REVENUE_NUM_NO_DATA_DAYS')], max_length=255, null=True),
        ),
        migrations.AlterField(
            model_name='pricingreportjobinfo',
            name='report_pickle_file',
            field=models.FileField(blank=True, null=True, storage=storages.backends.s3boto3.S3Boto3Storage(bucket='pricing-changes-pickles'), upload_to=''),
        ),
        migrations.AlterField(
            model_name='pricingreportjobstracker',
            name='full_report_file',
            field=models.FileField(blank=True, null=True, storage=storages.backends.s3boto3.S3Boto3Storage(bucket='pricing-change-reports'), upload_to=''),
        ),
        migrations.AlterField(
            model_name='revenuesplitrule',
            name='base_rent',
            field=models.FloatField(blank=True, null=True, verbose_name='Base rent'),
        ),
        migrations.AlterField(
            model_name='revenuesplitrule',
            name='breakpoint',
            field=models.FloatField(blank=True, null=True, verbose_name='Breakpoint | on revenue split deals'),
        ),
        migrations.AlterField(
            model_name='revenuesplitrule',
            name='end_date',
            field=models.DateField(blank=True, null=True, verbose_name='Date | rule split termination date'),
        ),
        migrations.AlterField(
            model_name='revenuesplitrule',
            name='end_gross_revenue',
            field=models.IntegerField(blank=True, null=True, verbose_name='Gross Revenue | rule split termination amount'),
        ),
        migrations.AlterField(
            model_name='revenuesplitrule',
            name='landloard_split_percent',
            field=models.FloatField(blank=True, null=True, verbose_name='Landlord revenue split proportion'),
        ),
        migrations.AlterField(
            model_name='revenuesplitrule',
            name='revenue_split_formula',
            field=models.CharField(choices=[('PERCENT', 'Percent'), ('NATURAL_BREAKPOINT', 'Natural Breakpoint'), ('GENERAL_BREAKPOINT', 'General Breakpoint')], max_length=1000),
        ),
        migrations.AlterField(
            model_name='revenuesplitrule',
            name='start_date',
            field=models.DateField(blank=True, null=True, verbose_name='Date | rule split effectuation date'),
        ),
        migrations.AlterField(
            model_name='revenuesplitrule',
            name='start_gross_revenue',
            field=models.IntegerField(blank=True, null=True, verbose_name='Gross Revenue | rule split effectuation amount'),
        ),
        migrations.AddField(
            model_name='billinggroup',
            name='client',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to='reporting.Client'),
        ),
    ]
