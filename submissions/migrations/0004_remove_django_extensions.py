# -*- coding: utf-8 -*-
from __future__ import absolute_import, unicode_literals

import uuid

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('submissions', '0003_submission_status'),
    ]

    operations = [
        migrations.AlterField(
            model_name='submission',
            name='uuid',
            field=models.UUIDField(default=uuid.uuid4, db_index=True),
        ),
    ]
