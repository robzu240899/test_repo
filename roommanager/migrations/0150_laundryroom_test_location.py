# Generated by Django 3.1.1 on 2023-05-05 19:35

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('roommanager', '0149_auto_20230108_1931'),
    ]

    operations = [
        migrations.AddField(
            model_name='laundryroom',
            name='test_location',
            field=models.BooleanField(default=False),
        ),
    ]
