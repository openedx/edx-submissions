"""
Tests for the analyze_uploaded_file_sizes management command.
"""
import ddt
import mock
import datetime as dt
import sys
try:
    from cStringIO import StringIO
except ModuleNotFoundError:
    from io import StringIO
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from ..analyze_uploaded_file_sizes import Command, HEADER
from ....tests.factories import StudentItemFactory, SubmissionFactory
from ....models import Submission
import contextlib


@contextlib.contextmanager
def capture():
    """ Context manager to capture stdout and stderr """
    oldout, olderr = sys.stdout, sys.stderr
    try:
        out = [StringIO(), StringIO()]
        sys.stdout, sys.stderr = out
        yield out
    finally:
        sys.stdout, sys.stderr = oldout, olderr
        out[0] = out[0].getvalue()
        out[1] = out[1].getvalue()


class BaseMixin(object):

    def assert_command_output(self, expected_output, start_date=None, end_date=None):
        """ Run the management command and assert the output """
        with capture() as out:
            if not start_date and not end_date:
                call_command(Command())
            else:
                call_command(Command(), start_date=start_date, end_date=end_date)
        result, _ = self.parse_output(out)
        self.assertDictEqual(result, expected_output)

    def parse_output(self, out):
        """
        Read captured stdout and parse tab limited output table into a dict
        Returns: (<parsed_table>, <list of any lines before the table>)
        """
        lines = out[0].splitlines()
        header_index = lines.index(HEADER)
        preamble = lines[:header_index]
        result = {}
        for line in lines[header_index+1:]:
            cells = line.split('\t')
            result[cells[0]] = (int(cells[1]), int(cells[2]), int(cells[3]))
        return result, preamble

    def create_answer(self, *filesizes):
        return {'files_sizes': filesizes}

    def create_another_submission(
            self,
            submission,
            answer=None,
            same_user=False,
            same_course=False,
            time_delta=None,
    ):
        """
        Creates a new Submission, copying certain fields from the 'base'
        """
        kwargs = {}
        if same_user:
            kwargs['student_id'] = submission.student_item.student_id
        if same_course:
            kwargs['course_id'] = submission.student_item.course_id
        student_item = StudentItemFactory.create(**kwargs)
        created_at = submission.created_at
        new_submission = SubmissionFactory.create(
            student_item=student_item,
            answer=answer if answer else submission.answer,
            created_at=created_at if time_delta is None else created_at + time_delta
        )
        return new_submission


@ddt.ddt
class TestOutput(BaseMixin, TestCase):
    """
    Test that the command correctly processes submissions data
    """

    def test_no_submissions(self):
        self.assert_command_output({})

    def test_empty_submission_only(self):
        SubmissionFactory.create(answer=self.create_answer())
        self.assert_command_output({})

    def test_one_empty_submission(self):
        submission_1 = SubmissionFactory.create(answer=self.create_answer())
        submission_2 = SubmissionFactory.create(answer=self.create_answer(100, 200))
        self.assert_command_output(
            {submission_2.student_item.course_id: (1, 300, 300)}
        )

    @ddt.data([100], [100, 200, 300])
    def test_one_entry(self, filesizes):
        submission = SubmissionFactory.create(answer=self.create_answer(*filesizes))
        total_filesize = sum(filesizes)
        self.assert_command_output(
            {submission.student_item.course_id: (1, total_filesize, total_filesize)}
        )

    def test_one_course_one_learner(self):
        submission = SubmissionFactory.create(answer=self.create_answer(100, 100, 100))
        self.create_another_submission(submission, same_user=True, same_course=True)
        self.create_another_submission(submission, same_user=True, same_course=True)
        self.assert_command_output(
            {submission.student_item.course_id: (1, 900, 900)}
        )

    def test_one_course_multiple_users_one_submission_per(self):
        submission = SubmissionFactory.create(answer=self.create_answer(100, 100, 100, 200))
        self.create_another_submission(submission, same_course=True)
        self.create_another_submission(submission, same_course=True)
        self.assert_command_output(
            {submission.student_item.course_id: (3, 1500, 500)}
        )

    def test_one_course_multiple_users_multiple_submissions(self):
        user_1_submission_1 = SubmissionFactory.create(answer=self.create_answer(100, 100, 100))
        submission = user_1_submission_1
        self.create_another_submission(submission, same_user=True, same_course=True)
        self.create_another_submission(submission, same_course=True)
        user_3_submission_1 = self.create_another_submission(submission, same_course=True)
        self.create_another_submission(user_3_submission_1, same_course=True, same_user=True)
        self.assert_command_output(
            {submission.student_item.course_id: (3, 1500, 500)}
        )

    def test_multiple_courses_one_user(self):
        submission_1 = SubmissionFactory.create(answer=self.create_answer(100, 100, 100))
        submission_2 = self.create_another_submission(submission_1, same_user=True)
        submission_3 = self.create_another_submission(submission_1, same_user=True)
        submission_4 = self.create_another_submission(submission_1, same_user=True)
        self.assert_command_output(
            {
                submission_1.student_item.course_id: (1, 300, 300),
                submission_2.student_item.course_id: (1, 300, 300),
                submission_3.student_item.course_id: (1, 300, 300),
                submission_4.student_item.course_id: (1, 300, 300),
            }
        )

    def test_many_courses(self):
        """
        Five courses, each course has 5000 total bytes
        First course has one user, fifth course has five users
        """

        # 'makes' ten courses
        first_submissions = [
            SubmissionFactory.create(answer=self.create_answer(500, 300, 200)) for _ in range(5)
        ]
        for additional_users, base_submission in enumerate(first_submissions):
            for _ in range(4):
                self.create_another_submission(
                    base_submission,
                    same_course=True,
                    same_user=additional_users > 0
                )
                additional_users -= 1

        expected_output = {
            submission.student_item.course_id: (5 - i, 5000, round(5000 / (5 - i)))
            for i, submission in enumerate(first_submissions)
        }
        self.assert_command_output(expected_output)


