# -*- coding: utf-8 -*-
from __future__ import absolute_import, unicode_literals

from django.db import migrations, models

import submissions.models


class Migration(migrations.Migration):

    dependencies = [
        ('submissions', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='ScoreAnnotation',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('annotation_type', models.CharField(max_length=255, db_index=True)),
                ('creator', submissions.models.AnonymizedUserIDField()),
                ('reason', models.TextField()),
                ('score', models.ForeignKey(to='submissions.Score', on_delete=models.CASCADE)),
            ],
        ),
        migrations.AlterField(
            model_name='studentitem',
            name='student_id',
            field=submissions.models.AnonymizedUserIDField(),
        ),
    ]
