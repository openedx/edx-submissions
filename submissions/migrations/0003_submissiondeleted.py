# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models
import django.utils.timezone
import jsonfield.fields
import django_extensions.db.fields


class Migration(migrations.Migration):

    dependencies = [
        ('submissions', '0002_auto_20151119_0913'),
    ]

    operations = [
        migrations.CreateModel(
            name='SubmissionDeleted',
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
                'abstract': False,
            },
        ),
    ]
