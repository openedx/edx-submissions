"""
Management command to analyze recently-uploaded files and create a report containing:

Per course:
    1) total bytes of files uploaded
    2) count of users who have uploaded a file
    3) rough bytes-per-user, #1 divided by #2

This report is printed to stdout with a header and values as a tabbed stream.

Arguments:
    -max_date (optional): The most recent day to include in the report. Defaults to today.
    -min_date (optional): The longest-ago day to include in the report.
                          Defaults to <today - 30 days>.
                          The maximum value for this argument is 2019-11-01.
                          Before this day, file size data is unavailable.

    both arguments must be in the form yyyy-mm-dd
    The two dates cannot be more than 90 days apart.
"""

from __future__ import absolute_import

import datetime

from django.core.management.base import BaseCommand, CommandError

from submissions.models import Submission

DATE_FORMAT = '%Y-%m-%d'
EARLIEST_ALLOWED_DATE = datetime.date(2019, 11, 1)
EARLIEST_ALLOWED_DATE_STR = EARLIEST_ALLOWED_DATE.strftime(DATE_FORMAT)
HEADER = u'Course ID\tUsers with Uploaded Files\tTotal Uploaded Bytes\tAverage Upload per User'


class Command(BaseCommand):
    """
    Example usage:

        ./manage.py lms analyze_uploaded_file_sizes --max_date=2020-01-30 --min_date=2019-12-31

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
            '--min_date',
            type=parse_date,
            default=thirty_days_ago,
            help=(u"The longest-ago day to include in the report. Defaults to <today - 30 days>. "
                  u"Cannot be set to before 2019-11-01.")
        )
        parser.add_argument(
            '--max_date',
            type=parse_date,
            default=today,
            help=u"The most recent day to include in the report. Defaults to today."
        )

    # pylint: disable=arguments-differ
    def handle(self, min_date, max_date, *args, **options):
        """
        Analyze ORA file upload submissions and and print tab-limited report
        """
        print(u'Starting file upload submission report')
        arg_echo_str = u'min_date = {}, max_date = {}'.format(
            min_date.strftime(DATE_FORMAT),
            max_date.strftime(DATE_FORMAT)
        )
        print(arg_echo_str)
        min_date = self.validate_input_dates(min_date, max_date)
        submission_data = self.load_data(min_date, max_date)
        print(HEADER)
        for course_row in self.parse_submission_data_by_course(submission_data):
            course_id, num_users, course_bytes = course_row
            self.print_row(course_id, num_users, course_bytes)

    def validate_input_dates(self, min_date, max_date):
        """
        Checks the validity of min_date and max_date
        Checks that the end date is not before LAST_DATE, and if it is, overrides it.
        """
        if max_date < min_date:
            raise CommandError("Max date must be less than (before) start date")
        if max_date - min_date > datetime.timedelta(days=90):
            raise CommandError("Max date and min date cannot be more than 90 days apart")
        if datetime.date.today() < max_date:
            print(u"Warning: max_date is in the future")
        if min_date < EARLIEST_ALLOWED_DATE:
            msg = u'File size data is unavailable before {earliest}. Setting min_date to {earliest}'
            print(msg.format(earliest=EARLIEST_ALLOWED_DATE_STR))
            return EARLIEST_ALLOWED_DATE
        return min_date

    def load_data(self, min_date, max_date):
        """ Load the uploaded file data from the database """
        # The model fields are datetimes, we need to make sure we
        # include everything that was submitted in that day
        min_datetime = self.beginning_of_day(min_date)
        max_datetime = self.end_of_day(max_date)

        return Submission.objects.filter(
            created_at__range=(min_datetime, max_datetime),
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

    def parse_submission_data_by_course(self, submission_data):
        """
        Groups submission_data by course

        Generates:
            (<course_id>, <number of users with uploaded files>, <total bytes uploaded in course>)
            for each course
        """
        course_bytes = 0
        users = set()
        prev_course_id = None

        for course_id, student_id, answer in submission_data:
            if course_id != prev_course_id and prev_course_id is not None:
                yield prev_course_id, len(users), course_bytes
                course_bytes = 0
                users = set()
            user_submission_bytes = sum(answer['files_sizes'])
            if user_submission_bytes:
                users.add(student_id)
                course_bytes += user_submission_bytes
            prev_course_id = course_id

        if prev_course_id:
            yield prev_course_id, len(users), course_bytes

    def print_row(self, course_id, num_course_users, course_bytes):
        """ Print a row of the report """
        if num_course_users or course_bytes:
            print(u"{course_id}\t{num_users}\t{total_bytes}\t{avg_bytes:.0f}".format(
                course_id=course_id,
                num_users=num_course_users,
                total_bytes=course_bytes,
                avg_bytes=course_bytes/num_course_users if num_course_users != 0 else 0
            ))
