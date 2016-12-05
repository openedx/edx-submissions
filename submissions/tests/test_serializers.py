"""
Tests for submissions serializers.
"""
import ddt
from django.test import TestCase
from submissions.models import Score, ScoreAnnotation, StudentItem, Submission
from submissions.serializers import ScoreSerializer


@ddt.ddt
class ScoreSerializerTest(TestCase):
    """
    Tests for the score serializer.
    """

    def setUp(self):
        super(ScoreSerializerTest, self).setUp()
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
