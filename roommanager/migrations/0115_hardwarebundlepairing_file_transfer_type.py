# Generated by Django 3.1.1 on 2021-07-10 12:10

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('roommanager', '0114_machine_maintainx_id'),
    ]

    operations = [
        migrations.AddField(
            model_name='hardwarebundlepairing',
            name='file_transfer_type',
            field=models.CharField(blank=True, max_length=20, null=True),
        ),
    ]
