"""
Command to update all instances of old-style (hyphenated) uuid values in the
submissions_submission table.

This command takes a long time to execute, please run it on a long-lived
background worker. The model code is resilient to both styles of uuid, this
command just standardizes them all to be similar.

EDUCATOR-1090
"""

import logging

from django.core.management.base import BaseCommand
from django.db import transaction

from submissions.models import Submission

log = logging.getLogger(__name__)

class Command(BaseCommand):
    """
    Example usage: ./manage.py lms --settings=devstack update_submissions_uuids.py
    """
    help = 'Loads and saves all Submissions objects to force new non-hyphenated uuid values on disk.'

    def handle(self, *args, **options):
        """
        By default, we're going to do this in chunks. This way, if there ends up being an error,
        we can check log messages and continue from that point after fixing the issue.
        """
        START_VALUE = 0
        CHUNK_SIZE = 1000
        total_len = Submission.objects.count()
        log.info("Beginning uuid update, {} rows exist in total")

        current = START_VALUE;
        while current < total_len:
            end_chunk = current + CHUNK_SIZE
            log.info("Updating entries {} to {}".format(current, end_chunk))
            with transaction.atomic():
                for submission in Submission.objects.filter(id__gte=current, id__lt=end_chunk).iterator():
                    submission.save(update_fields=['uuid'])
            current = current + CHUNK_SIZE
