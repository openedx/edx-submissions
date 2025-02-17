""" Api Module Tests. """

# Stdlib imports
import copy
import datetime
from unittest import mock

# Third party imports
import ddt
import pytz
# Django imports
from django.core.cache import cache
from django.db import DatabaseError, IntegrityError, connection, transaction
from django.test import TestCase
from django.utils.timezone import now
from freezegun import freeze_time

# Local imports
from submissions import api
from submissions.errors import SubmissionInternalError, SubmissionQueueCanNotBeEmptyError
from submissions.models import ExternalGraderDetail, ScoreAnnotation, ScoreSummary, StudentItem, Submission, score_set
from submissions.serializers import StudentItemSerializer

STUDENT_ITEM = {
    "student_id": "Tim",
    "course_id": "Demo_Course",
    "item_id": "item_one",
    "item_type": "Peer_Submission",
}

SECOND_STUDENT_ITEM = {
    "student_id": "Alice",
    "course_id": "Demo_Course",
    "item_id": "item_one",
    "item_type": "Peer_Submission",
}

ANSWER_ONE = "this is my answer!"
ANSWER_TWO = "this is my other answer!"
ANSWER_THREE = '' + 'c' * (Submission.MAXSIZE + 1)

# Test a non-string JSON-serializable answer
ANSWER_DICT = {"text": "foobar"}


