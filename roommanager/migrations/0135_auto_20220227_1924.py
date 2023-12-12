# Generated by Django 3.1.1 on 2022-02-27 19:24

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('roommanager', '0134_assetupdateapproval_serial_number_not_available'),
    ]

    operations = [
        migrations.AddField(
            model_name='bundlechangeapproval',
            name='serial_number_not_available',
            field=models.BooleanField(default=False, help_text='Check if Serial # NOT Available'),
        ),
        migrations.AlterField(
            model_name='assetupdateapproval',
            name='serial_number_not_available',
            field=models.BooleanField(default=False, help_text='Check if Serial # NOT Available'),
        ),
    ]