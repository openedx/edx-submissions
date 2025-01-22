"""
Tests for submission models.
"""
import time
from datetime import datetime, timedelta
from unittest import mock
from unittest.mock import patch

import pytest
from django.contrib import auth
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.utils.timezone import now
from pytz import UTC

from submissions.errors import TeamSubmissionInternalError, TeamSubmissionNotFoundError
from submissions.models import (
    DELETED,
    DuplicateTeamSubmissionsError,
    ExternalGraderDetail,
    Score,
    ScoreSummary,
    StudentItem,
    Submission,
    SubmissionFile,
    TeamSubmission,
    _get_storage_cached,
    get_storage
)

User = auth.get_user_model()


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
    default_team_id = 'team1'
    default_course_id = 'c1'
    default_item_id = 'i1'
    default_attempt_number = 1

    other_item_id = 'some_other_item'

    other_course_id = 'MIT/PerpetualMotion/Fall2020'

    @classmethod
    def setUpTestData(cls):
        cls.user = cls.create_user('user1')
        cls.default_submission = cls.create_team_submission(user=cls.user)
        super().setUpTestData()

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

    def test_create_duplicate_team_submission_not_allowed(self):
        with pytest.raises(DuplicateTeamSubmissionsError):
            TestTeamSubmission.create_team_submission(user=self.user)

    def test_get_team_submission_by_uuid(self):
        team_submission = TeamSubmission.get_team_submission_by_uuid(self.default_submission.uuid)
        self.assertEqual(team_submission.id, self.default_submission.id)

    def test_get_team_submission_by_uuid_nonexistant(self):
        fake_uuid = 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee'
        with self.assertRaises(TeamSubmissionNotFoundError):
            TeamSubmission.get_team_submission_by_uuid(fake_uuid)

    @mock.patch('submissions.models.TeamSubmission.SoftDeletedManager.get_queryset')
    def test_get_team_submission_by_uuid_error(self, mocked_qs):
        mocked_qs.side_effect = Exception()
        with self.assertRaises(TeamSubmissionInternalError):
            TeamSubmission.get_team_submission_by_uuid(self.default_submission.uuid)

    def test_get_team_submission_by_course_item_team(self):
        team_submission = TeamSubmission.get_team_submission_by_course_item_team(
            self.default_course_id,
            self.default_item_id,
            self.default_team_id
        )
        self.assertEqual(team_submission.id, self.default_submission.id)

    def test_get_team_submission_by_course_item_team_nonexistant(self):
        with self.assertRaises(TeamSubmissionNotFoundError):
            TeamSubmission.get_team_submission_by_course_item_team(
                self.other_course_id,
                self.other_item_id,
                'some_other_team',
            )

    @mock.patch('submissions.models.TeamSubmission.SoftDeletedManager.get_queryset')
    def test_get_team_submission_by_course_item_team_error(self, mocked_qs):
        mocked_qs.side_effect = Exception()
        with self.assertRaises(TeamSubmissionInternalError):
            TeamSubmission.get_team_submission_by_course_item_team(
                self.default_course_id,
                self.default_item_id,
                self.default_team_id
            )

    def test_get_all_team_submissions_for_course_item(self):
        team_submission_1 = self.create_team_submission(self.user, team_id='another_team_1')
        team_submission_2 = self.create_team_submission(self.user, team_id='another_team_2')
        team_submission_3 = self.create_team_submission(self.user, team_id='another_team_3')
        self.create_team_submission(self.user, item_id=self.other_item_id, team_id='another_team_4')
        self.create_team_submission(self.user, course_id=self.other_course_id, team_id='another_team_another_course')
        result = TeamSubmission.get_all_team_submissions_for_course_item(self.default_course_id, self.default_item_id)
        self.assertEqual(len(result), 4)
        self.assertIn(self.default_submission, result)
        self.assertIn(team_submission_1, result)
        self.assertIn(team_submission_2, result)
        self.assertIn(team_submission_3, result)

    def test_get_all_team_submissions_for_course_item_no_results(self):
        result = TeamSubmission.get_all_team_submissions_for_course_item(self.other_course_id, self.other_item_id)
        self.assertEqual(len(result), 0)

    @mock.patch('submissions.models.TeamSubmission.SoftDeletedManager.get_queryset')
    def test_get_all_team_submissions_for_course_item_error(self, mocked_qs):
        mocked_qs.side_effect = Exception()
        with self.assertRaises(TeamSubmissionInternalError):
            TeamSubmission.get_all_team_submissions_for_course_item(
                self.default_course_id,
                self.default_item_id,
            )


