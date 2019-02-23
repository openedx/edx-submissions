"""
Test reset scores.
"""

from __future__ import absolute_import
import copy
from mock import patch
from datetime import datetime
from django.test import TestCase
import ddt
from django.core.cache import cache
from django.db import DatabaseError
from django.dispatch import Signal
from freezegun import freeze_time
from submissions import api as sub_api
from submissions.models import Score, score_reset
import pytz


@ddt.ddt
class TestResetScore(TestCase):
    """
    Test resetting scores for a specific student on a specific problem.
    """

    STUDENT_ITEM = {
        'student_id': 'Test student',
        'course_id': 'Test course',
        'item_id': 'Test item',
        'item_type': 'Test item type',
    }

    def setUp(self):
        """
        Clear the cache.
        """
        cache.clear()

    def test_reset_with_no_scores(self):
        sub_api.reset_score(
            self.STUDENT_ITEM['student_id'],
            self.STUDENT_ITEM['course_id'],
            self.STUDENT_ITEM['item_id'],
        )
        self.assertIs(sub_api.get_score(self.STUDENT_ITEM), None)

        scores = sub_api.get_scores(self.STUDENT_ITEM['course_id'], self.STUDENT_ITEM['student_id'])
        self.assertEqual(len(scores), 0)

    def test_reset_with_one_score(self):
        # Create a submission for the student and score it
        submission = sub_api.create_submission(self.STUDENT_ITEM, 'test answer')
        sub_api.set_score(submission['uuid'], 1, 2)

        # Reset scores
        sub_api.reset_score(
            self.STUDENT_ITEM['student_id'],
            self.STUDENT_ITEM['course_id'],
            self.STUDENT_ITEM['item_id'],
        )

        # Expect that no scores are available for the student
        self.assertIs(sub_api.get_score(self.STUDENT_ITEM), None)
        scores = sub_api.get_scores(self.STUDENT_ITEM['course_id'], self.STUDENT_ITEM['student_id'])
        self.assertEqual(len(scores), 0)

    def test_reset_with_multiple_scores(self):
        # Create a submission for the student and score it
        submission = sub_api.create_submission(self.STUDENT_ITEM, 'test answer')
        sub_api.set_score(submission['uuid'], 1, 2)
        sub_api.set_score(submission['uuid'], 2, 2)

        # Reset scores
        sub_api.reset_score(
            self.STUDENT_ITEM['student_id'],
            self.STUDENT_ITEM['course_id'],
            self.STUDENT_ITEM['item_id'],
        )

        # Expect that no scores are available for the student
        self.assertIs(sub_api.get_score(self.STUDENT_ITEM), None)
        scores = sub_api.get_scores(self.STUDENT_ITEM['course_id'], self.STUDENT_ITEM['student_id'])
        self.assertEqual(len(scores), 0)

    @ddt.data(
        {'student_id': 'other student'},
        {'course_id': 'other course'},
        {'item_id': 'other item'},
    )
    def test_reset_different_student_item(self, changed):
        # Create a submissions for two students
        submission = sub_api.create_submission(self.STUDENT_ITEM, 'test answer')
        sub_api.set_score(submission['uuid'], 1, 2)

        other_student = copy.copy(self.STUDENT_ITEM)
        other_student.update(changed)
        submission = sub_api.create_submission(other_student, 'other test answer')
        sub_api.set_score(submission['uuid'], 3, 4)

        # Reset the score for the first student
        sub_api.reset_score(
            self.STUDENT_ITEM['student_id'],
            self.STUDENT_ITEM['course_id'],
            self.STUDENT_ITEM['item_id'],
        )

        # The first student's scores should be reset
        self.assertIs(sub_api.get_score(self.STUDENT_ITEM), None)
        scores = sub_api.get_scores(self.STUDENT_ITEM['course_id'], self.STUDENT_ITEM['student_id'])
        self.assertNotIn(self.STUDENT_ITEM['item_id'], scores)

        # But the second student should still have a score
        score = sub_api.get_score(other_student)
        self.assertEqual(score['points_earned'], 3)
        self.assertEqual(score['points_possible'], 4)
        scores = sub_api.get_scores(other_student['course_id'], other_student['student_id'])
        self.assertIn(other_student['item_id'], scores)

    def test_reset_then_add_score(self):
        # Create a submission for the student and score it
        submission = sub_api.create_submission(self.STUDENT_ITEM, 'test answer')
        sub_api.set_score(submission['uuid'], 1, 2)

        # Reset scores
        sub_api.reset_score(
            self.STUDENT_ITEM['student_id'],
            self.STUDENT_ITEM['course_id'],
            self.STUDENT_ITEM['item_id'],
        )

        # Score the student again
        sub_api.set_score(submission['uuid'], 3, 4)

        # Expect that the new score is available
        score = sub_api.get_score(self.STUDENT_ITEM)
        self.assertEqual(score['points_earned'], 3)
        self.assertEqual(score['points_possible'], 4)

        scores = sub_api.get_scores(self.STUDENT_ITEM['course_id'], self.STUDENT_ITEM['student_id'])
        self.assertIn(self.STUDENT_ITEM['item_id'], scores)
        item_score = scores[self.STUDENT_ITEM['item_id']]
        self.assertEqual((item_score['points_earned'], item_score['points_possible']), (3, 4))

    def test_reset_then_get_score_for_submission(self):
        # Create a submission for the student and score it
        submission = sub_api.create_submission(self.STUDENT_ITEM, 'test answer')
        sub_api.set_score(submission['uuid'], 1, 2)

        # Reset scores
        sub_api.reset_score(
            self.STUDENT_ITEM['student_id'],
            self.STUDENT_ITEM['course_id'],
            self.STUDENT_ITEM['item_id'],
        )

        # If we're retrieving the score for a particular submission,
        # instead of a student item, then we should STILL get a score.
        self.assertIsNot(sub_api.get_latest_score_for_submission(submission['uuid']), None)

    @patch.object(Score.objects, 'create')
    def test_database_error(self, create_mock):
        # Create a submission for the student and score it
        submission = sub_api.create_submission(self.STUDENT_ITEM, 'test answer')
        sub_api.set_score(submission['uuid'], 1, 2)

        # Simulate a database error when creating the reset score
        create_mock.side_effect = DatabaseError("Test error")
        with self.assertRaises(sub_api.SubmissionInternalError):
            sub_api.reset_score(
                self.STUDENT_ITEM['student_id'],
                self.STUDENT_ITEM['course_id'],
                self.STUDENT_ITEM['item_id'],
            )

    @freeze_time(datetime.now())
    @patch.object(score_reset, 'send')
    def test_reset_score_signal(self, send_mock):
        # Create a submission for the student and score it
        submission = sub_api.create_submission(self.STUDENT_ITEM, 'test answer')
        sub_api.set_score(submission['uuid'], 1, 2)

        # Reset scores
        sub_api.reset_score(
            self.STUDENT_ITEM['student_id'],
            self.STUDENT_ITEM['course_id'],
            self.STUDENT_ITEM['item_id'],
        )

        # Verify that the send method was properly called
        send_mock.assert_called_with(
            sender=None,
            anonymous_user_id=self.STUDENT_ITEM['student_id'],
            course_id=self.STUDENT_ITEM['course_id'],
            item_id=self.STUDENT_ITEM['item_id'],
            created_at=datetime.now().replace(tzinfo=pytz.UTC),
        )
