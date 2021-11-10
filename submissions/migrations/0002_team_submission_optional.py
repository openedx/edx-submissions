# Generated by Django 3.2.9 on 2021-11-10 22:08

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('submissions', '0001_squashed_0005_CreateTeamModel'),
    ]

    operations = [
        migrations.AlterField(
            model_name='submission',
            name='team_submission',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='submissions', to='submissions.teamsubmission'),
        ),
    ]