@ddt.ddt
class TestSubmissionsApi(TestCase):
    """
    Testing Submissions
    """

    def setUp(self):
        """
        Clear the cache.
        """
        super().setUp()
        cache.clear()

    @ddt.data(ANSWER_ONE, ANSWER_DICT)
    def test_create_submission(self, answer):
        submission = api.create_submission(STUDENT_ITEM, answer)
        student_item = self._get_student_item(STUDENT_ITEM)
        self._assert_submission(submission, answer, student_item.pk, 1)

    def test_create_huge_submission_fails(self):
        with self.assertRaises(api.SubmissionRequestError):
            api.create_submission(STUDENT_ITEM, ANSWER_THREE)

    def test_get_submission_and_student(self):
        submission = api.create_submission(STUDENT_ITEM, ANSWER_ONE)

        # Retrieve the submission by its uuid
        retrieved = api.get_submission_and_student(submission['uuid'])
        self.assertCountEqual(submission, retrieved)

        # Should raise an exception if the student item does not exist
        with self.assertRaises(api.SubmissionNotFoundError):
            api.get_submission_and_student('deadbeef-1234-5678-9100-1234deadbeef')

    def test_get_submissions(self):
        api.create_submission(STUDENT_ITEM, ANSWER_ONE)
        api.create_submission(STUDENT_ITEM, ANSWER_TWO)
        submissions = api.get_submissions(STUDENT_ITEM)

        student_item = self._get_student_item(STUDENT_ITEM)
        self._assert_submission(submissions[1], ANSWER_ONE, student_item.pk, 1)
        self._assert_submission(submissions[0], ANSWER_TWO, student_item.pk, 2)

    def test_get_all_submissions(self):
        api.create_submission(SECOND_STUDENT_ITEM, ANSWER_TWO)
        api.create_submission(STUDENT_ITEM, ANSWER_ONE)
        api.create_submission(STUDENT_ITEM, ANSWER_TWO)
        api.create_submission(SECOND_STUDENT_ITEM, ANSWER_ONE)
        with self.assertNumQueries(1):
            submissions = list(api.get_all_submissions(
                STUDENT_ITEM['course_id'],
                STUDENT_ITEM['item_id'],
                STUDENT_ITEM['item_type'],
                read_replica=False,
            ))

        student_item = self._get_student_item(STUDENT_ITEM)
        second_student_item = self._get_student_item(SECOND_STUDENT_ITEM)
        # The result is assumed to be sorted by student_id, which is not part of the specification
        # of get_all_submissions(), but it is what it currently does.
        self._assert_submission(submissions[0], ANSWER_ONE, second_student_item.pk, 2)
        self.assertEqual(submissions[0]['student_id'], SECOND_STUDENT_ITEM['student_id'])
        self._assert_submission(submissions[1], ANSWER_TWO, student_item.pk, 2)
        self.assertEqual(submissions[1]['student_id'], STUDENT_ITEM['student_id'])

    @ddt.data(True, False)
    def test_get_course_submissions(self, set_scores):
        submission1 = api.create_submission(STUDENT_ITEM, ANSWER_ONE)
        submission2 = api.create_submission(STUDENT_ITEM, ANSWER_TWO)
        submission3 = api.create_submission(SECOND_STUDENT_ITEM, ANSWER_ONE)
        submission4 = api.create_submission(SECOND_STUDENT_ITEM, ANSWER_TWO)

        if set_scores:
            api.set_score(submission1['uuid'], 1, 4)
            api.set_score(submission2['uuid'], 2, 4)
            api.set_score(submission3['uuid'], 3, 4)
            api.set_score(submission4['uuid'], 4, 4)

        submissions_and_scores = list(api.get_all_course_submission_information(
            STUDENT_ITEM['course_id'],
            STUDENT_ITEM['item_type'],
            read_replica=False,
        ))

        student_item1 = self._get_student_item(STUDENT_ITEM)
        student_item2 = self._get_student_item(SECOND_STUDENT_ITEM)

        self.assertDictEqual(SECOND_STUDENT_ITEM, submissions_and_scores[0][0])
        self._assert_submission(submissions_and_scores[0][1], submission4['answer'], student_item2.pk, 2)

        self.assertDictEqual(SECOND_STUDENT_ITEM, submissions_and_scores[1][0])
        self._assert_submission(submissions_and_scores[1][1], submission3['answer'], student_item2.pk, 1)

        self.assertDictEqual(STUDENT_ITEM, submissions_and_scores[2][0])
        self._assert_submission(submissions_and_scores[2][1], submission2['answer'], student_item1.pk, 2)

        self.assertDictEqual(STUDENT_ITEM, submissions_and_scores[3][0])
        self._assert_submission(submissions_and_scores[3][1], submission1['answer'], student_item1.pk, 1)

        # These scores will always be empty
        self.assertEqual(submissions_and_scores[1][2], {})
        self.assertEqual(submissions_and_scores[3][2], {})

        if set_scores:
            self._assert_score(submissions_and_scores[0][2], 4, 4)
            self._assert_score(submissions_and_scores[2][2], 2, 4)
        else:
            self.assertEqual(submissions_and_scores[0][2], {})
            self.assertEqual(submissions_and_scores[2][2], {})

    def test_get_submission(self):
        # Test base case that we can create a submission and get it back
        sub_dict1 = api.create_submission(STUDENT_ITEM, ANSWER_ONE)
        sub_dict2 = api.get_submission(sub_dict1["uuid"])
        self.assertEqual(sub_dict1, sub_dict2)

        # Test invalid inputs
        with self.assertRaises(api.SubmissionRequestError):
            api.get_submission(20)
        with self.assertRaises(api.SubmissionRequestError):
            api.get_submission({})

        # Test not found
        with self.assertRaises(api.SubmissionNotFoundError):
            api.get_submission("deadbeef-1234-5678-9100-1234deadbeef")

    @mock.patch.object(Submission.objects, 'get')
    def test_get_submission_deep_error(self, mock_get):
        # Test deep explosions are wrapped
        with self.assertRaises(api.SubmissionInternalError):
            mock_get.side_effect = DatabaseError("Kaboom!")
            api.get_submission("000000000000000")

    def test_get_old_submission(self):
        # hack in an old-style submission, this can't be created with the ORM (EDUCATOR-1090)
        with transaction.atomic():
            student_item = StudentItem.objects.create()
            connection.cursor().execute("""
                INSERT INTO submissions_submission
                    (id, uuid, attempt_number, submitted_at, created_at, raw_answer, student_item_id, status)
                VALUES (
                    {}, {}, {}, {}, {}, {}, {}, {}
                );""".format(
                    1,
                    "\'deadbeef-1234-5678-9100-1234deadbeef\'",
                    1,
                    "\'2017-07-13 17:56:02.656129\'",
                    "\'2017-07-13 17:56:02.656129\'",
                    "\'{\"parts\":[{\"text\":\"raw answer text\"}]}\'",
                    int(student_item.id),
                    "\'A\'"
                ), []
            )

        with mock.patch.object(
            Submission.objects, 'raw',
            wraps=Submission.objects.raw
        ) as mock_raw:
            _ = api.get_submission('deadbeef-1234-5678-9100-1234deadbeef')
            self.assertEqual(1, mock_raw.call_count)

            # On subsequent accesses we still get the submission, but raw() isn't needed
            mock_raw.reset_mock()
            _ = api.get_submission('deadbeef-1234-5678-9100-1234deadbeef')
            self.assertEqual(0, mock_raw.call_count)

    def test_two_students(self):
        api.create_submission(STUDENT_ITEM, ANSWER_ONE)
        api.create_submission(SECOND_STUDENT_ITEM, ANSWER_TWO)

        submissions = api.get_submissions(STUDENT_ITEM)
        self.assertEqual(1, len(submissions))
        student_item = self._get_student_item(STUDENT_ITEM)
        self._assert_submission(submissions[0], ANSWER_ONE, student_item.pk, 1)

        submissions = api.get_submissions(SECOND_STUDENT_ITEM)
        self.assertEqual(1, len(submissions))
        student_item = self._get_student_item(SECOND_STUDENT_ITEM)
        self._assert_submission(submissions[0], ANSWER_TWO, student_item.pk, 1)

    @ddt.file_data('data/valid_student_items.json')
    def test_various_student_items(self, **valid_student_item):
        api.create_submission(valid_student_item, ANSWER_ONE)
        student_item = self._get_student_item(valid_student_item)
        submission = api.get_submissions(valid_student_item)[0]
        self._assert_submission(submission, ANSWER_ONE, student_item.pk, 1)

    def test_get_latest_submission(self):
        past_date = datetime.datetime(2007, 9, 12, 0, 0, 0, 0, pytz.UTC)
        more_recent_date = datetime.datetime(2007, 9, 13, 0, 0, 0, 0, pytz.UTC)
        api.create_submission(STUDENT_ITEM, ANSWER_ONE, more_recent_date)
        api.create_submission(STUDENT_ITEM, ANSWER_TWO, past_date)

        # Test a limit on the submissions
        submissions = api.get_submissions(STUDENT_ITEM, 1)
        self.assertEqual(1, len(submissions))
        self.assertEqual(ANSWER_ONE, submissions[0]["answer"])
        self.assertEqual(more_recent_date.year,
                         submissions[0]["submitted_at"].year)

    def test_set_attempt_number(self):
        api.create_submission(STUDENT_ITEM, ANSWER_ONE, None, 2)
        submissions = api.get_submissions(STUDENT_ITEM)
        student_item = self._get_student_item(STUDENT_ITEM)
        self._assert_submission(submissions[0], ANSWER_ONE, student_item.pk, 2)

    @ddt.file_data('data/bad_student_items.json')
    def test_error_checking(self, **bad_student_item):
        with self.assertRaises(api.SubmissionRequestError):
            api.create_submission(bad_student_item, -100)

    def test_error_checking_submissions(self):
        with self.assertRaises(api.SubmissionRequestError):
            # Attempt number should be >= 0
            api.create_submission(STUDENT_ITEM, ANSWER_ONE, None, -1)

    @mock.patch.object(Submission.objects, 'filter')
    def test_error_on_submission_creation(self, mock_filter):
        with self.assertRaises(api.SubmissionInternalError):
            mock_filter.side_effect = DatabaseError("Bad things happened")
            api.create_submission(STUDENT_ITEM, ANSWER_ONE)

    def test_create_non_json_answer(self):
        with self.assertRaises(api.SubmissionRequestError):
            api.create_submission(STUDENT_ITEM, now())

    def test_load_non_json_answer(self):
        submission = api.create_submission(STUDENT_ITEM, ANSWER_ONE)
        sub_model = Submission.objects.get(uuid=submission['uuid'])

        # This should never happen, if folks are using the public API.
        # Create a submission with a raw answer that is NOT valid JSON
        with transaction.atomic():
            query = "UPDATE submissions_submission SET raw_answer = '}' WHERE id = %s"
            connection.cursor().execute(query, [str(sub_model.id)])

        with self.assertRaises(api.SubmissionInternalError):
            api.get_submission(sub_model.uuid)

        with self.assertRaises(api.SubmissionInternalError):
            api.get_submission_and_student(sub_model.uuid)

    @mock.patch.object(StudentItemSerializer, 'save')
    def test_create_student_item_validation(self, mock_save):
        with self.assertRaises(api.SubmissionInternalError):
            mock_save.side_effect = DatabaseError("Bad things happened")
            api.create_submission(STUDENT_ITEM, ANSWER_ONE)

    def test_unicode_enforcement(self):
        api.create_submission(STUDENT_ITEM, "Testing unicode answers.")
        submissions = api.get_submissions(STUDENT_ITEM, 1)
        self.assertEqual("Testing unicode answers.", submissions[0]["answer"])

    def _assert_submission(self, submission, expected_answer, expected_item, expected_attempt):
        self.assertIsNotNone(submission)
        self.assertEqual(submission["answer"], expected_answer)
        self.assertEqual(submission["student_item"], expected_item)
        self.assertEqual(submission["attempt_number"], expected_attempt)

    def _get_student_item(self, student_item):
        return StudentItem.objects.get(
            student_id=student_item["student_id"],
            course_id=student_item["course_id"],
            item_id=student_item["item_id"]
        )

    def test_caching(self):
        sub = api.create_submission(STUDENT_ITEM, "Hello World!")

        # The first request to get the submission hits the database...
        with self.assertNumQueries(1):
            db_sub = api.get_submission(sub["uuid"])

        # The next one hits the cache only...
        with self.assertNumQueries(0):
            cached_sub = api.get_submission(sub["uuid"])

        # The data that gets passed back matches the original in both cases
        self.assertEqual(sub, db_sub)
        self.assertEqual(sub, cached_sub)

    # Testing Scores

    def test_create_score(self):
        submission = api.create_submission(STUDENT_ITEM, ANSWER_ONE)
        student_item = self._get_student_item(STUDENT_ITEM)
        self._assert_submission(submission, ANSWER_ONE, student_item.pk, 1)

        api.set_score(submission["uuid"], 11, 12)
        score = api.get_latest_score_for_submission(submission["uuid"])
        self._assert_score(score, 11, 12)
        self.assertFalse(ScoreAnnotation.objects.all().exists())

    @freeze_time(now())
    @mock.patch.object(score_set, 'send')
    def test_set_score_signal(self, send_mock):
        submission = api.create_submission(STUDENT_ITEM, ANSWER_ONE)
        api.set_score(submission['uuid'], 11, 12)

        # Verify that the send method was properly called
        send_mock.assert_called_with(
            sender=None,
            points_possible=12,
            points_earned=11,
            anonymous_user_id=STUDENT_ITEM['student_id'],
            course_id=STUDENT_ITEM['course_id'],
            item_id=STUDENT_ITEM['item_id'],
            created_at=now(),
        )

    @ddt.data("First score was incorrect", "☃")
    def test_set_score_with_annotation(self, reason):
        submission = api.create_submission(STUDENT_ITEM, ANSWER_ONE)
        creator_uuid = "Bob"
        annotation_type = "staff_override"
        api.set_score(submission["uuid"], 11, 12, creator_uuid, annotation_type, reason)
        score = api.get_latest_score_for_submission(submission["uuid"])
        self._assert_score(score, 11, 12)

        # We need to do this to verify that one score annotation exists and was
        # created for this score. We do not have an api point for retrieving
        # annotations, and it doesn't make sense to expose them, since they're
        # for auditing purposes.
        annotations = ScoreAnnotation.objects.all()
        self.assertGreater(len(annotations), 0)
        annotation = annotations[0]
        self.assertEqual(annotation.score.points_earned, 11)
        self.assertEqual(annotation.score.points_possible, 12)
        self.assertEqual(annotation.annotation_type, annotation_type)
        self.assertEqual(annotation.creator, creator_uuid)
        self.assertEqual(annotation.reason, reason)

    def test_get_score(self):
        submission = api.create_submission(STUDENT_ITEM, ANSWER_ONE)
        api.set_score(submission["uuid"], 11, 12)
        score = api.get_score(STUDENT_ITEM)
        self._assert_score(score, 11, 12)
        self.assertEqual(score['submission_uuid'], submission['uuid'])

    def test_get_score_for_submission_hidden_score(self):
        # Create a "hidden" score for the submission
        # (by convention, a score with points possible set to 0)
        submission = api.create_submission(STUDENT_ITEM, ANSWER_ONE)
        api.set_score(submission["uuid"], 0, 0)

        # Expect that the retrieved score is None
        score = api.get_latest_score_for_submission(submission['uuid'])
        self.assertIs(score, None)

    def test_get_score_no_student_id(self):
        student_item = copy.deepcopy(STUDENT_ITEM)
        student_item['student_id'] = None
        self.assertIs(api.get_score(student_item), None)

    @freeze_time(now())
    def test_get_scores(self):
        student_item = copy.deepcopy(STUDENT_ITEM)
        student_item["course_id"] = "get_scores_course"

        student_item["item_id"] = "i4x://a/b/c/s1"
        s1 = api.create_submission(student_item, "Hello World")

        student_item["item_id"] = "i4x://a/b/c/s2"
        s2 = api.create_submission(student_item, "Hello World")

        student_item["item_id"] = "i4x://a/b/c/s3"
        s3 = api.create_submission(student_item, "Hello World")

        api.set_score(s1['uuid'], 3, 5)
        api.set_score(s1['uuid'], 4, 5)
        api.set_score(s1['uuid'], 2, 5)  # Should overwrite previous lines

        api.set_score(s2['uuid'], 0, 10)
        api.set_score(s3['uuid'], 4, 4)

        # Getting the scores for a user should never take more than one query
        with self.assertNumQueries(1):
            scores = api.get_scores(
                student_item["course_id"], student_item["student_id"]
            )
        self.assertEqual(
            scores,
            {
                'i4x://a/b/c/s1': {
                    'created_at': now(),
                    'points_earned': 2,
                    'points_possible': 5,
                    'student_item': 1,
                    'submission': 1,
                    'submission_uuid': s1['uuid'],
                },
                'i4x://a/b/c/s2': {
                    'created_at': now(),
                    'points_earned': 0,
                    'points_possible': 10,
                    'student_item': 2,
                    'submission': 2,
                    'submission_uuid': s2['uuid'],
                },
                'i4x://a/b/c/s3': {
                    'created_at': now(),
                    'points_earned': 4,
                    'points_possible': 4,
                    'student_item': 3,
                    'submission': 3,
                    'submission_uuid': s3['uuid'],
                },
            }
        )

    def test_get_top_submissions(self):
        student_item_1 = copy.deepcopy(STUDENT_ITEM)
        student_item_1['student_id'] = 'Tim'

        student_item_2 = copy.deepcopy(STUDENT_ITEM)
        student_item_2['student_id'] = 'Bob'

        student_item_3 = copy.deepcopy(STUDENT_ITEM)
        student_item_3['student_id'] = 'Li'

        student_1 = api.create_submission(student_item_1, "Hello World")
        student_2 = api.create_submission(student_item_2, "Hello World")
        student_3 = api.create_submission(student_item_3, "Hello World")

        api.set_score(student_1['uuid'], 8, 10)
        api.set_score(student_2['uuid'], 4, 10)
        api.set_score(student_3['uuid'], 2, 10)

        # Get top scores works correctly
        with self.assertNumQueries(1):
            top_scores = api.get_top_submissions(
                STUDENT_ITEM["course_id"],
                STUDENT_ITEM["item_id"],
                "Peer_Submission", 3,
                use_cache=False,
                read_replica=False,
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
                    {
                        'content': "Hello World",
                        'score': 2
                    },
                ]
            )

        # Fewer top scores available than the number requested.
        top_scores = api.get_top_submissions(
            STUDENT_ITEM["course_id"],
            STUDENT_ITEM["item_id"],
            "Peer_Submission", 10,
            use_cache=False,
            read_replica=False
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
                {
                    'content': "Hello World",
                    'score': 2
                },
            ]
        )

        # More top scores available than the number requested.
        top_scores = api.get_top_submissions(
            STUDENT_ITEM["course_id"],
            STUDENT_ITEM["item_id"],
            "Peer_Submission", 2,
            use_cache=False,
            read_replica=False
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
                }
            ]
        )

    def test_get_top_submissions_with_score_greater_than_zero(self):
        student_item_1 = copy.deepcopy(STUDENT_ITEM)
        student_item_1['student_id'] = 'Tim'

        student_item_2 = copy.deepcopy(STUDENT_ITEM)
        student_item_2['student_id'] = 'Bob'

        student_item_3 = copy.deepcopy(STUDENT_ITEM)
        student_item_3['student_id'] = 'Li'

        student_1 = api.create_submission(student_item_1, "Hello World")
        student_2 = api.create_submission(student_item_2, "Hello World")
        student_3 = api.create_submission(student_item_3, "Hello World")

        api.set_score(student_1['uuid'], 8, 10)
        api.set_score(student_2['uuid'], 4, 10)
        # These scores should not appear in top submissions.
        # because we are considering the scores which are
        # latest and greater than 0.
        api.set_score(student_3['uuid'], 5, 10)
        api.set_score(student_3['uuid'], 0, 10)

        # Get greater than 0 top scores works correctly
        with self.assertNumQueries(1):
            top_scores = api.get_top_submissions(
                STUDENT_ITEM["course_id"],
                STUDENT_ITEM["item_id"],
                "Peer_Submission", 3,
                use_cache=False,
                read_replica=False,
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
                    }
                ]
            )

    def test_get_top_submissions_from_cache(self):
        student_item_1 = copy.deepcopy(STUDENT_ITEM)
        student_item_1['student_id'] = 'Tim'

        student_item_2 = copy.deepcopy(STUDENT_ITEM)
        student_item_2['student_id'] = 'Bob'

        student_item_3 = copy.deepcopy(STUDENT_ITEM)
        student_item_3['student_id'] = 'Li'

        student_1 = api.create_submission(student_item_1, "Hello World")
        student_2 = api.create_submission(student_item_2, "Hello World")
        student_3 = api.create_submission(student_item_3, "Hello World")

        api.set_score(student_1['uuid'], 8, 10)
        api.set_score(student_2['uuid'], 4, 10)
        api.set_score(student_3['uuid'], 2, 10)

        # The first call should hit the database
        with self.assertNumQueries(1):
            scores = api.get_top_submissions(
                STUDENT_ITEM["course_id"],
                STUDENT_ITEM["item_id"],
                STUDENT_ITEM["item_type"], 2,
                use_cache=True,
                read_replica=False
            )
            self.assertEqual(scores, [
                {"content": "Hello World", "score": 8},
                {"content": "Hello World", "score": 4},
            ])

        # The second call should use the cache
        with self.assertNumQueries(0):
            cached_scores = api.get_top_submissions(
                STUDENT_ITEM["course_id"],
                STUDENT_ITEM["item_id"],
                STUDENT_ITEM["item_type"], 2,
                use_cache=True,
                read_replica=False
            )
            self.assertEqual(cached_scores, scores)

    def test_get_top_submissions_from_cache_having_greater_than_0_score(self):
        student_item_1 = copy.deepcopy(STUDENT_ITEM)
        student_item_1['student_id'] = 'Tim'

        student_item_2 = copy.deepcopy(STUDENT_ITEM)
        student_item_2['student_id'] = 'Bob'

        student_item_3 = copy.deepcopy(STUDENT_ITEM)
        student_item_3['student_id'] = 'Li'

        student_1 = api.create_submission(student_item_1, "Hello World")
        student_2 = api.create_submission(student_item_2, "Hello World")
        student_3 = api.create_submission(student_item_3, "Hello World")

        api.set_score(student_1['uuid'], 8, 10)
        api.set_score(student_2['uuid'], 4, 10)
        api.set_score(student_3['uuid'], 0, 10)

        # The first call should hit the database
        with self.assertNumQueries(1):
            scores = api.get_top_submissions(
                STUDENT_ITEM["course_id"],
                STUDENT_ITEM["item_id"],
                STUDENT_ITEM["item_type"], 3,
                use_cache=True,
                read_replica=False
            )
        self.assertEqual(scores, [
            {"content": "Hello World", "score": 8},
            {"content": "Hello World", "score": 4},
        ])

        # The second call should use the cache
        with self.assertNumQueries(0):
            cached_scores = api.get_top_submissions(
                STUDENT_ITEM["course_id"],
                STUDENT_ITEM["item_id"],
                STUDENT_ITEM["item_type"], 3,
                use_cache=True,
                read_replica=False
            )
        self.assertEqual(cached_scores, scores)

    def test_clear_state(self):
        # Create a submission, give it a score, and verify that score exists
        submission = api.create_submission(STUDENT_ITEM, ANSWER_ONE)
        api.set_score(submission["uuid"], 11, 12)
        score = api.get_score(STUDENT_ITEM)
        self._assert_score(score, 11, 12)
        self.assertEqual(score['submission_uuid'], submission['uuid'])

        # Reset the score with clear_state=True
        # This should set the submission's score to None, and make it unavailable to get_submissions
        api.reset_score(
            STUDENT_ITEM["student_id"],
            STUDENT_ITEM["course_id"],
            STUDENT_ITEM["item_id"],
            clear_state=True,
        )
        score = api.get_score(STUDENT_ITEM)
        self.assertIsNone(score)
        subs = api.get_submissions(STUDENT_ITEM)
        self.assertEqual(subs, [])

    def test_error_on_get_top_submissions_too_few(self):
        with self.assertRaises(api.SubmissionRequestError):
            student_item = copy.deepcopy(STUDENT_ITEM)
            student_item["course_id"] = "get_scores_course"
            student_item["item_id"] = "i4x://a/b/c/s1"
            api.get_top_submissions(
                student_item["course_id"],
                student_item["item_id"],
                "Peer_Submission", 0,
                read_replica=False
            )

    def test_error_on_get_top_submissions_too_many(self):
        with self.assertRaises(api.SubmissionRequestError):
            student_item = copy.deepcopy(STUDENT_ITEM)
            student_item["course_id"] = "get_scores_course"
            student_item["item_id"] = "i4x://a/b/c/s1"
            api.get_top_submissions(
                student_item["course_id"],
                student_item["item_id"],
                "Peer_Submission",
                api.MAX_TOP_SUBMISSIONS + 1,
                read_replica=False
            )

    @mock.patch.object(ScoreSummary.objects, 'filter')
    def test_error_on_get_top_submissions_db_error(self, mock_filter):
        with self.assertRaises(api.SubmissionInternalError):
            mock_filter.side_effect = DatabaseError("Bad things happened")
            student_item = copy.deepcopy(STUDENT_ITEM)
            api.get_top_submissions(
                student_item["course_id"],
                student_item["item_id"],
                "Peer_Submission", 1,
                read_replica=False
            )

    @mock.patch.object(ScoreSummary.objects, 'filter')
    def test_error_on_get_scores(self, mock_filter):
        with self.assertRaises(api.SubmissionInternalError):
            mock_filter.side_effect = DatabaseError("Bad things happened")
            api.get_scores("some_course", "some_student")

    def _assert_score(self, score, expected_points_earned, expected_points_possible):
        self.assertIsNotNone(score)
        self.assertEqual(score["points_earned"], expected_points_earned)
        self.assertEqual(score["points_possible"], expected_points_possible)

    def test_get_student_ids_by_submission_uuid(self):
        # Define two course ids, with some associated item ids, and some "student ids"
        course_id = 'test_course_0000001'
        course_item_ids = [f"{course_id}_item_{i}" for i in range(4)]
        course_member_student_ids = [f'test_user_999{i}' for i in range(4)]
        # other_course is just for database noise. It has an overlap of two learners with "course"
        other_course_id = 'test_course_846292'
        other_course_items_id = [f"{other_course_id}_item_{i}" for i in range(2)]
        other_course_members_ids = [
            'some_other_user',
            'another_guy',
            course_member_student_ids[0],
            course_member_student_ids[2]
        ]

        def submit(course_id, item_id, student_ids):
            result_dict = {}
            for student_id in student_ids:
                student_item = {
                    "course_id": course_id,
                    "item_id": item_id,
                    "student_id": student_id,
                    "item_type": 'test_get_student_ids_by_submission_uuid'
                }
                submission_uuid = api.create_submission(student_item, ANSWER_ONE)['uuid']
                result_dict[submission_uuid] = student_id
            return result_dict

        # Make some submissions for the target course
        # Item 0, users 0 and 1 submit
        item_0_expected_result = submit(
            course_id,
            course_item_ids[0],
            course_member_student_ids[:2]
        )
        # Item 1, all users submit
        item_1_expected_result = submit(
            course_id,
            course_item_ids[1],
            course_member_student_ids
        )
        # Item 2, users 2 and 3
        item_2_expected_result = submit(
            course_id,
            course_item_ids[0],
            course_member_student_ids[2:]
        )
        # Item 3, users 1, 2, 3
        item_3_expected_result = submit(
            course_id,
            course_item_ids[0],
            course_member_student_ids[1:]
        )
        for item_id in other_course_items_id:
            submit(other_course_id, item_id, other_course_members_ids)
        self.assertDictEqual(
            api.get_student_ids_by_submission_uuid(
                course_id,
                item_0_expected_result.keys(),
                read_replica=False,
            ),
            item_0_expected_result
        )
        self.assertDictEqual(
            api.get_student_ids_by_submission_uuid(
                course_id,
                item_1_expected_result.keys(),
                read_replica=False,
            ),
            item_1_expected_result
        )
        self.assertDictEqual(
            api.get_student_ids_by_submission_uuid(
                course_id,
                item_2_expected_result.keys(),
                read_replica=False,
            ),
            item_2_expected_result
        )
        self.assertDictEqual(
            api.get_student_ids_by_submission_uuid(
                course_id,
                item_3_expected_result.keys(),
                read_replica=False,
            ),
            item_3_expected_result
        )

    def test_get_or_create_student_item_race_condition__item_created(self):
        """
        Test for a race condition in _get_or_create_student_item where the item does not exist when
        we check first, but has been created by the time we try to save, raising an IntegrityError.

        Test for the case where the second call to get succeeds.
        """
        mock_item = mock.Mock()
        with mock.patch.object(StudentItem.objects, "get") as mock_get_item:
            with mock.patch.object(StudentItemSerializer, "save", side_effect=IntegrityError):
                mock_get_item.side_effect = [
                    StudentItem.DoesNotExist,
                    mock_item
                ]
                self.assertEqual(
                    api._get_or_create_student_item(STUDENT_ITEM),  # pylint: disable=protected-access
                    mock_item
                )

    def test_get_or_create_student_item_race_condition__item_not_created(self):
        """
        Test for a race condition in _get_or_create_student_item where the item does not exist when
        we check first, but has been created by the time we try to save, raising an IntegrityError.

        Test for the case where the second call does not return an item, so the caught IntegrityError was something
        else and should be re-raised.
        """
        with mock.patch.object(StudentItem.objects, "get") as mock_get_item:
            with mock.patch.object(StudentItemSerializer, "save", side_effect=IntegrityError):
                mock_get_item.side_effect = StudentItem.DoesNotExist
                with self.assertRaisesMessage(SubmissionInternalError, "An error occurred creating student item"):
                    api._get_or_create_student_item(STUDENT_ITEM)  # pylint: disable=protected-access

    def test_create_queue_record(self):
        """Test the direct creation of a submission queue record."""
        student_item = api._get_or_create_student_item(STUDENT_ITEM)  # pylint: disable=protected-access
        submission = Submission.objects.create(
            student_item=student_item,
            answer=ANSWER_ONE,
            attempt_number=1
        )

        event_data = {'queue_name': 'test_queue'}
        queue_record = api.create_submission_queue_record(submission, event_data)

        self.assertEqual(queue_record.submission.id, submission.id)
        self.assertEqual(queue_record.queue_name, 'test_queue')

    def test_create_multiple_queue_record(self):
        """Test the direct creation of a submission queue record."""
        student_item1 = api._get_or_create_student_item(STUDENT_ITEM)  # pylint: disable=protected-access
        submission1 = Submission.objects.create(
            student_item=student_item1,
            answer=ANSWER_ONE,
            attempt_number=1
        )

        event_data1 = {'queue_name': 'test_queue'}
        queue_record1 = api.create_submission_queue_record(submission1, event_data1)

        self.assertEqual(queue_record1.submission.id, submission1.id)
        self.assertEqual(queue_record1.queue_name, 'test_queue')

        student_item2 = api._get_or_create_student_item(SECOND_STUDENT_ITEM)  # pylint: disable=protected-access
        submission2 = Submission.objects.create(
            student_item=student_item2,
            answer=ANSWER_ONE,
            attempt_number=1
        )

        event_data2 = {'queue_name': 'test_queue'}
        queue_record2 = api.create_submission_queue_record(submission2, event_data2)

        self.assertEqual(queue_record2.submission.id, submission2.id)
        self.assertEqual(queue_record2.queue_name, 'test_queue')

    def test_create_submission_queue_record_directly_missing_queue_name(self):
        """Test that create_submission_queue_record validates queue_name existence."""
        student_item = api._get_or_create_student_item(STUDENT_ITEM)  # pylint: disable=protected-access
        submission = Submission.objects.create(
            student_item=student_item,
            answer=ANSWER_ONE,
            attempt_number=1
        )

        with self.assertRaises(SubmissionQueueCanNotBeEmptyError):
            api.create_submission_queue_record(submission, {"queue_name": ""})

    def test_create_submission_queue_record_directly_database_error(self):
        """Test database error handling in create_submission_queue_record."""
        student_item = api._get_or_create_student_item(STUDENT_ITEM)  # pylint: disable=protected-access
        submission = Submission.objects.create(
            student_item=student_item,
            answer=ANSWER_ONE,
            attempt_number=1
        )

        event_data = {'queue_name': 'test_queue'}

        with mock.patch.object(ExternalGraderDetail.objects, 'create') as mock_create:
            mock_create.side_effect = DatabaseError("Database connection failed")

            with self.assertRaises(api.SubmissionInternalError):
                api.create_submission_queue_record(submission, event_data)

    def test_create_submission_with_queue_record(self):
        """
        Test that create_submission correctly creates a queue record when event_data is provided.
        """

        submission_dict = api.create_submission(STUDENT_ITEM,
                                                ANSWER_ONE,
                                                queue_name="test_queue",
                                                files={}
                                                )

        student_item = self._get_student_item(STUDENT_ITEM)
        self._assert_submission(submission_dict, ANSWER_ONE, student_item.pk, 1)

        queue_record = ExternalGraderDetail.objects.get(submission__uuid=submission_dict['uuid'])
        self.assertEqual(queue_record.queue_name, 'test_queue')

    def test_create_submission_missing_queue_name(self):
        """
        Test that creating a submission with event_data but without queue_name raises ValueError.
        """
        with self.assertRaises(SubmissionQueueCanNotBeEmptyError):
            api.create_submission(STUDENT_ITEM, ANSWER_ONE, queue_name="", files={})

    def test_create_multiple_submission_queue_records(self):
        """
        Test that multiple submissions can have queue records with the same queue_name.
        """

        submission1_dict = api.create_submission(STUDENT_ITEM,
                                                 ANSWER_ONE,
                                                 queue_name="shared_queue",
                                                 files={})

        second_student = SECOND_STUDENT_ITEM
        submission2_dict = api.create_submission(second_student, ANSWER_TWO,
                                                 queue_name="shared_queue",
                                                 files={})

        submission1 = Submission.objects.get(uuid=submission1_dict['uuid'])
        queue_record1 = submission1.queue_record

        submission2 = Submission.objects.get(uuid=submission2_dict['uuid'])
        queue_record2 = submission2.queue_record

        self.assertEqual(queue_record1.queue_name, 'shared_queue')
        self.assertEqual(queue_record2.queue_name, 'shared_queue')
        self.assertNotEqual(queue_record1.submission.uuid, queue_record2.submission.uuid)

    def test_create_submission_queue_record_database_error_integration(self):
        """
        Test database error handling when creating a queue record through create_submission.
        """
        with mock.patch.object(ExternalGraderDetail.objects, 'create') as mock_create:
            mock_create.side_effect = DatabaseError("Database connection failed")

            with self.assertRaises(api.SubmissionInternalError):
                api.create_submission(STUDENT_ITEM, ANSWER_ONE, queue_name="test_queue", files={})
