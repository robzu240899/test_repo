# Generated by Django 3.1.1 on 2021-05-17 13:42

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('reporting', '0097_auto_20210515_1410'),
        ('roommanager', '0102_auto_20210515_1410'),
        ('reports', '0007_clientfullrevenuereportconfig'),
    ]

    operations = [
        migrations.AlterField(
            model_name='clientfullrevenuereportconfig',
            name='billing_groups',
            field=models.ManyToManyField(blank=True, to='reporting.BillingGroup'),
        ),
        migrations.AlterField(
            model_name='clientrevenuereportconfig',
            name='billing_groups',
            field=models.ManyToManyField(blank=True, to='reporting.BillingGroup'),
        ),
        migrations.AlterField(
            model_name='internalreportconfig',
            name='billing_groups',
            field=models.ManyToManyField(blank=True, to='reporting.BillingGroup'),
        ),
        migrations.AlterField(
            model_name='internalreportconfig',
            name='rooms',
            field=models.ManyToManyField(blank=True, related_name='rooms', to='roommanager.LaundryRoom'),
        ),
        migrations.CreateModel(
            name='RentPaidReportConfig',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('time_units_lookback', models.IntegerField(default=1)),
                ('time_units', models.CharField(choices=[('days', 'days'), ('weeks', 'weeks'), ('months', 'months'), ('years', 'years')], default='months', max_length=30)),
                ('email', models.CharField(max_length=100)),
                ('cron_expression', models.CharField(max_length=20)),
                ('metric', models.CharField(choices=[('REVENUE FUNDS', 'REVENUE FUNDS'), ('REVENUE_FUNDS_CREDIT', 'REVENUE_FUNDS_CREDIT'), ('REVENUE_FUNDS_CREDIT_PRESENT_ADD_VALUE', 'REVENUE_FUNDS_CREDIT_PRESENT_ADD_VALUE'), ('REVENUE_FUNDS_CREDIT_WEB_ADD_VALUE', 'REVENUE_FUNDS_CREDIT_WEB_ADD_VALUE'), ('REVENUE_FUNDS_CREDIT_DIRECT_VEND', 'REVENUE_FUNDS_CREDIT_DIRECT_VEND'), ('REVENUE_FUNDS_CASH', 'REVENUE_FUNDS_CASH'), ('REVENUE_FUNDS_CHECK', 'REVENUE_FUNDS_CHECK'), ('REVENUE_EARNED', 'REVENUE_EARNED'), ('FASCARD_REVENUE_FUNDS', 'FASCARD_REVENUE_FUNDS'), ('REVENUE_NUM_ZERO_DOLLAR_TRANSACTIONS', 'REVENUE_NUM_ZERO_DOLLAR_TRANSACTIONS'), ('REVENUE_NUM_NO_DATA_DAYS', 'REVENUE_NUM_NO_DATA_DAYS'), ('REFUNDS', 'REFUNDS'), ('TRANSACTIONS_COUNT', 'TRANSACTIONS_COUNT')], max_length=50)),
                ('billing_groups', models.ManyToManyField(blank=True, to='reporting.BillingGroup')),
                ('event_rule', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='reports.eventrule')),
            ],
            options={
                'abstract': False,
            },
        ),
    ]
