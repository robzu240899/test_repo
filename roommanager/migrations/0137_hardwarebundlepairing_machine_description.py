# Generated by Django 3.1.1 on 2022-11-25 18:15

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('roommanager', '0136_machinemeterreading'),
    ]

    operations = [
        migrations.AddField(
            model_name='hardwarebundlepairing',
            name='machine_description',
            field=models.TextField(blank=True, max_length=200, null=True),
        ),
    ]
