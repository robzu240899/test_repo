# Generated by Django 3.1.1 on 2021-06-19 18:10

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('revenue', '0062_faketx'),
    ]

    operations = [
        migrations.DeleteModel(
            name='FakeTx',
        ),
        migrations.AlterField(
            model_name='laundrytransaction',
            name='fascard_record_id',
            field=models.CharField(max_length=40),
        ),
    ]
