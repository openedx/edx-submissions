"""
Command to update all instances of old-style (hyphenated) uuid values in the
submissions_submission table.

This command takes a long time to execute, please run it on a long-lived
background worker. The model code is resilient to both styles of uuid, this
command just standardizes them all to be similar.

EDUCATOR-1090
"""

from __future__ import absolute_import

import logging
import time

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Max

from submissions.models import Submission

log = logging.getLogger(__name__)


class Command(BaseCommand):
    """
    Example usage: ./manage.py lms --settings=devstack update_submissions_uuids.py
    """
    help = 'Loads and saves all Submissions objects to force new non-hyphenated uuid values on disk.'

    def add_arguments(self, parser):
        """
        Add arguments to the command parser.

        Uses argparse syntax.  See documentation at
        https://docs.python.org/3/library/argparse.html.
        """
        parser.add_argument(
            '--start', '-s',
            default=0,
            type=int,
            help=u"The Submission.id at which to begin updating rows. 0 by default."
        )
        parser.add_argument(
            '--chunk', '-c',
            default=1000,
            type=int,
            help=u"Batch size, how many rows to update in a given transaction. Default 1000.",
        )
        parser.add_argument(
            '--wait', '-w',
            default=2,
            type=int,
            help=u"Wait time between transactions, in seconds. Default 2.",
        )

    def handle(self, *args, **options):
        """
        By default, we're going to do this in chunks. This way, if there ends up being an error,
        we can check log messages and continue from that point after fixing the issue.
        """
        # Note that by taking last_id here, we're going to miss any submissions created *during* the command execution
        # But that's okay! All new entries have already been created using the new style, no acion needed there
        # pylint: disable=protected-access
        last_id = Submission._objects.all().aggregate(Max('id'))['id__max']
        log.info("Beginning uuid update")

        current = options['start']
        while current < last_id:
            end_chunk = current + options['chunk'] if last_id - options['chunk'] >= current else last_id
            log.info("Updating entries in range [{}, {}]".format(current, end_chunk))
            with transaction.atomic():
                # pylint: disable=protected-access
                for submission in Submission._objects.filter(id__gte=current, id__lte=end_chunk).iterator():
                    submission.save(update_fields=['uuid'])
            time.sleep(options['wait'])
            current = end_chunk + 1
