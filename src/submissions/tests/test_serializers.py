"""
Tests for submissions serializers.
"""

import ddt
from django.test import TestCase

from submissions.models import Score, ScoreAnnotation, StudentItem, Submission
from submissions.serializers import ScoreSerializer, TeamSubmissionSerializer
from submissions.tests.factories import StudentItemFactory, SubmissionFactory, TeamSubmissionFactory


@ddt.ddt
class ScoreSerializerTest(TestCase):
    """
    Tests for the score serializer.
    """

    def setUp(self):
        super().setUp()
        self.item = StudentItem.objects.create(
            student_id="score_test_student",
            course_id="score_test_course",
            item_id="i4x://mycourse/special_presentation"
        )
        self.submission = Submission.objects.create(student_item=self.item, attempt_number=1)

        self.score = Score.objects.create(
            student_item=self.item,
            submission=self.submission,
            points_earned=2,
            points_possible=6,
        )

    def test_score_with_null_submission(self):
        # Create a score with a null submission
        null_sub_score = Score.objects.create(
            student_item=self.item,
            submission=None,
            points_earned=3,
            points_possible=8,
        )
        null_sub_score_dict = ScoreSerializer(null_sub_score).data
        self.assertIs(null_sub_score_dict['submission_uuid'], None)
        self.assertEqual(null_sub_score_dict['points_earned'], 3)
        self.assertEqual(null_sub_score_dict['points_possible'], 8)

    @ddt.data(['test_annotation_1', 'test_annotation_2'], [])
    def test_score_annotations(self, annotation_types):
        """
        Ensure that annotation types are returned with serialized scores.
        """
        annotation_kwargs = {
            'creator': 'test_annotator',
            'reason': 'tests for the test god'
        }
        for test_type in annotation_types:
            ScoreAnnotation.objects.create(
                score=self.score,
                annotation_type=test_type,
                **annotation_kwargs
            )
        score_dict = ScoreSerializer(self.score).data
        self.assertEqual(
            score_dict['annotations'],
            [
                {
                    'reason': annotation_kwargs['reason'],
                    'annotation_type': annotation_type,
                    'creator': annotation_kwargs['creator'],
                }
                for annotation_type in annotation_types
            ]
        )


class TeamSubmissionSerializerTest(TestCase):
    """
    Tests for the Team Submission Serializer.
    """

    @classmethod
    def setUpTestData(cls):
        cls.course_id = 'test-course-id'
        cls.item_id = 'test-item-id'
        cls.answer = {'something': 'b', 'something_else': 7000, 'some_other_thing': ['one_thing', 'two_thing']}

        cls.student_items = [StudentItemFactory.create(course_id=cls.course_id, item_id=cls.item_id) for _ in range(5)]
        cls.submissions = [
            SubmissionFactory.create(
                student_item=cls.student_items[i],
                answer=cls.answer
            ) for i in range(5)
        ]
        cls.team_submission = TeamSubmissionFactory.create(course_id=cls.course_id, item_id=cls.item_id)
        cls.team_submission.submissions.set(cls.submissions)
        super().setUpTestData()

    def test_team_submission_serializer(self):
        """
        Test that the non-trivial fields on TeamSerializer have been serialized correctly
        """
        serialized_data = TeamSubmissionSerializer(self.team_submission).data

        self.assertEqual(
            serialized_data['team_submission_uuid'],
            str(self.team_submission.uuid)
        )
        self.assertEqual(
            set(serialized_data['submission_uuids']),
            {submission.uuid for submission in self.submissions},
        )
        self.assertEqual(serialized_data['submitted_at'], self.team_submission.submitted_at)
        self.assertEqual(serialized_data['created_at'], self.team_submission.created)
        self.assertEqual(serialized_data['attempt_number'], self.team_submission.attempt_number)
        self.assertEqual(serialized_data['answer'], self.answer)
