# Generated by Django 3.1.1 on 2021-07-10 13:58

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('roommanager', '0116_hardwarebundlepairing_file_upload_path'),
    ]

    operations = [
        migrations.RenameField(
            model_name='hardwarebundlepairing',
            old_name='file_upload_path',
            new_name='file_transfer_upload_path',
        ),
    ]