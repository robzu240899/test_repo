# Generated by Django 3.1.1 on 2022-11-23 16:50

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('reporting', '0120_auto_20221122_1933'),
    ]

    operations = [
        migrations.AddField(
            model_name='clientrevenuereportjobinfo',
            name='error',
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='clientrevenuereportjobinfo',
            name='errored',
            field=models.BooleanField(default=False),
        )
    ]