class TestExternalGraderDetail(TestCase):
    """
    Test the ExternalGraderDetail model functionality.
    """

    def setUp(self):
        """Set up common test data."""
        self.student_item = StudentItem.objects.create(
            student_id="test_student",
            course_id="test_course",
            item_id="test_item"
        )
        self.submission = Submission.objects.create(
            student_item=self.student_item,
            answer="test answer",
            attempt_number=1
        )
        self.external_grader_detail = ExternalGraderDetail.objects.create(
            submission=self.submission,
            queue_name="test_queue"
        )

    def test_default_status(self):
        """Test that new external graders are created with 'pending' status."""
        self.assertEqual(self.external_grader_detail.status, 'pending')
        self.assertEqual(self.external_grader_detail.num_failures, 0)

    def test_valid_status_transition(self):
        """Test valid status transitions."""
        # Test pending -> pulled transition
        self.external_grader_detail.update_status('pulled')
        self.assertEqual(self.external_grader_detail.status, 'pulled')

        # Test pulled -> retired transition
        self.external_grader_detail.update_status('retired')
        self.assertEqual(self.external_grader_detail.status, 'retired')

    def test_invalid_status_transition(self):
        """Test that invalid status transitions raise ValueError."""
        # Can't go from pending to retired
        with self.assertRaises(ValueError):
            self.external_grader_detail.update_status('retired')

        # Can't go from pending to an invalid status
        with self.assertRaises(ValueError):
            self.external_grader_detail.update_status('invalid_status')

    def test_failure_count(self):
        """Test that failure count increases properly."""
        self.assertEqual(self.external_grader_detail.num_failures, 0)

        # Transition to failed status should increment counter
        self.external_grader_detail.update_status('pulled')
        self.external_grader_detail.update_status('retry')
        self.assertEqual(self.external_grader_detail.num_failures, 1)

    def test_status_time_updates(self):
        """Test that status_time updates with status changes."""
        original_time = self.external_grader_detail.status_time

        # Wait a small amount to ensure time difference
        time.sleep(0.1)

        self.external_grader_detail.update_status('pulled')
        self.assertGreater(self.external_grader_detail.status_time, original_time)

    def test_valid_status_transitions(self):
        """Test valid status transitions"""
        # Test pending -> pulled
        self.external_grader_detail.update_status('pulled')
        self.assertEqual(self.external_grader_detail.status, 'pulled')

        # Test pulled -> retired
        self.external_grader_detail.update_status('retired')
        self.assertEqual(self.external_grader_detail.status, 'retired')

    def test_invalid_status_transitions(self):
        """Test invalid status transitions raise error"""
        # Can't go from pending to retired
        with self.assertRaises(ValueError):
            self.external_grader_detail.update_status('retired')

        # Set to pulled first
        self.external_grader_detail.update_status('pulled')

        # Can't go from pulled to pending
        with self.assertRaises(ValueError):
            self.external_grader_detail.update_status('pending')

    def test_clean_new_instance(self):
        """Test clean method for new instances (no pk assigned yet)"""
        new_record = ExternalGraderDetail(
            submission=self.submission,
            queue_name="test_queue"
        )
        new_record.clean()
        self.assertIsNone(new_record.pk, "New record should not have pk")
        self.assertEqual(new_record.status, 'pending', "The intital state should be 'pending'")
        self.assertIsNotNone(new_record.submission, "Submission must be defined")
        self.assertEqual(new_record.queue_name, "test_queue")

    def test_get_queue_length_multiple_statuses(self):
        """Test that get_queue_length only counts pending submissions."""

        # Create an old submission (outside processing window) that's pending
        _ = ExternalGraderDetail.objects.create(
            submission=Submission.objects.create(
                student_item=self.student_item,
                answer="old pending",
                attempt_number=2
            ),
            queue_name="test_queue",
            status="pending",
            status_time=now() - timedelta(minutes=90)
        )

        # Create an old submission that's pulled
        _ = ExternalGraderDetail.objects.create(
            submission=Submission.objects.create(
                student_item=self.student_item,
                answer="old pulled",
                attempt_number=3
            ),
            queue_name="test_queue",
            status="pulled",
            status_time=now() - timedelta(minutes=90)
        )

        # Should only count the pending submission
        self.assertEqual(
            ExternalGraderDetail.objects.get_queue_length("test_queue"),
            1
        )

    def test_filter_get_next_submission(self):
        """
        Test specific to filter with get_next_submission
        """
        new_student_item = StudentItem.objects.create(
            student_id="test_student_2",
            course_id="test_course",
            item_id="test_item"
        )
        new_submission = Submission.objects.create(
            student_item=new_student_item,
            answer="test answer 2",
            attempt_number=1
        )

        submissions2 = ExternalGraderDetail.objects.create(
            submission=new_submission,
            queue_name="test_queue_2",
            status='pending',
            status_time=now() - timedelta(minutes=61)
        )

        result = ExternalGraderDetail.objects.get_next_submission("test_queue_2")

        self.assertEqual(result, submissions2)
        result_wrong_queue = ExternalGraderDetail.objects.get_next_submission("wrong_queue")
        self.assertIsNone(result_wrong_queue)

    def test_clean_valid_transitions(self):
        """Test that clean method allows all valid status transitions"""

        # Test 1: pending -> pulled
        record = ExternalGraderDetail.objects.get(pk=self.external_grader_detail.pk)
        self.assertEqual(record.status, 'pending', "Initial status should be 'pending'")
        record.status = 'pulled'
        record.clean()
        record.save()
        self.assertEqual(record.status, 'pulled', "Status should transition from 'pending' to 'pulled'")

        # Test 2: pulled -> failed
        self.assertEqual(record.status, 'pulled', "Status should be 'pulled' before transition")
        record.status = 'failed'
        record.clean()
        record.save()
        self.assertEqual(record.status, 'failed', "Status should transition from 'pulled' to 'failed'")

        # Test 3: failed -> pending
        self.assertEqual(record.status, 'failed', "Status should be 'failed' before transition")
        record.status = 'pending'
        record.clean()
        record.save()
        self.assertEqual(record.status, 'pending', "Status should transition from 'failed' to 'pending'")

        # Test 4: pending -> failed (otra rama)
        self.assertEqual(record.status, 'pending', "Status should be 'pending' before transition")
        record.status = 'failed'
        record.clean()
        record.save()
        self.assertEqual(record.status, 'failed', "Status should transition from 'pending' to 'failed'")

        # Test 5: pending -> pulled -> retired
        self.assertEqual(record.status, 'failed', "Status should be 'failed' before transition")
        record.status = 'pending'
        record.clean()
        record.save()
        self.assertEqual(record.status, 'pending', "Status should transition back to 'pending'")

        record.status = 'pulled'
        record.clean()
        record.save()
        self.assertEqual(record.status, 'pulled', "Status should transition from 'pending' to 'pulled'")

        record = ExternalGraderDetail.objects.get(pk=self.external_grader_detail.pk)
        self.assertEqual(record.status, 'pulled', "Status should be 'pulled' before transition")
        record.status = 'retired'
        record.clean()
        record.save()
        self.assertEqual(record.status, 'retired', "Status should transition from 'pulled' to 'retired'")


