# Generated by Django 3.1.1 on 2023-01-08 22:36

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('reporting', '0124_pricingperiod_timestamp'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='laundryroomextension',
            name='latitude',
        ),
        migrations.RemoveField(
            model_name='laundryroomextension',
            name='longitude',
        ),
        migrations.RemoveField(
            model_name='laundryroomextension',
            name='zip_code',
        ),
    ]
