"""
Unit tests for the submissions events.
"""
from unittest import mock
from uuid import UUID

from django.test import TestCase
from openedx_events.learning.signals import SUBMISSION_CREATED
from submissions.api import create_submission
from submissions.models import TeamSubmission


class TestSubmissionEvents(TestCase):
    """Test cases for submission events."""

    def setUp(self):
        """Set up test data."""
        super().setUp()
        self.student_item_dict = {
            'student_id': 'test_student',
            'course_id': 'test_course',
            'item_id': 'test_item',
            'item_type': 'test_type'
        }
        self.answer = {'text': 'Esta es una respuesta de prueba'}

    def test_submission_created_event_emitted(self):
        """Test that the submission event is emitted when creating a submission."""
        event_receiver = mock.Mock()
        SUBMISSION_CREATED.connect(event_receiver)

        _ = create_submission(self.student_item_dict, self.answer)

        event_receiver.assert_called_once()

        event_kwargs = event_receiver.call_args.kwargs
        submission_data = event_kwargs['submission']

        self.assertEqual(submission_data.student_id, self.student_item_dict['student_id'])
        self.assertEqual(submission_data.item_id, self.student_item_dict['item_id'])
        self.assertEqual(submission_data.course_id, self.student_item_dict['course_id'])
        self.assertEqual(submission_data.item_type, self.student_item_dict['item_type'])
        self.assertEqual(submission_data.answer, self.answer)
        self.assertEqual(submission_data.attempt_number, 1)


    def test_event_data_with_team_submission(self):
        """Test event data when submission includes team data."""
        event_receiver = mock.Mock()
        SUBMISSION_CREATED.connect(event_receiver)
        uuid = UUID('12345678-1234-5678-1234-567812345678')
        team_submission = TeamSubmission.objects.create(
            uuid=uuid,
            attempt_number=1
        )

        _ = create_submission(
            self.student_item_dict,
            self.answer,
            team_submission=team_submission
        )

        event_receiver.assert_called_once()
        event_kwargs = event_receiver.call_args.kwargs
        self.assertEqual(
            str(event_kwargs['submission'].team_submission_uuid),
            str(team_submission.uuid)
        )

    def test_event_not_emitted_on_error(self):
        """Test that event is not emitted when submission creation fails."""
        event_receiver = mock.Mock()
        SUBMISSION_CREATED.connect(event_receiver)

        invalid_student_dict = {
            'student_id': '',
            'course_id': 'test_course',
            'item_id': 'test_item',
            'item_type': 'test_type'
        }

        with self.assertRaises(Exception):
            _ = create_submission(invalid_student_dict, self.answer)

        event_receiver.assert_not_called()
