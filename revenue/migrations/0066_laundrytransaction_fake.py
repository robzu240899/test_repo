# Generated by Django 3.1.1 on 2021-06-20 16:45

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('revenue', '0065_refundauthorizationrequest_cashout_type'),
    ]

    operations = [
        migrations.AddField(
            model_name='laundrytransaction',
            name='fake',
            field=models.BooleanField(default=False),
        ),
    ]
