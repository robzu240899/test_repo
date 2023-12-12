# Generated by Django 3.1.1 on 2021-05-17 22:17

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('reports', '0011_auto_20210517_1427'),
    ]

    operations = [
        migrations.AlterField(
            model_name='clientfullrevenuereportconfig',
            name='event_rule',
            field=models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='reports.eventrule'),
        ),
        migrations.AlterField(
            model_name='clientrevenuereportconfig',
            name='event_rule',
            field=models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='reports.eventrule'),
        ),
        migrations.AlterField(
            model_name='rentpaidreportconfig',
            name='event_rule',
            field=models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='reports.eventrule'),
        ),
        migrations.AlterField(
            model_name='transactionreportconfig',
            name='event_rule',
            field=models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='reports.eventrule'),
        ),
    ]
