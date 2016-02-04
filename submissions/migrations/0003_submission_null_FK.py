# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('submissions', '0002_auto_20151119_0913'),
    ]

    operations = [
        migrations.AlterField(
            model_name='submission',
            name='student_item',
            field=models.ForeignKey(to='submissions.StudentItem', null=True, default=1),
            preserve_default=False
        ),
    ]
