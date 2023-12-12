# Generated by Django 3.1.1 on 2022-12-02 20:13

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('roommanager', '0138_auto_20221126_2038'),
    ]

    operations = [
        migrations.AlterField(
            model_name='assetupdateapproval',
            name='asset_picture_decision',
            field=models.CharField(blank=True, choices=[('ACCEPT_AND_REPLACE', 'Accept and Replace Current'), ('SAVE_DONT_REPLACE', 'Save Picture But Do Not Replace Current'), ('REJECT', 'Reject'), ('NA', 'na')], default=('NA', 'na'), max_length=20, null=True),
        ),
        migrations.AlterField(
            model_name='assetupdateapproval',
            name='asset_serial_picture_decision',
            field=models.CharField(blank=True, choices=[('ACCEPT_AND_REPLACE', 'Accept and Replace Current'), ('SAVE_DONT_REPLACE', 'Save Picture But Do Not Replace Current'), ('REJECT', 'Reject'), ('NA', 'na')], default=('NA', 'na'), max_length=20, null=True),
        ),
        migrations.AlterField(
            model_name='bundlechangeapproval',
            name='asset_picture_decision',
            field=models.CharField(blank=True, choices=[('ACCEPT_AND_REPLACE', 'Accept and Replace Current'), ('SAVE_DONT_REPLACE', 'Save Picture But Do Not Replace Current'), ('REJECT', 'Reject'), ('NA', 'na')], default=('NA', 'na'), max_length=20, null=True),
        ),
        migrations.AlterField(
            model_name='bundlechangeapproval',
            name='asset_serial_picture_decision',
            field=models.CharField(blank=True, choices=[('ACCEPT_AND_REPLACE', 'Accept and Replace Current'), ('SAVE_DONT_REPLACE', 'Save Picture But Do Not Replace Current'), ('REJECT', 'Reject'), ('NA', 'na')], default=('NA', 'na'), max_length=20, null=True),
        ),
    ]