# Generated by Django 3.1.1 on 2022-06-11 20:29

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('reporting', '0113_billinggroup_payment_method'),
    ]

    operations = [
        migrations.AddField(
            model_name='pricingreportjobinfo',
            name='revenue_data_granularity',
            field=models.CharField(choices=[('daily', 'Daily'), ('monthly', 'Monthly')], default='monthly', max_length=100),
        ),
    ]