@ddt.ddt
class TestDateRange(BaseMixin, TestCase):

    start_date = dt.date(2020, 1, 30)
    start_date_str = '2020-01-30'
    end_date = dt.date(2020, 1, 1)
    end_date_str = '2020-01-01'

    td_month = dt.timedelta(weeks=4)
    td_day = dt.timedelta(days=1)
    td_none = dt.timedelta()

    @ddt.unpack
    @ddt.data((True, 600), (False, 900))
    def test_submission_excluded_same_course_same_user(self, exclude_submission, expected_bytes):
        submission_1 = SubmissionFactory.create(
            created_at=dt.datetime(2020, 1, 3),
            answer=self.create_answer(100, 100, 100)
        )
        self.create_another_submission(
            submission_1,
            same_course=True,
            same_user=True,
            time_delta=self.td_day
        )
        self.create_another_submission(
            submission_1,
            same_course=True,
            same_user=True,
            time_delta=self.td_month if exclude_submission else self.td_day
        )
        self.assert_command_output(
            {submission_1.student_item.course_id: (1, expected_bytes, expected_bytes)},
            start_date=self.start_date,
            end_date=self.end_date,
        )

    @ddt.unpack
    @ddt.data((True, 2, 600), (False, 3, 900))
    def test_submission_excluded_same_course_different_user(
        self, exclude_submission, expected_users, expected_bytes
    ):
        submission_1 = SubmissionFactory.create(
            created_at=dt.datetime(2020, 1, 3),
            answer=self.create_answer(100, 100, 100)
        )
        self.create_another_submission(
            submission_1,
            same_course=True,
            time_delta=self.td_day
        )
        self.create_another_submission(
            submission_1,
            same_course=True,
            time_delta=self.td_month if exclude_submission else self.td_day
        )
        self.assert_command_output(
            {submission_1.student_item.course_id: (expected_users, expected_bytes, 300)},
            start_date=self.start_date,
            end_date=self.end_date,
        )

    @ddt.data(True, False)
    def test_entire_course_out_of_range(self, exclude_course):
        course_1_submission = SubmissionFactory.create(
            created_at=dt.datetime(2020, 1, 3),
            answer=self.create_answer(100, 100, 100)
        )
        self.create_another_submission(
            course_1_submission,
            same_course=True,
        )
        self.create_another_submission(
            course_1_submission,
            same_course=True,
        )

        if exclude_course:
            created_at = dt.datetime(2019, 12, 1)
        else:
            created_at = dt.datetime(2020, 1, 3)
        course_2_submission = SubmissionFactory.create(
            created_at=created_at,
            answer=self.create_answer(500, 200)
        )
        self.create_another_submission(
            course_2_submission,
            same_course=True,
        )

        expected_output = {
            course_1_submission.student_item.course_id: (3, 900, 300)
        }
        if not exclude_course:
            expected_output[course_2_submission.student_item.course_id] = (2, 1400, 700)

        self.assert_command_output(
            expected_output,
            start_date=self.start_date,
            end_date=self.end_date,
        )