class TestSubmission(TestCase):
    """
    Test the Submission model functionality.
    """

    def setUp(self):
        """Set up common test data."""
        self.student_item = StudentItem.objects.create(
            student_id="test_student",
            course_id="test_course",
            item_id="test_item"
        )
        self.test_answer = {"response": "This is a test answer"}
        self.submission = Submission.objects.create(
            student_item=self.student_item,
            answer=self.test_answer,
            attempt_number=1
        )

    def test_submission_str(self):
        """Test the string representation of a Submission."""
        self.assertEqual(str(self.submission), f"Submission {self.submission.uuid}")

    def test_submission_repr(self):
        """Test the repr representation of a Submission."""
        submission_dict = {
            "uuid": str(self.submission.uuid),
            "student_item": str(self.student_item),
            "attempt_number": self.submission.attempt_number,
            "submitted_at": self.submission.submitted_at,
            "created_at": self.submission.created_at,
            "answer": self.submission.answer,
        }

        self.assertIn(str(submission_dict["uuid"]), repr(self.submission))
        self.assertIn(str(submission_dict["answer"]), repr(self.submission))
        self.assertIn(str(submission_dict["attempt_number"]), repr(self.submission))

    def test_get_cache_key(self):
        """Test the cache key generation."""
        expected_key = f"submissions.submission.{self.submission.uuid}"
        self.assertEqual(Submission.get_cache_key(self.submission.uuid), expected_key)

    def test_submission_ordering(self):
        """Test that submissions are ordered by submitted_at and id."""
        past_time = now() - timedelta(hours=1)
        earlier_submission = Submission.objects.create(
            student_item=self.student_item,
            answer=self.test_answer,
            attempt_number=2,
            submitted_at=past_time
        )

        submissions = Submission.objects.all()
        self.assertEqual(submissions[0], self.submission)  # Most recent first
        self.assertEqual(submissions[1], earlier_submission)

    def test_soft_deletion(self):
        """Test that soft-deleted submissions are excluded from default queries."""
        # Create a submission that will be soft-deleted
        submission_to_delete = Submission.objects.create(
            student_item=self.student_item,
            answer=self.test_answer,
            attempt_number=3
        )

        submission_to_delete.status = DELETED
        submission_to_delete.save()
        self.assertNotIn(submission_to_delete, Submission.objects.all())

    def test_answer_json_serialization(self):
        """Test that the answer field properly handles JSON serialization."""
        test_cases = [
            {"text": "Simple answer"},
            ["list", "of", "items"],
            {"nested": {"data": {"structure": True}}},
            123,
            ["mixed", 1, {"types": True}]
        ]

        for test_case in test_cases:
            submission = Submission.objects.create(
                student_item=self.student_item,
                answer=test_case,
                attempt_number=1
            )
            re_fetched = Submission.objects.get(id=submission.id)
            self.assertEqual(re_fetched.answer, test_case)

    def test_max_answer_size(self):
        """
        Test large answer submission.
        Note: This test verifies we can handle large answers up to MAXSIZE.
        """
        # Test with an answer just under the max size
        valid_answer = {
            "large_field": "x" * (Submission.MAXSIZE - 100)
        }

        submission = Submission.objects.create(
            student_item=self.student_item,
            answer=valid_answer,
            attempt_number=1
        )

        self.assertEqual(submission.answer, valid_answer)

    def test_submission_mutability(self):
        """
        Test submission field updates.
        Note: While submissions should conceptually be immutable,
        this is enforced at the application level, not the database level.
        """
        new_answer = {"new": "answer"}
        new_attempt = 999
        new_time = now()

        # Update the submission
        self.submission.answer = new_answer
        self.submission.attempt_number = new_attempt
        self.submission.submitted_at = new_time
        self.submission.save()

        # Fetch fresh from database
        re_fetched = Submission.objects.get(id=self.submission.id)

        # Verify changes were saved
        self.assertEqual(re_fetched.answer, new_answer)
        self.assertEqual(re_fetched.attempt_number, new_attempt)
        self.assertEqual(re_fetched.submitted_at, new_time)


