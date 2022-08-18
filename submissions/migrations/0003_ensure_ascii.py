# Generated by Django 3.2.14 on 2022-08-18 19:01

from django.db import migrations
import jsonfield.fields


class Migration(migrations.Migration):

    dependencies = [
        ('submissions', '0002_team_submission_optional'),
    ]

    operations = [
        migrations.AlterField(
            model_name='submission',
            name='answer',
            field=jsonfield.fields.JSONField(blank=True, db_column='raw_answer', dump_kwargs={'ensure_ascii': True}),
        ),
    ]
