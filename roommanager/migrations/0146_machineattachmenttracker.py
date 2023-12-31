# Generated by Django 3.1.1 on 2022-12-23 23:12

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('roommanager', '0145_laundryroom_room_zip_code'),
    ]

    operations = [
        migrations.CreateModel(
            name='MachineAttachmentTracker',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('attachment_maintainx_url', models.IntegerField()),
                ('url', models.CharField(blank=True, max_length=1000, null=True)),
                ('decision', models.CharField(blank=True, choices=[('ACCEPT_AND_REPLACE', 'Accept and Replace Current'), ('SAVE_DONT_REPLACE', 'Save Picture But Do Not Replace Current'), ('REJECT', 'Reject'), ('NA', 'NA')], default='NA', max_length=20, null=True)),
                ('machine', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='roommanager.machine')),
            ],
        ),
    ]
