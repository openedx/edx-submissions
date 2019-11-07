"""
Management command to analyze recently-uploaded files and create a report containing:

Per course:
    1) total bytes of files uploaded
    2) count of users who have uploaded a file
    3) rough bytes-per-user, #1 divided by #2

This report is printed to stdout with a header and values as a tabbed stream.

Arguments:
    -start_date (optional): The most recent day to include in the report. Defaults to today.
    -end_date (optional): The longest-ago day to include in the report.
                          Defaults to <today - 30 days>.
                          The maximum value for this argument is 2019-11-01.
                          Before this day, file size data is unavailable.

    both arguments must be in the form yyyy-mm-dd
"""

from __future__ import absolute_import

import datetime
import json

from django.core.management.base import BaseCommand, CommandError

from submissions.models import Submission

DATE_FORMAT = '%Y-%m-%d'
LAST_DATE = datetime.date(2019, 11, 1)
HEADER = u'Course ID\tUsers with Uploaded Files\tTotal Uploaded Bytes\tAverage Upload per User'


class Command(BaseCommand):
    """
    Example usage:

        ./manage.py lms analyze_uploaded_file_sizes --start_date=2020-01-30 --end_date=2019-12-31

    """
    help = u'Collects and prints stats about ORA file upload usage'

    def add_arguments(self, parser):
        """
        Add arguments to the command parser.
        """
        today = datetime.date.today()
        thirty_days = datetime.timedelta(days=30)
        thirty_days_ago = today - thirty_days

        def parse_date(s):
            datetime.datetime.strptime(s, DATE_FORMAT).date()

        parser.add_argument(
            '--start_date',
            type=parse_date,
            default=today,
            help=u"The most recent day to include in the report. Defaults to today."
        )
        parser.add_argument(
            '--end_date',
            type=parse_date,
            default=thirty_days_ago,
            help=(u"The longest-ago day to include in the report. Defaults to <today - 30 days>. "
                  u"Cannot be set to before 2019-11-01.")
        )

    # pylint: disable=arguments-differ, unused-argument
    def handle(self, start_date, end_date, *args, **options):
        """
        Analyze ORA file upload submissions and and print tab-limited report
        """
        print(u'Starting file upload submission report')
        arg_echo_str = u'start_date = {}, end_date = {}'.format(
            start_date.strftime(DATE_FORMAT),
            end_date.strftime(DATE_FORMAT)
        )
        print(arg_echo_str)
        end_date = self.validate_input_dates(start_date, end_date)
        submission_data = self.load_data(start_date, end_date)
        self.print_report(submission_data)

    def validate_input_dates(self, start_date, end_date):
        """
        Checks the validity of start_date and end_date
        Checks that the end date is not before LAST_DATE, and if it is, overrides it.
        """
        if start_date < end_date:
            raise CommandError("End date must be before start date")
        if datetime.date.today() < start_date:
            print(u"Warning: start_date is in the future")
        if end_date < LAST_DATE:
            print(u'File size data is unavailable before 2019-11-01. Setting end_date to 2019-11-01')
            return LAST_DATE
        return end_date

    def load_data(self, start_date, end_date):
        """ Load the uploaded file data from the database """
        # The model fields are datetimes, we need to make sure we
        # include everything that was submitted in that day
        end_datetime = self.beginning_of_day(end_date)
        start_datetime = self.end_of_day(start_date)

        return Submission.objects.filter(
            created_at__range=(end_datetime, start_datetime),
            student_item__item_type='openassessment',
            answer__contains='files_sizes":['
        ).order_by(
            'student_item__course_id',
            'student_item__student_id'
        ).select_related('student_item').values_list(
            'student_item__course_id',
            'student_item__student_id',
            'answer',
        )

    def beginning_of_day(self, dt):
        """ Given a datetime, return a datetime that represents the first second of that day """
        return datetime.datetime.combine(dt, datetime.time.min)

    def end_of_day(self, dt):
        """ Given a datetime, return a datetime that represents the last second of that day """
        return datetime.datetime.combine(dt, datetime.time.max)

    def print_report(self, submission_data):
        """ Crunch numbers, print results """
        print(HEADER)
        course_bytes = 0
        users = set()
        prev_course_id = None

        for course_id, student_id, answer in submission_data:
            answer = json.loads(answer)
            if course_id != prev_course_id and prev_course_id is not None:
                self.print_row(prev_course_id, users, course_bytes)
                course_bytes = 0
                users = set()
            user_submission_bytes = sum(answer['files_sizes'])
            if user_submission_bytes:
                users.add(student_id)
                course_bytes += user_submission_bytes
            prev_course_id = course_id

        if prev_course_id:
            self.print_row(prev_course_id, users, course_bytes)

    def print_row(self, course_id, users, course_bytes):
        """ Print a row of the report """
        num_users = len(users)
        if users or course_bytes:
            print(u"{course_id}\t{num_users}\t{total_bytes}\t{avg_bytes:.0f}".format(
                course_id=course_id,
                num_users=num_users,
                total_bytes=course_bytes,
                avg_bytes=course_bytes/num_users if num_users != 0 else 0
            ))
