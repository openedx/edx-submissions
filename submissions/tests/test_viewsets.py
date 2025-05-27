"""
Tests for XQueue API views.
"""
import json
import uuid
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.db import DatabaseError
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.test import APITestCase

from submissions.models import ExternalGraderDetail, SubmissionFile
from submissions.tests.factories import ExternalGraderDetailFactory, SubmissionFactory
from submissions.views.xqueue import XqueueViewSet

User = get_user_model()


@override_settings(ROOT_URLCONF='submissions.urls')
class TestXqueueViewSet(APITestCase):
    """
    Test cases for XqueueViewSet endpoints.
    """

    def setUp(self):
        """Set up test data."""
        super().setUp()
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass'
        )
        self.submission = SubmissionFactory()
        self.external_grader = ExternalGraderDetailFactory(
            submission=self.submission,
            pullkey='test_pull_key',
            status='pending',
            queue_name='test_queue',
            num_failures=0
        )
        self.url_put_result = reverse('xqueue-put_result')
        self.url_login = reverse('xqueue-login')
        self.url_logout = reverse('xqueue-logout')
        self.url_status = reverse('xqueue-status')
        self.get_submission_url = reverse('xqueue-get_submission')
        self.viewset = XqueueViewSet()

    def test_get_submission_missing_queue_name(self):
        """Test error when queue_name parameter is missing."""
        self.client.login(username='testuser', password='testpass')
        response = self.client.get(self.get_submission_url)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            response.data,
            self.viewset.compose_reply(False, "'get_submission' must provide parameter 'queue_name'")
        )

    def test_get_submission_queue_empty(self):
        """Test error when the specified queue is empty."""
        queue_name = 'empty_queue'
        self.client.login(username='testuser', password='testpass')
        ExternalGraderDetail.objects.filter(queue_name=queue_name).delete()
        response = self.client.get(self.get_submission_url, {'queue_name': queue_name})
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(
            response.data,
            self.viewset.compose_reply(False, f"Queue '{queue_name}' is empty")
        )

    def test_get_submission_success(self):
        """Test successfully retrieving a submission from the queue."""
        queue_name = 'prueba'
        self.client.login(username='testuser', password='testpass')

        initial_pullkey = 'initial_pullkey'

        new_submission = SubmissionFactory()
        external_grader = ExternalGraderDetailFactory(
            queue_name=queue_name,
            status='pending',
            submission=new_submission,
            pullkey=initial_pullkey
        )

        response = self.client.get(self.get_submission_url, {'queue_name': queue_name})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        content = json.loads(response.data['content'])
        self.assertEqual(response.data['return_code'], 0)

        xqueue_header = json.loads(content['xqueue_header'])
        xqueue_body = json.loads(content['xqueue_body'])
        self.assertEqual(xqueue_header['submission_id'], new_submission.id)
        response_pullkey = xqueue_header['submission_key']
        self.assertEqual(xqueue_body['student_response'], new_submission.answer)
        self.assertEqual(content['xqueue_files'], '{}')

        external_grader.refresh_from_db()
        self.assertEqual(external_grader.status, 'pulled')
        self.assertEqual(external_grader.pullkey, response_pullkey)
        self.assertIsNotNone(external_grader.status_time)

    @patch('submissions.views.xqueue.ExternalGraderDetail.update_status',
           side_effect=ValueError('Invalid transition'))
    def test_get_submission_invalid_transition(self, mock_update_status):
        """Test get_submission when there is an invalid state transition (ValueError)."""
        queue_name = 'prueba'
        data = {
            'username': 'testuser',
            'password': 'testpass'
        }
        response = self.client.post(self.url_login, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        new_submission = SubmissionFactory()
        external_grader = ExternalGraderDetailFactory(
            submission=new_submission,
            queue_name=queue_name,
            status='pending'
        )

        response = self.client.get(self.get_submission_url, {'queue_name': queue_name})
        mock_update_status.assert_called_once_with('pulled')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            response.data,
            self.viewset.compose_reply(False, "Error processing submission: Invalid transition")
        )

        external_grader.refresh_from_db()
        self.assertEqual(external_grader.status, 'pending')

    def test_put_result_invalid_submission_id(self):
        """Test put_result with non-existent submission ID."""
        self.client.login(username='testuser', password='testpass')
        response = self.client.post(self.url_status)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        payload = {
            'xqueue_header': json.dumps({
                'submission_id': 99999,
                'submission_key': 'test_pull_key'
            }),
            'xqueue_body': json.dumps({'score': 0.8})
        }

        response = self.client.post(self.url_put_result, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        response_data = json.loads(response.content)
        self.assertEqual(
            response_data,
            self.viewset.compose_reply(False, 'Submission does not exist')
        )

    def test_put_result_invalid_key(self):
        """Test put_result with incorrect submission key."""
        self.client.login(username='testuser', password='testpass')
        response = self.client.post(self.url_status)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        payload = {
            'xqueue_header': json.dumps({
                'submission_id': self.submission.id,
                'submission_key': 'wrong_key'
            }),
            'xqueue_body': json.dumps({'score': 0.8})
        }

        response = self.client.post(self.url_put_result, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        response_data = json.loads(response.content)
        self.assertEqual(
            response_data,
            self.viewset.compose_reply(False, 'Incorrect key for submission')
        )

    def test_put_result_invalid_format(self):
        """Test put_result with malformed request data."""
        self.client.login(username='testuser', password='testpass')
        response = self.client.post(self.url_status)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        invalid_payloads = [
            {},
            {'xqueue_header': 'not_json'},
            {'xqueue_header': '{}', 'xqueue_body': 'not_json'},
            {'xqueue_body': '{}'},
            {'xqueue_header': '{}'},
        ]

        for payload in invalid_payloads:
            response = self.client.post(self.url_put_result, payload, format='json')
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
            response_data = json.loads(response.content)
            self.assertEqual(
                response_data,
                self.viewset.compose_reply(False, 'Incorrect reply format')
            )

    def test_put_result_set_score_failure(self):
        """
        Test put_result handling when set_score fails.
        """
        data = {
            'username': 'testuser',
            'password': 'testpass'
        }
        response = self.client.post(self.url_login, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        response = self.client.post(self.url_status)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.external_grader.update_status('pulled')

        payload = {
            'xqueue_header': json.dumps({
                'submission_id': self.submission.id,
                'submission_key': self.external_grader.pullkey
            }),
            'xqueue_body': json.dumps({'score': 0.8})
        }

        with patch('submissions.api.set_score') as mock_set_score:
            mock_set_score.side_effect = Exception('Test error')
            response = self.client.post(self.url_put_result, payload, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.external_grader.refresh_from_db()
        self.assertEqual(self.external_grader.num_failures, 1)
        self.assertEqual(self.external_grader.status, 'retry')

    def test_put_result_set_score_fail_30_times(self):
        """
        Test put_result handling when set_score by intentionally failing 30 times.
        """
        self.client.login(username='testuser', password='testpass')
        response = self.client.post(self.url_status)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        for each in range(31):
            with patch('submissions.api.set_score') as _:
                self.external_grader.update_status('pulled')
                payload = {
                    'xqueue_header': json.dumps({
                        'submission_id': self.submission.id,
                        'submission_key': self.external_grader.pullkey,
                    }),
                    'xqueue_body': json.dumps({'score': 0.8})
                }
                response = self.client.post(self.url_put_result, payload, format='json')

            self.assertEqual(response.status_code, status.HTTP_200_OK)

            self.external_grader.refresh_from_db()
            self.assertEqual(self.external_grader.num_failures, each + 1)

        self.assertEqual(self.external_grader.status, 'failed')

    @patch('submissions.views.xqueue.log')
    def test_put_result_success(self, mock_log):
        """
        Test that appropriate logging occurs in various scenarios.
        """
        self.submission.external_grader_detail.status = 'pulled'
        self.submission.external_grader_detail.save()
        self.submission.external_grader_detail.refresh_from_db()
        self.assertEqual(self.submission.external_grader_detail.status, 'pulled')

        payload = {
            'xqueue_header': json.dumps({
                'submission_id': self.submission.id,
                'submission_key': 'test_pull_key'
            }),
            'xqueue_body': json.dumps({'score': 8})
        }

        with patch('submissions.api.set_score') as mock_set_score:
            self.client.login(username='testuser', password='testpass')
            response = self.client.post(self.url_status)
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            mock_set_score.return_value = True
            response = self.client.post(self.url_put_result, payload, format='json')

        mock_log.info.assert_any_call(
            "Successfully updated submission score for submission %s",
            self.submission.id
        )

        response_data = json.loads(response.content)
        self.assertEqual(
            response_data,
            self.viewset.compose_reply(True, '')
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_get_permissions_login(self):
        """Test permissions for login endpoint"""
        viewset = XqueueViewSet()
        viewset.action = 'login'
        permissions = viewset.get_permissions()
        self.assertTrue(any(isinstance(p, AllowAny) for p in permissions))

    def test_get_permissions_other_actions(self):
        """Test permissions for non-login endpoints"""
        viewset = XqueueViewSet()
        viewset.action = 'logout'
        permissions = viewset.get_permissions()
        self.assertTrue(all(isinstance(p, IsAuthenticated) for p in permissions))

    def test_dispatch_valid_session(self):
        """Test dispatch with valid session"""
        self.client.login(username='testuser', password='testpass')
        response = self.client.post(self.url_status)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_dispatch_invalid_session(self):
        """Test dispatch with invalid session"""
        # Create invalid session cookie
        self.client.cookies['sessionid'] = 'invalid_session_id'
        response = self.client.get(self.url_status)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_login_success(self):
        """Test successful login"""
        data = {
            'username': 'testuser',
            'password': 'testpass'
        }
        response = self.client.post(self.url_login, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['return_code'], 0)
        self.assertIn('sessionid', response.cookies)

    def test_login_missing_credentials(self):
        """Test login with missing credentials"""
        response = self.client.post(self.url_login, {})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['return_code'], 1)

    def test_login_invalid_credentials(self):
        """Test login with invalid credentials"""
        data = {
            'username': 'testuser',
            'password': 'wrongpass'
        }
        response = self.client.post(self.url_login, data)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(response.data['return_code'], 1)

    def test_logout(self):
        """Test logout functionality"""
        self.client.login(username='testuser', password='testpass')
        response = self.client.post(self.url_logout)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['return_code'], 0)

    def test_validate_grader_reply_valid(self):
        """Test _validate_grader_reply with valid data"""
        viewset = XqueueViewSet()
        external_reply = {
            'xqueue_header': json.dumps({
                'submission_id': 123,
                'submission_key': 'test_key'
            }),
            'xqueue_body': json.dumps({
                'score': 0.8
            })
        }
        valid, sub_id, sub_key, _, points = viewset.validate_grader_reply(external_reply)
        self.assertTrue(valid)
        self.assertEqual(sub_id, 123)
        self.assertEqual(sub_key, 'test_key')
        self.assertEqual(points, 0.8)

    def test_validate_grader_reply_invalid(self):
        """Test _validate_grader_reply with invalid data"""
        viewset = XqueueViewSet()
        invalid_replies = [
            None,
            {},
            {'xqueue_header': 42, 'xqueue_body': json.dumps({'score': 0.8})},
            {'xqueue_header': 'invalid_json'},
            {'xqueue_header': '{}', 'xqueue_body': 'invalid_json'},
            {'xqueue_header': json.dumps({}), 'xqueue_body': '{}'},
            {'xqueue_header': json.dumps(["item1", "item2", "item3"]), 'xqueue_body': json.dumps({'score': 0.8})}
        ]
        for reply in invalid_replies:
            valid, *_ = viewset.validate_grader_reply(reply)
            self.assertFalse(valid)

    def test_compose_reply(self):
        """Test _compose_reply method"""
        viewset = XqueueViewSet()
        success_reply = viewset.compose_reply(True, "Success message")
        self.assertEqual(success_reply['return_code'], 0)
        self.assertEqual(success_reply['content'], "Success message")

        error_reply = viewset.compose_reply(False, "Error message")
        self.assertEqual(error_reply['return_code'], 1)
        self.assertEqual(error_reply['content'], "Error message")

    def test_status_endpoint(self):
        """Test status endpoint"""
        self.client.login(username='testuser', password='testpass')
        response = self.client.post(self.url_status)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        content = response.content.decode('utf-8')
        self.assertIn('return_code', content)
        self.assertIn('content', content)

    def test_get_submission_with_files(self):
        """Test successfully retrieving a submission with attached files from the queue."""
        self.client.login(username='testuser', password='testpass')

        file_content = b'Test file content'
        submission_file = SubmissionFile.objects.create(
            external_grader=self.external_grader,
            file=ContentFile(file_content, name='test.txt'),
            original_filename='test.txt'
        )

        response = self.client.get(self.get_submission_url, {'queue_name': 'test_queue'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        content = json.loads(response.data['content'])

        xqueue_files = json.loads(content['xqueue_files'])
        self.assertIn('test.txt', xqueue_files)
        expected_url = f'/test_queue/{submission_file.uuid}'
        self.assertEqual(xqueue_files['test.txt'], expected_url)

    def test_get_submission_with_multiple_files(self):
        """Test retrieving a submission with multiple attached files."""
        self.client.login(username='testuser', password='testpass')

        files_data = [
            ('file1.txt', b'Content 1'),
            ('file2.txt', b'Content 2'),
            ('file3.txt', b'Content 3')
        ]

        created_files = []
        for filename, content in files_data:
            submission_file = SubmissionFile.objects.create(
                external_grader=self.external_grader,
                file=ContentFile(content, name=filename),
                original_filename=filename
            )
            created_files.append(submission_file)

        response = self.client.get(self.get_submission_url, {'queue_name': 'test_queue'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        content = json.loads(response.data['content'])
        xqueue_files = json.loads(content['xqueue_files'])

        self.assertEqual(len(xqueue_files), len(files_data))
        for file_obj, (filename, _) in zip(created_files, files_data):
            self.assertIn(filename, xqueue_files)
            expected_url = f'/test_queue/{file_obj.uuid}'
            self.assertEqual(xqueue_files[filename], expected_url)

    def test_get_submission_file_urls_format(self):
        """Test that file URLs in the response follow the expected format."""
        self.client.login(username='testuser', password='testpass')

        test_uuid = uuid.uuid4()
        _ = SubmissionFile.objects.create(
            external_grader=self.external_grader,
            file=ContentFile(b'content', name='test.txt'),
            original_filename='test.txt',
            uuid=test_uuid
        )

        response = self.client.get(self.get_submission_url, {'queue_name': 'test_queue'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        content = json.loads(response.data['content'])
        xqueue_files = json.loads(content['xqueue_files'])

        expected_url = f'/test_queue/{test_uuid}'
        self.assertEqual(xqueue_files['test.txt'], expected_url)

    def test_get_submission_db_error(self):
        """Test DatabaseError handling when retrieving a submission."""
        self.client.login(username='testuser', password='testpass')
        queue_name = 'test_queue'

        with patch(
                'submissions.views.xqueue.ExternalGraderDetail.objects.select_for_update',
                side_effect=DatabaseError("Simulated DB Error")
        ):
            response = self.client.get(self.get_submission_url, {'queue_name': queue_name})

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(
            response.data,
            self.viewset.compose_reply(False, "Submission already in process")
        )

    def test_get_submission_already_pulled(self):
        """Test retrieving a submission that already has a 'pulled' status."""
        queue_name = 'test_queue'
        self.client.login(username='testuser', password='testpass')
        self.external_grader.update_status('pulled')
        self.external_grader.status_time = timezone.now() - timedelta(minutes=6)
        self.external_grader.save()

        response = self.client.get(self.get_submission_url, {'queue_name': queue_name})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        content = json.loads(response.data['content'])

        xqueue_header = json.loads(content['xqueue_header'])
        self.assertEqual(xqueue_header['submission_id'], self.external_grader.submission.id)
        self.assertEqual(xqueue_header['submission_key'],  self.external_grader.pullkey)

        self.external_grader.refresh_from_db()
        self.assertEqual(self.external_grader.status, 'pulled')
