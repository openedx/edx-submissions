"""
Tests for submission models.
"""

from __future__ import absolute_import

from datetime import datetime

import pytest
from django.contrib.auth.models import User
from django.test import TestCase
from pytz import UTC

from submissions.models import (
    DuplicateTeamSubmissionsError,
    Score,
    ScoreSummary,
    StudentItem,
    Submission,
    TeamSubmission
)


class TestScoreSummary(TestCase):
    """
    Test selection of options from a rubric.
    """

    def test_latest(self):
        item = StudentItem.objects.create(
            student_id="score_test_student",
            course_id="score_test_course",
            item_id="i4x://mycourse/class_participation.section_attendance"
        )
        Score.objects.create(
            student_item=item,
            submission=None,
            points_earned=8,
            points_possible=10,
        )
        second_score = Score.objects.create(
            student_item=item,
            submission=None,
            points_earned=5,
            points_possible=10,
        )
        latest_score = ScoreSummary.objects.get(student_item=item).latest
        self.assertEqual(second_score, latest_score)

    def test_highest(self):
        item = StudentItem.objects.create(
            student_id="score_test_student",
            course_id="score_test_course",
            item_id="i4x://mycourse/special_presentation"
        )

        # Low score is higher than no score...
        low_score = Score.objects.create(
            student_item=item,
            points_earned=0,
            points_possible=0,
        )
        self.assertEqual(
            low_score,
            ScoreSummary.objects.get(student_item=item).highest
        )

        # Medium score should supplant low score
        med_score = Score.objects.create(
            student_item=item,
            points_earned=8,
            points_possible=10,
        )
        self.assertEqual(
            med_score,
            ScoreSummary.objects.get(student_item=item).highest
        )

        # Even though the points_earned is higher in the med_score, high_score
        # should win because it's 4/4 as opposed to 8/10.
        high_score = Score.objects.create(
            student_item=item,
            points_earned=4,
            points_possible=4,
        )
        self.assertEqual(
            high_score,
            ScoreSummary.objects.get(student_item=item).highest
        )

        # Put another medium score to make sure it doesn't get set back down
        med_score2 = Score.objects.create(
            student_item=item,
            points_earned=5,
            points_possible=10,
        )
        self.assertEqual(
            high_score,
            ScoreSummary.objects.get(student_item=item).highest
        )
        self.assertEqual(
            med_score2,
            ScoreSummary.objects.get(student_item=item).latest
        )

    def test_reset_score_highest(self):
        item = StudentItem.objects.create(
            student_id="score_test_student",
            course_id="score_test_course",
            item_id="i4x://mycourse/special_presentation"
        )

        # Reset score with no score
        Score.create_reset_score(item)
        highest = ScoreSummary.objects.get(student_item=item).highest
        self.assertEqual(highest.points_earned, 0)
        self.assertEqual(highest.points_possible, 0)

        # Non-reset score after a reset score
        submission = Submission.objects.create(student_item=item, attempt_number=1)
        Score.objects.create(
            student_item=item,
            submission=submission,
            points_earned=2,
            points_possible=3,
        )
        highest = ScoreSummary.objects.get(student_item=item).highest
        self.assertEqual(highest.points_earned, 2)
        self.assertEqual(highest.points_possible, 3)

        # Reset score after a non-reset score
        Score.create_reset_score(item)
        highest = ScoreSummary.objects.get(student_item=item).highest
        self.assertEqual(highest.points_earned, 0)
        self.assertEqual(highest.points_possible, 0)

    def test_highest_score_hidden(self):
        item = StudentItem.objects.create(
            student_id="score_test_student",
            course_id="score_test_course",
            item_id="i4x://mycourse/special_presentation"
        )

        # Score with points possible set to 0
        # (by convention a "hidden" score)
        submission = Submission.objects.create(student_item=item, attempt_number=1)
        Score.objects.create(
            student_item=item,
            submission=submission,
            points_earned=0,
            points_possible=0,
        )
        highest = ScoreSummary.objects.get(student_item=item).highest
        self.assertEqual(highest.points_earned, 0)
        self.assertEqual(highest.points_possible, 0)

        # Score with points
        submission = Submission.objects.create(student_item=item, attempt_number=1)
        Score.objects.create(
            student_item=item,
            submission=submission,
            points_earned=1,
            points_possible=2,
        )
        highest = ScoreSummary.objects.get(student_item=item).highest
        self.assertEqual(highest.points_earned, 1)
        self.assertEqual(highest.points_possible, 2)

        # Another score with points possible set to 0
        # The previous score should remain the highest score.
        submission = Submission.objects.create(student_item=item, attempt_number=1)
        Score.objects.create(
            student_item=item,
            submission=submission,
            points_earned=0,
            points_possible=0,
        )
        highest = ScoreSummary.objects.get(student_item=item).highest
        self.assertEqual(highest.points_earned, 1)
        self.assertEqual(highest.points_possible, 2)


class TestTeamSubmission(TestCase):
    """
    Test the TeamSubmission class
    """

    @classmethod
    def setUpTestData(cls):
        cls.user = cls.create_user('user1')
        cls.default_team_id = 'team1'
        cls.default_Course_id = 'c1'
        cls.defaullt_item_id = 'i1'
        cls.default_attempt_number = 1
        cls.default_submission = cls.create_team_submission(user=cls.user)
        super().setUpTestData()

    def test_create_team_submission(self):
        # force evaluation of __str__ to ensure there are no issues with the class, since there
        # isn't much specific to assert.
        self.assertNotEqual(self.default_submission.__str__, None)

    def test_create_duplicate_team_submission_not_allowed(self):
        with pytest.raises(DuplicateTeamSubmissionsError):
            TestTeamSubmission.create_team_submission(user=self.user)

    @staticmethod
    def create_user(username):
        return User.objects.create(
            username=username,
            password='secret',
            first_name='fname',
            last_name='lname',
            is_staff=False,
            is_active=True,
            last_login=datetime(2012, 1, 1, tzinfo=UTC),
            date_joined=datetime(2011, 1, 1, tzinfo=UTC)
        )

    @staticmethod
    def create_team_submission(user, team_id='team1', course_id='c1', item_id='i1', attempt_number=1):
        return TeamSubmission.objects.create(
            submitted_by=user,
            team_id=team_id,
            course_id=course_id,
            item_id=item_id,
            attempt_number=attempt_number
        )
