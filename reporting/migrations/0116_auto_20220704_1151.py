# Generated by Django 3.1.1 on 2022-07-04 11:51

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('reporting', '0115_storedfascardtoken'),
    ]

    operations = [
        migrations.AlterField(
            model_name='storedfascardtoken',
            name='session_token',
            field=models.CharField(max_length=300),
        ),
    ]
