# Generated by Django 3.1.1 on 2021-07-05 17:42

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('roommanager', '0111_technicianemployeeprofile_fascard_user'),
    ]

    operations = [
        migrations.AddField(
            model_name='laundryroom',
            name='maintainx_id',
            field=models.CharField(blank=True, max_length=20, null=True),
        ),
    ]
