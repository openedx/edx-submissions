"""
Test API calls using the read replica.
"""
from __future__ import absolute_import
import copy

from django.conf import settings
from django.test import TransactionTestCase
import mock

from submissions import api as sub_api


def _mock_use_read_replica(queryset):
    """
    The Django DATABASES setting TEST_MIRROR isn't reliable.
    See: https://code.djangoproject.com/ticket/23718
    """
    return (
        queryset.using('default')
        if 'read_replica' in settings.DATABASES
        else queryset
    )

class ReadReplicaTest(TransactionTestCase):
    """ Test queries that use the read replica. """
    STUDENT_ITEM = {
        "student_id": "test student",
        "course_id": "test course",
        "item_id": "test item",
        "item_type": "test type"
    }

    SCORE = {
        "points_earned": 3,
        "points_possible": 5
    }

    def setUp(self):
        """ Create a submission and score. """
        self.submission = sub_api.create_submission(self.STUDENT_ITEM, "test answer")
        self.score = sub_api.set_score(
            self.submission['uuid'],
            self.SCORE["points_earned"],
            self.SCORE["points_possible"]
        )

    def test_get_submission_and_student(self):
        with mock.patch('submissions.api._use_read_replica', _mock_use_read_replica):
            retrieved = sub_api.get_submission_and_student(self.submission['uuid'], read_replica=True)
            expected = copy.deepcopy(self.submission)
            expected['student_item'] = copy.deepcopy(self.STUDENT_ITEM)
            self.assertEqual(retrieved, expected)

    def test_get_latest_score_for_submission(self):
        with mock.patch('submissions.api._use_read_replica', _mock_use_read_replica):
            retrieved = sub_api.get_latest_score_for_submission(self.submission['uuid'], read_replica=True)
            self.assertEqual(retrieved['points_possible'], self.SCORE['points_possible'])
            self.assertEqual(retrieved['points_earned'], self.SCORE['points_earned'])

    def test_get_top_submissions(self):
        student_item_1 = copy.deepcopy(self.STUDENT_ITEM)
        student_item_1['student_id'] = 'Tim'

        student_item_2 = copy.deepcopy(self.STUDENT_ITEM)
        student_item_2['student_id'] = 'Bob'

        student_item_3 = copy.deepcopy(self.STUDENT_ITEM)
        student_item_3['student_id'] = 'Li'

        student_1 = sub_api.create_submission(student_item_1, "Hello World")
        student_2 = sub_api.create_submission(student_item_2, "Hello World")
        student_3 = sub_api.create_submission(student_item_3, "Hello World")

        sub_api.set_score(student_1['uuid'], 8, 10)
        sub_api.set_score(student_2['uuid'], 4, 10)
        sub_api.set_score(student_3['uuid'], 2, 10)

        # Use the read-replica
        with mock.patch('submissions.api._use_read_replica', _mock_use_read_replica):
            top_scores = sub_api.get_top_submissions(
                self.STUDENT_ITEM['course_id'],
                self.STUDENT_ITEM['item_id'],
                self.STUDENT_ITEM['item_type'], 2,
                read_replica=True
            )
            self.assertEqual(
                top_scores,
                [
                    {
                        'content': "Hello World",
                        'score': 8
                    },
                    {
                        'content': "Hello World",
                        'score': 4
                    },
                ]
            )
