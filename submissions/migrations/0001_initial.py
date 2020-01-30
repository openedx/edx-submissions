# -*- coding: utf-8 -*-
from __future__ import absolute_import, unicode_literals

import django.utils.timezone
from django.db import migrations, models

from ..models import UpdatedJSONField


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
                ('highest', models.ForeignKey(related_name='+', to='submissions.Score', on_delete=models.CASCADE)),
                ('latest', models.ForeignKey(related_name='+', to='submissions.Score', on_delete=models.CASCADE)),
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
                ('uuid', models.UUIDField(db_index=True, editable=False, blank=True)),
                ('attempt_number', models.PositiveIntegerField()),
                ('submitted_at', models.DateTimeField(default=django.utils.timezone.now, db_index=True)),
                ('created_at', models.DateTimeField(default=django.utils.timezone.now, editable=False, db_index=True)),
                ('answer', UpdatedJSONField(db_column='raw_answer', blank=True)),
                ('student_item', models.ForeignKey(to='submissions.StudentItem', on_delete=models.CASCADE)),
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
            field=models.OneToOneField(to='submissions.StudentItem', on_delete=models.CASCADE),
        ),
        migrations.AddField(
            model_name='score',
            name='student_item',
            field=models.ForeignKey(to='submissions.StudentItem', on_delete=models.CASCADE),
        ),
        migrations.AddField(
            model_name='score',
            name='submission',
            field=models.ForeignKey(to='submissions.Submission', null=True, on_delete=models.CASCADE),
        ),
    ]
