# Generated by Django 3.1.1 on 2021-06-21 21:30

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('revenue', '0066_laundrytransaction_fake'),
    ]

    operations = [
        migrations.AddField(
            model_name='refundauthorizationrequest',
            name='charge_damage_to_landlord',
            field=models.BooleanField(default=False),
        ),
    ]