class TestSubmissionFile(TestCase):
    """
    Test the SubmissionFile model functionality.
    """

    def setUp(self):
        """Set up common test data."""

        self.student_item = StudentItem.objects.create(
            student_id="test_student",
            course_id="test_course",
            item_id="test_item"
        )
        self.submission = Submission.objects.create(
            student_item=self.student_item,
            answer="test answer",
            attempt_number=1
        )
        self.external_grader_detail = ExternalGraderDetail.objects.create(
            submission=self.submission,
            queue_name="test_queue"
        )

        self.test_file = SimpleUploadedFile(
            "test_file.txt",
            b"test content",
            content_type="text/plain"
        )

        self.submission_file = SubmissionFile.objects.create(
            external_grader=self.external_grader_detail,
            file=self.test_file,
            original_filename="test_file.txt"
        )

    def test_create_submission_file(self):
        """Test basic submission file creation."""
        self.assertIsNotNone(self.submission_file.uuid)
        self.assertEqual(self.submission_file.original_filename, "test_file.txt")
        self.assertEqual(self.submission_file.external_grader, self.external_grader_detail)
        self.assertIsNotNone(self.submission_file.created_at)

    def test_xqueue_url_format(self):
        """Test that xqueue_url property returns the correct format."""
        expected_url = f"/{self.external_grader_detail.queue_name}/{self.submission_file.uuid}"
        self.assertEqual(self.submission_file.xqueue_url, expected_url)

    def test_multiple_files_per_submission(self):
        """Test that multiple files can be associated with a single submission."""
        second_file = SimpleUploadedFile(
            "second_file.txt",
            b"more content",
            content_type="text/plain"
        )

        second_submission_file = SubmissionFile.objects.create(
            external_grader=self.external_grader_detail,
            file=second_file,
            original_filename="second_file.txt"
        )

        files = self.external_grader_detail.files.all()
        self.assertEqual(files.count(), 2)
        self.assertIn(self.submission_file, files)
        self.assertIn(second_submission_file, files)

    def test_file_path_generation(self):
        """Test that files are stored with the correct path structure."""
        file_path = self.submission_file.file.name
        expected_parts = [
            self.external_grader_detail.queue_name,
            str(self.submission_file.uuid)
        ]

        for part in expected_parts:
            self.assertIn(part, file_path)

    def test_unique_uids(self):
        """Test that each file gets a unique UUID."""
        second_file = SimpleUploadedFile(
            "another_file.txt",
            b"content",
            content_type="text/plain"
        )

        second_submission_file = SubmissionFile.objects.create(
            external_grader=self.external_grader_detail,
            file=second_file,
            original_filename="another_file.txt"
        )

        self.assertNotEqual(
            self.submission_file.uuid,
            second_submission_file.uuid
        )

    def test_related_name_access(self):
        """Test accessing files through the submission external grader."""
        files = self.external_grader_detail.files.all()
        self.assertEqual(files.count(), 1)
        self.assertEqual(files.first(), self.submission_file)

    def test_ordering(self):
        """Test that files are ordered by created_at."""
        past_time = now() - timedelta(hours=1)

        older_file = SimpleUploadedFile(
            "older_file.txt",
            b"old content",
            content_type="text/plain"
        )
        older_submission_file = SubmissionFile.objects.create(
            external_grader=self.external_grader_detail,
            file=older_file,
            original_filename="older_file.txt",
            created_at=past_time
        )

        files = self.external_grader_detail.files.all()
        self.assertEqual(files[0], self.submission_file)
        self.assertEqual(files[1], older_submission_file)

    def test_get_storage_default_with_mock(self):
        """Test that get_storage returns default_storage when no custom configuration exists."""
        _get_storage_cached.cache_clear()

        with patch('submissions.models.getattr', return_value={}):
            self.assertEqual(get_storage(), default_storage)
