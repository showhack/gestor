# Generated by Django 3.0.8 on 2022-10-09 02:27

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0003_userprofile_role'),
    ]

    operations = [
        migrations.DeleteModel(
            name='User',
        ),
    ]
