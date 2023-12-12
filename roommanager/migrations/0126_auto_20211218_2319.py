# Generated by Django 3.1.1 on 2021-12-18 23:19

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('roommanager', '0125_auto_20211218_2126'),
    ]

    operations = [
        migrations.CreateModel(
            name='UpkeepUser',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('first_name', models.CharField(blank=True, max_length=30, null=True)),
                ('last_name', models.CharField(blank=True, max_length=30, null=True)),
                ('role', models.CharField(blank=True, max_length=30, null=True)),
                ('email', models.EmailField(blank=True, max_length=254, null=True)),
                ('phone_number', models.CharField(blank=True, max_length=20, null=True)),
                ('upkeep_id', models.CharField(blank=True, max_length=20, null=True)),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.AlterField(
            model_name='maintainxuser',
            name='first_name',
            field=models.CharField(blank=True, max_length=30, null=True),
        ),
        migrations.AlterField(
            model_name='maintainxuser',
            name='last_name',
            field=models.CharField(blank=True, max_length=30, null=True),
        ),
        migrations.AlterField(
            model_name='maintainxuser',
            name='role',
            field=models.CharField(blank=True, max_length=30, null=True),
        ),
    ]