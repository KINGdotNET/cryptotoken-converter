# Generated by Django 2.1.7 on 2019-05-30 02:30

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('payments', '0004_cryptokeypair'),
    ]

    operations = [
        migrations.AddField(
            model_name='cryptokeypair',
            name='used',
            field=models.BooleanField(default=False),
        ),
    ]