"""
Command to update all instances of old-style (hyphenated) uuid values in the
submissions_submission table.

This command takes a long time to execute, please run it on a long-lived
background worker. The model code is resilient to both styles of uuid, this
command just standardizes them all to be similar.

EDUCATOR-1090
"""

import logging
import time

from django.core.management.base import BaseCommand
from django.db import transaction

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
            help=u"The Submission.id at which to begin updating rows. 0 by default."
        )
        parser.add_argument(
            '--chunk', '-c',
            default=1000,
            help=u"Batch size, how many rows to update in a given transaction. Default 1000.",
        )
        parser.add_argument(
            '--wait', '-w',
            default=2,
            help=u"Wait time between transactions, in seconds. Default 2.",
        )

    def handle(self, *args, **options):
        """
        By default, we're going to do this in chunks. This way, if there ends up being an error,
        we can check log messages and continue from that point after fixing the issue.
        """
        total_len = Submission.objects.count()
        log.info("Beginning uuid update, {} rows exist in total".format(total_len))

        current = options['start'];
        while current < total_len:
            end_chunk = current + options['chunk'] if total_len - options['chunk'] >= current else total_len
            log.info("Updating entries in range [{}, {})".format(current, end_chunk))
            with transaction.atomic():
                for submission in Submission.objects.filter(id__gte=current, id__lt=end_chunk).iterator():
                    submission.save(update_fields=['uuid'])
            time.sleep(options['wait'])
            current = current + options['chunk']
