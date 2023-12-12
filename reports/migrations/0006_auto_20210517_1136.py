# Generated by Django 3.1.1 on 2021-05-17 11:36

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('reports', '0005_auto_20210517_1102'),
    ]

    operations = [
        migrations.AddField(
            model_name='clientrevenuereportconfig',
            name='cron_expression',
            field=models.CharField(default='', max_length=20),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='clientrevenuereportconfig',
            name='email',
            field=models.CharField(default='', max_length=100),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='clientrevenuereportconfig',
            name='event_rule',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='reports.eventrule'),
        ),
    ]