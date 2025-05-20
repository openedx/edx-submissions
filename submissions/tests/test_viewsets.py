"""
Tests for XQueue API views.
"""
import json
import uuid
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.files.base import ContentFile
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import AllowAny
from rest_framework.test import APITestCase

from submissions.models import ExternalGraderDetail, SubmissionFile
from submissions.permissions import IsXQueueUser
from submissions.tests.factories import ExternalGraderDetailFactory, SubmissionFactory
from submissions.views.xqueue import MAX_SCORE_UPDATE_RETRIES, XQueueViewSet

User = get_user_model()


class CsrfExemptSessionAuthentication(SessionAuthentication):
    def enforce_csrf(self, request):
        return  # Bypass CSRF checks for testing


@override_settings(ROOT_URLCONF='submissions.urls')
class TestXqueueViewSet(APITestCase):
    """
    Test cases for XQueueViewSet endpoints.
    """

    def setUp(self):
        """Set up test data."""
        super().setUp()
        self._orig_auth_classes = XQueueViewSet.authentication_classes
        XQueueViewSet.authentication_classes = [CsrfExemptSessionAuthentication]

        # Ensure the 'xqueue' group exists and add the user to it
        xqueue_group, _ = Group.objects.get_or_create(name='xqueue')
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass'
        )
        self.user.groups.add(xqueue_group)
        self.user.save()

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
        self.viewset = XQueueViewSet()

    def tearDown(self):
        XQueueViewSet.authentication_classes = self._orig_auth_classes
        super().tearDown()

    def api_login(self):
        """Helper to login via the API and set session cookie for subsequent requests."""
        data = {'username': 'testuser', 'password': 'testpass'}
        response = self.client.post(self.url_login, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Set sessionid cookie for subsequent requests
        if 'sessionid' in response.cookies:
            self.client.cookies['sessionid'] = response.cookies['sessionid'].value

    def test_get_permissions_login(self):
        """Test permissions for login endpoint"""
        viewset = XQueueViewSet()
        viewset.action = 'login'
        permissions = viewset.get_permissions()
        self.assertTrue(any(isinstance(p, AllowAny) for p in permissions))

    def test_get_permissions_other_actions(self):
        """Test permissions for non-login endpoints"""
        viewset = XQueueViewSet()
        viewset.action = 'logout'
        permissions = viewset.get_permissions()
        self.assertTrue(all(isinstance(p, IsXQueueUser) for p in permissions))

    def test_dispatch_valid_session(self):
        """Test dispatch with valid session"""
        self.client.login(username='testuser', password='testpass')
        response = self.client.post(self.url_status)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_dispatch_invalid_session(self):
        """Test dispatch with invalid session"""
        # No login, should get 403
        response = self.client.get(self.url_status)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

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
        self.assertEqual(response.status_code, status.HTTP_200_OK)  # Cambiado de 404
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
            'xqueue_body': json.dumps({'score': 1})  # Cambiado a entero
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
            'xqueue_body': json.dumps({'score': 1})  # Cambiado a entero
        }

        response = self.client.post(self.url_put_result, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        response_data = json.loads(response.content)
        self.assertEqual(
            response_data,
            self.viewset.compose_reply(False, 'Incorrect key for submission')
        )

    def test_put_result_invalid_reply_format(self):
        """Test put_result with invalid reply format to cover lines 191-193."""
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
            'xqueue_body': json.dumps({'score': 1})
        }

        with patch('submissions.views.xqueue.set_score') as mock_set_score:
            mock_set_score.side_effect = Exception('Test error')
            response = self.client.post(self.url_put_result, payload, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Verificar que external_grader status cambió a 'failed'
        self.external_grader.refresh_from_db()
        self.assertEqual(self.external_grader.num_failures, 1)
        self.assertEqual(self.external_grader.status, 'retry')

    def test_put_result_set_score_fail_multiple_times(self):
        """
        Test put_result handling when set_score by intentionally failing multiple times.
        """
        self.client.login(username='testuser', password='testpass')
        response = self.client.post(self.url_status)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        for each in range(MAX_SCORE_UPDATE_RETRIES+1):
            with patch('submissions.views.xqueue.set_score') as mock_set_score:
                mock_set_score.side_effect = Exception('Test error')  # Make it actually fail
                # Ensure the external grader is in the right state for pulling
                # If it's failed, we need to reset it to pending first, then to pulled
                if self.external_grader.status == 'failed':
                    self.external_grader.update_status('pending')
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
            'xqueue_body': json.dumps({'score': 1})  # Cambiado a entero
        }

        with patch('submissions.api.set_score') as mock_set_score:
            self.client.login(username='testuser', password='testpass')
            response = self.client.post(self.url_status)
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            mock_set_score.return_value = True
            response = self.client.post(self.url_put_result, payload, format='json')

        submission_context = {
                'submission_id': self.submission.id,
                'course_id': self.submission.student_item.course_id,
                'user_id': self.submission.student_item.student_id,
                'item_id': self.submission.student_item.item_id,
                'queue_name': self.external_grader.queue_name,
                'queue_key': self.external_grader.queue_key,
            }
        mock_log.info.assert_any_call(
            "Successfully updated submission %(submission_id)s for user %(user_id)s",
            submission_context
        )

        response_data = json.loads(response.content)
        self.assertEqual(
            response_data,
            self.viewset.compose_reply(True, '')
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

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

    @patch('submissions.views.xqueue.get_files_for_grader')
    def test_get_submission_value_error(self, mock_get_files):
        """Test get_submission when processing raises ValueError."""
        queue_name = 'test_queue'
        self.client.login(username='testuser', password='testpass')

        # Use the existing external grader from setUp and update its queue_name and status
        self.external_grader.queue_name = queue_name
        self.external_grader.status = 'pending'
        self.external_grader.save()

        # Mock get_files_for_grader to raise ValueError to test the exception handler
        mock_get_files.side_effect = ValueError("File processing error")

        response = self.client.get(self.get_submission_url, {'queue_name': queue_name})

        self.assertEqual(response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)
        self.assertEqual(response.data['return_code'], 1)
        self.assertIn("Unable to serialize submission payload", response.data['content'])
