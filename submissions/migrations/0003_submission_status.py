# -*- coding: utf-8 -*-
from __future__ import absolute_import, unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('submissions', '0002_auto_20151119_0913'),
    ]

    operations = [
        migrations.AddField(
            model_name='submission',
            name='status',
            field=models.CharField(default='A', max_length=1, choices=[('D', 'Deleted'), ('A', 'Active')]),
        ),
    ]
