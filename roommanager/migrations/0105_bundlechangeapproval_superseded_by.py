# Generated by Django 3.1.1 on 2021-06-04 20:07

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('roommanager', '0104_auto_20210527_1115'),
    ]

    operations = [
        migrations.AddField(
            model_name='bundlechangeapproval',
            name='superseded_by',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='roommanager.bundlechangeapproval'),
        ),
    ]