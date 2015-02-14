"""
Test API calls using the read replica.
"""
import copy
from django.test import TransactionTestCase
from submissions import api as sub_api


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
        retrieved = sub_api.get_submission_and_student(self.submission['uuid'], read_replica=True)
        expected = copy.deepcopy(self.submission)
        expected['student_item'] = copy.deepcopy(self.STUDENT_ITEM)
        self.assertEqual(retrieved, expected)

    def test_get_latest_score_for_submission(self):
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
        with self.assertNumQueries(0):
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