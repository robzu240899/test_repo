# Generated by Django 3.1.1 on 2021-06-01 11:33

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('revenue', '0059_auto_20210515_1410'),
    ]

    operations = [
        migrations.AddField(
            model_name='refundauthorizationrequest',
            name='refunded',
            field=models.BooleanField(default=False),
        ),
    ]
