# Generated by Django 3.1.1 on 2021-06-19 19:23

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('revenue', '0064_auto_20210619_1810'),
    ]

    operations = [
        migrations.AddField(
            model_name='refundauthorizationrequest',
            name='cashout_type',
            field=models.CharField(blank=True, choices=[('Balance', 'Balance'), ('Bonus', 'Bonus')], max_length=30, null=True),
        ),
    ]
