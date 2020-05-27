""" Team Api Module Tests. """

import ddt
import mock
from django.core.cache import cache
from django.db import DatabaseError
from django.test import TestCase
from django.utils.timezone import now
from freezegun import freeze_time

from submissions import team_api
from submissions.errors import (
    DuplicateTeamSubmissionsError,
    SubmissionInternalError,
    TeamSubmissionInternalError,
    TeamSubmissionNotFoundError,
    TeamSubmissionRequestError
)
from submissions.models import ACTIVE, DELETED, Score, StudentItem, Submission, TeamSubmission
from submissions.serializers import TeamSubmissionSerializer
from submissions.tests.factories import SubmissionFactory, TeamSubmissionFactory, UserFactory

COURSE_ID = 'edX/Teamwork101/Cooperation'
ITEM_1_ID = 'item_1'
ITEM_2_ID = 'item_2'
TEAM_1_ID = 'team_apple'
TEAM_2_ID = 'team_banana'

ANSWER = {
    'file_descriptions': ['a1', 'a2'],
    'file_names': ['a1.txt', 'a2.png'],
    'file_keys': ['key_1', 'key_2'],
}

OTHER_COURSE_ID = 'edX/Selfishness/Loneliness'


@ddt.ddt
class TestTeamSubmissionsApi(TestCase):
    """
    Testing Team Submissions API
    """

    def setUp(self):
        """
        Clear the cache.
        """
        super(TestTeamSubmissionsApi, self).setUp()
        cache.clear()

    @classmethod
    def setUpTestData(cls):
        """ Create some test users """
        super(TestTeamSubmissionsApi, cls).setUpTestData()
        cls.user_1 = UserFactory.create()
        cls.user_2 = UserFactory.create()
        cls.user_3 = UserFactory.create()
        cls.user_4 = UserFactory.create()
        cls.anonymous_user_id_map = {
            cls.user_1: '11111111111111111111111111111111',
            cls.user_2: '22222222222222222222222222222222',
            cls.user_3: '33333333333333333333333333333333',
            cls.user_4: '44444444444444444444444444444444',
        }
        cls.student_ids = list(cls.anonymous_user_id_map.values())

    @classmethod
    def _make_team_submission(
        cls,
        attempt_number=1,
        course_id=COURSE_ID,
        item_id=ITEM_1_ID,
        team_id=TEAM_1_ID,
        status=None,
        create_submissions=False
    ):
        """ Convenience method to create test TeamSubmissions with some default values """
        model_args = {
            'attempt_number': attempt_number,
            'course_id': course_id,
            'item_id': item_id,
            'team_id': team_id,
        }
        if status:
            model_args['status'] = status
        team_submission = TeamSubmissionFactory.create(**model_args)
        if create_submissions:
            for student_id in cls.student_ids:
                student_item = cls._get_or_create_student_item(student_id, course_id=course_id, item_id=item_id)
                SubmissionFactory.create(student_item=student_item, team_submission=team_submission, answer='Foo')
        return team_submission

    @classmethod
    def _get_or_create_student_item(
        cls,
        student_id,
        course_id=COURSE_ID,
        item_id=ITEM_1_ID,
        item_type='openassessment'
    ):
        """ Convenience method to get or create student item, mostly for creating test Submission models """
        student_item, _ = StudentItem.objects.get_or_create(
            student_id=student_id,
            course_id=course_id,
            item_id=item_id,
            item_type=item_type
        )
        return student_item

    def _call_create_submission_for_team_with_default_args(self):
        """ Convenience method to call team_api.create_submission_for_team with some default arguments """
        return team_api.create_submission_for_team(
            COURSE_ID,
            ITEM_1_ID,
            TEAM_1_ID,
            self.user_1.id,
            self.student_ids,
            ANSWER
        )

    @freeze_time("2020-04-10 12:00:01", tz_offset=-4)
    def test_create_submission_for_team(self):
        """
        Test that calling create_submisson_for_team creates a TeamSubmission with the expected field values and
        one Submission per team member with the same andswer and expected field values
        """
        result = self._call_create_submission_for_team_with_default_args()
        # The values of these don't really matter, they're just uuids
        team_submission_uuid = result.pop('team_submission_uuid')
        submission_uuids = result.pop('submission_uuids')

        self.assertDictEqual(
            {
                'answer': ANSWER,
                'submitted_at': now(),
                'created_at': now(),
                'attempt_number': 1,
                'course_id': COURSE_ID,
                'item_id': ITEM_1_ID,
                'team_id': TEAM_1_ID,
                'submitted_by': self.user_1.id
            },
            result
        )
        # Make sure the model was created
        TeamSubmission.objects.get(uuid=team_submission_uuid)

        # Make sure the submisisons have been created
        self.assertEqual(len(submission_uuids), len(self.student_ids))
        remaining_users = set(self.student_ids)
        for submission_uuid in submission_uuids:
            submission = Submission.objects.select_related('student_item').get(uuid=submission_uuid)
            self.assertIn(submission.student_item.student_id, remaining_users)
            self.assertEqual(COURSE_ID, submission.student_item.course_id)
            self.assertEqual(ITEM_1_ID, submission.student_item.item_id)
            self.assertEqual(result['attempt_number'], submission.attempt_number)
            self.assertEqual(ANSWER, submission.answer)
            remaining_users.remove(submission.student_item.student_id)

    def test_create_submission_for_team_existing_active_team_submission(self):
        """
        Test for calling create_submission_for_team with an existing active team submission
        for the same team course and item.
        """
        self._make_team_submission(status=ACTIVE)
        with self.assertRaises(DuplicateTeamSubmissionsError):
            self._call_create_submission_for_team_with_default_args()

    def test_create_submission_for_team_existing_deleted_team_submission(self):
        """
        Test for calling create_submission_for_team with an existing deleted team submission
        for the same team course and item.
        """
        team_submission_1 = self._make_team_submission(status=DELETED)
        team_submission_2 = self._call_create_submission_for_team_with_default_args()
        self.assertEqual(team_submission_1.attempt_number, 1)
        self.assertEqual(team_submission_2['attempt_number'], 1)

    def test_create_submission_for_team_invalid_attempt(self):
        """
        Test for calling create_submission_for_team with an invalid attempt_number
        """
        with self.assertRaises(TeamSubmissionRequestError):
            team_api.create_submission_for_team(
                COURSE_ID,
                ITEM_1_ID,
                TEAM_1_ID,
                self.user_1.id,
                self.student_ids,
                ANSWER,
                attempt_number=-1
            )

    def test_create_submission_for_team_existing_individual_submission(self):
        """
        Test for calling create_submission_for_team when a user somehow already has
        an existing active submission for the item.

        For normal Submissions, if a submission exists and we create another one, the second
        will increment the first's attempt_number. However, for team submissions, we currently
        pass the attempt_number from team_api.create_submission to api.create_submission, so
        all created individual submissions will have the same attempt_number
        """
        user_3_item = self._get_or_create_student_item(self.anonymous_user_id_map[self.user_3])
        SubmissionFactory.create(student_item=user_3_item)
        team_submission_data = self._call_create_submission_for_team_with_default_args()
        self.assertEqual(team_submission_data['attempt_number'], 1)
        submissions = Submission.objects.select_related(
            'student_item'
        ).filter(
            uuid__in=team_submission_data['submission_uuids']
        ).all()
        for submission in submissions:
            self.assertEqual(submission.attempt_number, 1)

    @mock.patch('submissions.api._log_submission')
    def test_create_submission_for_team_error_creating_individual_submission(self, mocked_log_submission):
        """
        Test for when there is an error creating one individual submission.
        the team submission and all other individual submissions should not be created.
        """
        mocked_log_submission.side_effect = [None, None, None, DatabaseError()]
        with self.assertRaises(SubmissionInternalError):
            self._call_create_submission_for_team_with_default_args()
        self.assertEqual(TeamSubmission.objects.count(), 0)
        self.assertEqual(Submission.objects.count(), 0)

    def test_get_team_submission(self):
        """
        Test that calling team_api.get_team_submission returns the expected team submission
        """
        team_submission_model = self._make_team_submission(create_submissions=True)

        team_submission_dict = team_api.get_team_submission(team_submission_model.uuid)
        self.assertDictEqual(
            team_submission_dict,
            TeamSubmissionSerializer(team_submission_model).data
        )

    def test_get_team_submission_missing(self):
        """
        Test that calling team_api.get_team_submission when there is no matching TeamSubmission will
        raise a TeamSubmissionNotFoundError
        """
        with self.assertRaises(TeamSubmissionNotFoundError):
            team_api.get_team_submission('aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee')

    def test_get_team_submission_invalid_uuid(self):
        """
        Test that calling team_api.get_team_submission with an invalid UUID will
        raise a TeamSubmissionInternalError
        """
        with self.assertRaisesMessage(TeamSubmissionInternalError, 'not a valid UUID'):
            team_api.get_team_submission('thisisntauuid')

    def test_get_team_submission_for_team(self):
        """
        Test that calling team_api.get_team_submission_for_team returns the expected team submission
        """
        team_submission = self._make_team_submission(create_submissions=True)
        team_submission_dict = team_api.get_team_submission_for_team(COURSE_ID, ITEM_1_ID, TEAM_1_ID)
        self.assertDictEqual(
            team_submission_dict,
            TeamSubmissionSerializer(team_submission).data
        )

    def test_get_team_submission_for_team_not_found(self):
        """
        Test that calling team_api.get_team_submission_for_team when there is no matching TeamSubmission will
        raise a TeamSubmissionNotFoundError
        """
        self._make_team_submission()
        with self.assertRaises(TeamSubmissionNotFoundError):
            team_api.get_team_submission_for_team(COURSE_ID, ITEM_1_ID, TEAM_2_ID)

    @mock.patch('submissions.models.TeamSubmission.SoftDeletedManager.get_queryset')
    def test_get_team_submission_for_team_error(self, mocked_qs):
        """
        Test for error behavior within team_api.get_team_submission_for_team
        """
        mocked_qs.side_effect = Exception('!!!error!!!')
        with self.assertRaisesMessage(TeamSubmissionInternalError, 'caused error: !!!error!!!'):
            team_api.get_team_submission_for_team(COURSE_ID, ITEM_1_ID, TEAM_1_ID)

    def assert_team_submission_list(self, team_submissions, expected_submission_1, expected_submission_2):
        """
        Convenience method.
        Asserts that team_submissions has exactly two elements and that they are equal to
        expected_submission_1 and expected_submission_2
        """
        self.assertEqual(len(team_submissions), 2)
        self.assertEqual(
            {submission['team_submission_uuid'] for submission in team_submissions},
            {str(expected_submission_1.uuid), str(expected_submission_2.uuid)}
        )
        if team_submissions[0]['team_submission_uuid'] == expected_submission_1.uuid:
            team_submission_1, team_submission_2 = team_submissions
        else:
            team_submission_2, team_submission_1 = team_submissions

        self.assertDictEqual(
            TeamSubmissionSerializer(expected_submission_1).data,
            team_submission_1
        )
        self.assertDictEqual(
            TeamSubmissionSerializer(expected_submission_2).data,
            team_submission_2
        )

    def test_get_all_team_submissions(self):
        """
        Test that team_api.get_all_team_submissions returns the expected list of TeamSubmissions
        """
        # Make a bunch of team submissions
        team_submission_models = [
            self._make_team_submission(
                course_id=COURSE_ID,
                item_id=ITEM_1_ID,
                team_id=TEAM_1_ID,
                create_submissions=True
            ),
            self._make_team_submission(
                course_id=COURSE_ID,
                item_id=ITEM_1_ID,
                team_id=TEAM_2_ID,
                create_submissions=True
            ),
            self._make_team_submission(
                course_id=COURSE_ID,
                item_id=ITEM_2_ID,
                team_id=TEAM_1_ID,
                create_submissions=True
            ),
            self._make_team_submission(
                course_id=COURSE_ID,
                item_id=ITEM_2_ID,
                team_id=TEAM_2_ID,
                create_submissions=True
            )
        ]
        team_submissions = team_api.get_all_team_submissions(COURSE_ID, ITEM_1_ID)
        self.assert_team_submission_list(team_submissions, team_submission_models[0], team_submission_models[1])

        team_submissions = team_api.get_all_team_submissions(COURSE_ID, ITEM_2_ID)
        self.assertEqual(len(team_submissions), 2)
        self.assert_team_submission_list(team_submissions, team_submission_models[2], team_submission_models[3])

    def test_get_all_team_submissions_no_submissions(self):
        """
        Test that calling team_api.get_all_team_submissions when there are no matching teams returns an empty list.
        """
        team_submissions = team_api.get_all_team_submissions(COURSE_ID, ITEM_1_ID)
        self.assertEqual(team_submissions, [])

    @mock.patch('submissions.models.TeamSubmission.SoftDeletedManager.get_queryset')
    def test_get_all_team_submissions_error(self, mocked_qs):
        """
        Test for get_all_team_submissions error behavior
        """
        mocked_qs.side_effect = Exception('!!!error!!!')
        with self.assertRaisesMessage(TeamSubmissionInternalError, 'caused error: !!!error!!!'):
            team_api.get_all_team_submissions(COURSE_ID, ITEM_1_ID)

    def test_set_score(self):
        """
        Test that calling team_api.set_score will set the score for each individual submission,
        and that calling it again will create another score for all individual submissions.
        """
        team_submission = self._make_team_submission(create_submissions=True)
        team_api.set_score(team_submission.uuid, 6, 10)
        first_round_scores = {}
        for student_id in self.student_ids:
            individual_submission = team_submission.submissions.get(student_item__student_id=student_id)
            self.assertEqual(individual_submission.score_set.count(), 1)
            score = individual_submission.score_set.first()
            self.assertEqual(score.points_earned, 6)
            self.assertEqual(score.points_possible, 10)
            self.assertFalse(score.scoreannotation_set.exists())
            first_round_scores[student_id] = score

        team_api.set_score(
            team_submission.uuid,
            9,
            10,
            annotation_creator='some_staff',
            annotation_reason='they did some extra credit!',
            annotation_type='staff_override',
        )

        for student_id in self.student_ids:
            individual_submission = team_submission.submissions.get(student_item__student_id=student_id)
            self.assertEqual(individual_submission.score_set.count(), 2)
            second_score = individual_submission.score_set.exclude(pk=first_round_scores[student_id].pk).first()
            self.assertEqual(second_score.points_earned, 9)
            self.assertEqual(second_score.points_possible, 10)
            self.assertEqual(second_score.scoreannotation_set.count(), 1)
            annotation = second_score.scoreannotation_set.first()
            self.assertEqual(annotation.creator, 'some_staff')
            self.assertEqual(annotation.reason, 'they did some extra credit!')
            self.assertEqual(annotation.annotation_type, 'staff_override')

    @mock.patch('submissions.api._log_score')
    def test_set_score_error(self, mock_log):
        """
        Test for when there is an error creating one individual score.
        No scores should be created.
        """
        mock_log.side_effect = [None, None, None, Exception()]
        team_submission = self._make_team_submission(create_submissions=True)
        with self.assertRaises(Exception):
            team_api.set_score(team_submission.uuid, 6, 10)
        self.assertFalse(
            Score.objects.filter(submission__team_submission=team_submission).exists()
        )

    @ddt.unpack
    @ddt.data(
        (True, True),
        (True, False),
        (False, True),
        (False, False),
    )
    def test_reset_scores(self, set_scores, clear_state):
        """
        Test for resetting scores.
        """
        team_submission = self._make_team_submission(create_submissions=True)
        if set_scores:
            team_api.set_score(team_submission.uuid, 6, 10)

        team_submission.refresh_from_db()

        self.assertEqual(team_submission.status, ACTIVE)
        student_items = []
        for submission in team_submission.submissions.all():
            self.assertEqual(submission.status, ACTIVE)
            student_items.append(submission.student_item)

        # We have no / some scores, and no resets.
        self.assertEqual(
            Score.objects.filter(student_item__in=student_items, reset=False).count(),
            0 if not set_scores else len(student_items)
        )
        self.assertEqual(
            Score.objects.filter(student_item__in=student_items, reset=True).count(),
            0
        )

        # Reset
        team_api.reset_scores(team_submission.uuid, clear_state=clear_state)

        expected_state = DELETED if clear_state else ACTIVE
        # If we've cleared the state, the team submission status should be DELETED,
        # as should all of the individual submissions
        team_submission.refresh_from_db()
        self.assertEqual(team_submission.status, expected_state)
        for submission in team_submission.submissions.all():
            self.assertEqual(submission.status, expected_state)

        # We have created reset scores
        self.assertEqual(
            Score.objects.filter(student_item__in=student_items, reset=True).count(),
            len(student_items)
        )

    @mock.patch('submissions.team_api._api.reset_score')
    def test_reset_scores_error(self, mock_individual_reset):
        mock_individual_reset.side_effect = DatabaseError()
        team_submission = self._make_team_submission(create_submissions=True)
        with self.assertRaises(TeamSubmissionInternalError):
            team_api.reset_scores(team_submission.uuid)
