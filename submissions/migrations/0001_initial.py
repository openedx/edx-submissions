# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models
import jsonfield.fields
import django.utils.timezone
import django_extensions.db.fields


class Migration(migrations.Migration):

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='Score',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('points_earned', models.PositiveIntegerField(default=0)),
                ('points_possible', models.PositiveIntegerField(default=0)),
                ('created_at', models.DateTimeField(default=django.utils.timezone.now, editable=False, db_index=True)),
                ('reset', models.BooleanField(default=False)),
            ],
        ),
        migrations.CreateModel(
            name='ScoreSummary',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('highest', models.ForeignKey(related_name='+', to='submissions.Score')),
                ('latest', models.ForeignKey(related_name='+', to='submissions.Score')),
            ],
            options={
                'verbose_name_plural': 'Score Summaries',
            },
        ),
        migrations.CreateModel(
            name='StudentItem',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('student_id', models.CharField(max_length=255, db_index=True)),
                ('course_id', models.CharField(max_length=255, db_index=True)),
                ('item_id', models.CharField(max_length=255, db_index=True)),
                ('item_type', models.CharField(max_length=100)),
            ],
        ),
        migrations.CreateModel(
            name='Submission',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('uuid', django_extensions.db.fields.UUIDField(db_index=True, version=1, editable=False, blank=True)),
                ('attempt_number', models.PositiveIntegerField()),
                ('submitted_at', models.DateTimeField(default=django.utils.timezone.now, db_index=True)),
                ('created_at', models.DateTimeField(default=django.utils.timezone.now, editable=False, db_index=True)),
                ('answer', jsonfield.fields.JSONField(db_column=b'raw_answer', blank=True)),
                ('student_item', models.ForeignKey(to='submissions.StudentItem')),
            ],
            options={
                'ordering': ['-submitted_at', '-id'],
            },
        ),
        migrations.AlterUniqueTogether(
            name='studentitem',
            unique_together=set([('course_id', 'student_id', 'item_id')]),
        ),
        migrations.AddField(
            model_name='scoresummary',
            name='student_item',
            field=models.OneToOneField(to='submissions.StudentItem'),
        ),
        migrations.AddField(
            model_name='score',
            name='student_item',
            field=models.ForeignKey(to='submissions.StudentItem'),
        ),
        migrations.AddField(
            model_name='score',
            name='submission',
            field=models.ForeignKey(to='submissions.Submission', null=True),
        ),
    ]
