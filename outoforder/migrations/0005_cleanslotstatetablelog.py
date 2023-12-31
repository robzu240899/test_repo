# Generated by Django 3.1.1 on 2021-08-15 13:15

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('outoforder', '0004_auto_20200318_1940'),
    ]

    operations = [
        migrations.CreateModel(
            name='CleanSlotStateTableLog',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('start_date', models.DateTimeField()),
                ('end_date', models.DateTimeField()),
                ('success', models.BooleanField(default=False)),
                ('timestamp', models.DateField(auto_now_add=True)),
            ],
        ),
    ]
