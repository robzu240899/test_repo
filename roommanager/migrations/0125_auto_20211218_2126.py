# Generated by Django 3.1.1 on 2021-12-18 21:26

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('roommanager', '0124_remove_maintainxworkorderpart_quantity_used'),
    ]

    operations = [
        migrations.AlterField(
            model_name='maintainxworkorderpart',
            name='area',
            field=models.CharField(blank=True, max_length=100, null=True),
        ),
        migrations.AlterField(
            model_name='maintainxworkorderpart',
            name='name',
            field=models.CharField(blank=True, max_length=100, null=True),
        ),
    ]
