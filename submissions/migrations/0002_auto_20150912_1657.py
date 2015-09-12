# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('submissions', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='scoresummary',
            name='student_item',
            field=models.OneToOneField(to='submissions.StudentItem'),
        ),
    ]
