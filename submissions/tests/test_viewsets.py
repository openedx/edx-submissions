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
from django.db import DatabaseError
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import AllowAny
from rest_framework.test import APITestCase

from submissions.errors import SubmissionInternalError, SubmissionNotFoundError
from submissions.models import ExternalGraderDetail, SubmissionFile
from submissions.permissions import IsXQueueUser
from submissions.tests.factories import ExternalGraderDetailFactory, SubmissionFactory
from submissions.views.xqueue import XQueueViewSet

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

        # Test case 1: Empty dict - will fail at validate_grader_reply because missing keys
        # This will trigger lines 191-193 since validate_grader_reply returns False
        invalid_payload = {}
        response = self.client.post(self.url_put_result, invalid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            response.data,
            self.viewset.compose_reply(False, 'Incorrect reply format')
        )

        # Test case 2: Dict with wrong keys - also triggers validate_grader_reply to return False
        invalid_payload = {'wrong_key': 'wrong_value'}
        response = self.client.post(self.url_put_result, invalid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            response.data,
            self.viewset.compose_reply(False, 'Incorrect reply format')
        )

        # Test case 3: Dict with only one required key missing
        invalid_payload = {'xqueue_header': '{"submission_id": 1, "submission_key": "key"}'}
        # Missing xqueue_body
        response = self.client.post(self.url_put_result, invalid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            response.data,
            self.viewset.compose_reply(False, 'Incorrect reply format')
        )

    @patch('submissions.views.xqueue.set_score')
    def test_put_result_set_score_exceptions(self, mock_set_score):
        """Test put_result when set_score raises exceptions."""
        self.client.login(username='testuser', password='testpass')

        payload = {
            'xqueue_header': json.dumps({
                'submission_id': self.submission.id,
                'submission_key': 'test_pull_key'
            }),
            'xqueue_body': json.dumps({'score': 1})
        }

        # Test SubmissionNotFoundError
        mock_set_score.side_effect = SubmissionNotFoundError("Submission not found")
        response = self.client.post(self.url_put_result, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Verificar que external_grader status cambió a 'failed'
        self.external_grader.refresh_from_db()
        self.assertEqual(self.external_grader.status, 'failed')

        # Test DatabaseError
        mock_set_score.side_effect = DatabaseError("Database error")
        _ = self.client.post(self.url_put_result, payload, format='json')

        # Test SubmissionInternalError
        mock_set_score.side_effect = SubmissionInternalError("Internal error")
        _ = self.client.post(self.url_put_result, payload, format='json')

    def test_validate_grader_reply_not_dict(self):
        """Test validate_grader_reply with non-dict input."""
        viewset = XQueueViewSet()

        # Test con string
        result = viewset.validate_grader_reply("not_a_dict")
        self.assertEqual(result, (False, -1, '', '', ''))

        # Test con lista
        result = viewset.validate_grader_reply([1, 2, 3])
        self.assertEqual(result, (False, -1, '', '', ''))

        # Test con None
        result = viewset.validate_grader_reply(None)
        self.assertEqual(result, (False, -1, '', '', ''))

    def test_validate_grader_reply_missing_keys(self):
        """Test validate_grader_reply with missing required keys."""
        viewset = XQueueViewSet()

        # Test sin xqueue_header
        reply = {'xqueue_body': '{"score": 1}'}
        result = viewset.validate_grader_reply(reply)
        self.assertEqual(result, (False, -1, '', '', ''))

        # Test sin xqueue_body
        reply = {'xqueue_header': '{"submission_id": 1, "submission_key": "key"}'}
        result = viewset.validate_grader_reply(reply)
        self.assertEqual(result, (False, -1, '', '', ''))

        # Test sin ninguna key
        reply = {}
        result = viewset.validate_grader_reply(reply)
        self.assertEqual(result, (False, -1, '', '', ''))

    def test_validate_grader_reply_invalid_header_json(self):
        """Test validate_grader_reply with invalid JSON in header."""
        viewset = XQueueViewSet()

        # Test con header JSON inválido
        reply = {
            'xqueue_header': 'invalid_json{',
            'xqueue_body': '{"score": 1}'
        }
        result = viewset.validate_grader_reply(reply)
        self.assertEqual(result, (False, -1, '', '', ''))

        # Test con header None
        reply = {
            'xqueue_header': None,
            'xqueue_body': '{"score": 1}'
        }
        result = viewset.validate_grader_reply(reply)
        self.assertEqual(result, (False, -1, '', '', ''))

    @patch('submissions.views.xqueue.log')
    def test_validate_grader_reply_invalid_body_json(self, mock_log):
        """Test validate_grader_reply with invalid JSON in body."""
        viewset = XQueueViewSet()

        # Test con body JSON inválido
        reply = {
            'xqueue_header': '{"submission_id": 1, "submission_key": "key"}',
            'xqueue_body': 'invalid_json{'
        }
        result = viewset.validate_grader_reply(reply)
        self.assertEqual(result, (False, -1, '', '', ''))

        # Verificar que se loggeó el error
        mock_log.error.assert_called()

        # Test con body None
        reply = {
            'xqueue_header': '{"submission_id": 1, "submission_key": "key"}',
            'xqueue_body': None
        }
        result = viewset.validate_grader_reply(reply)
        self.assertEqual(result, (False, -1, '', '', ''))

    def test_validate_grader_reply_header_not_dict(self):
        """Test validate_grader_reply when parsed header is not a dict."""
        viewset = XQueueViewSet()

        # Test cuando header parsea a una lista
        reply = {
            'xqueue_header': '[1, 2, 3]',
            'xqueue_body': '{"score": 1}'
        }
        result = viewset.validate_grader_reply(reply)
        self.assertEqual(result, (False, -1, '', '', ''))

        # Test cuando header parsea a un string
        reply = {
            'xqueue_header': '"just_a_string"',
            'xqueue_body': '{"score": 1}'
        }
        result = viewset.validate_grader_reply(reply)
        self.assertEqual(result, (False, -1, '', '', ''))

    def test_validate_grader_reply_missing_header_keys(self):
        """Test validate_grader_reply with missing keys in header dict."""
        viewset = XQueueViewSet()

        # Test sin submission_id
        reply = {
            'xqueue_header': '{"submission_key": "key"}',
            'xqueue_body': '{"score": 1}'
        }
        result = viewset.validate_grader_reply(reply)
        self.assertEqual(result, (False, -1, '', '', ''))

        # Test sin submission_key
        reply = {
            'xqueue_header': '{"submission_id": 1}',
            'xqueue_body': '{"score": 1}'
        }
        result = viewset.validate_grader_reply(reply)
        self.assertEqual(result, (False, -1, '', '', ''))

        # Test con header dict vacío
        reply = {
            'xqueue_header': '{}',
            'xqueue_body': '{"score": 1}'
        }
        result = viewset.validate_grader_reply(reply)
        self.assertEqual(result, (False, -1, '', '', ''))

    @patch('submissions.views.xqueue.log')
    def test_put_result_success(self, mock_log):
        """
        Test that appropriate logging occurs in various scenarios.
        """
        self.client.login(username='testuser', password='testpass')

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
        self.assertIsNotNone(xqueue_header['submission_key'])  # Solo verificamos que existe

        self.external_grader.refresh_from_db()
        self.assertEqual(self.external_grader.status, 'pulled')

    def test_access_without_session(self):
        """Test access to protected endpoints without authentication session."""
        # Sin hacer login, intentar acceder a endpoints protegidos

        # Test get_submission sin sesión
        response = self.client.get(self.get_submission_url, {'queue_name': 'test_queue'})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        # Test put_result sin sesión
        payload = {
            'xqueue_header': json.dumps({
                'submission_id': self.submission.id,
                'submission_key': 'test_pull_key'
            }),
            'xqueue_body': json.dumps({'score': 1})
        }
        response = self.client.post(self.url_put_result, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        # Test logout sin sesión
        response = self.client.post(self.url_logout)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        # Test status sin sesión
        response = self.client.post(self.url_status)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_access_without_xqueue_group(self):
        """Test access to endpoints by authenticated user not in xqueue group."""
        # Crear un usuario que NO esté en el grupo xqueue
        _ = User.objects.create_user(
            username='non_xqueue_user',
            password='testpass'
        )
        # Intencionalmente NO agregamos el usuario al grupo xqueue

        # Login con el usuario que no está en grupo xqueue
        self.client.login(username='non_xqueue_user', password='testpass')

        # Test get_submission - debe fallar por falta de permisos
        response = self.client.get(self.get_submission_url, {'queue_name': 'test_queue'})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        # Test put_result - debe fallar por falta de permisos
        payload = {
            'xqueue_header': json.dumps({
                'submission_id': self.submission.id,
                'submission_key': 'test_pull_key'
            }),
            'xqueue_body': json.dumps({'score': 1})
        }
        response = self.client.post(self.url_put_result, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        # Test logout - debe fallar por falta de permisos
        response = self.client.post(self.url_logout)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        # Test status - debe fallar por falta de permisos
        response = self.client.post(self.url_status)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_login_endpoint_public_access(self):
        """Test that login endpoint is publicly accessible (no authentication required)."""
        # Login endpoint debe ser accesible sin autenticación previa

        # Test con credenciales válidas
        data = {
            'username': 'testuser',
            'password': 'testpass'
        }
        response = self.client.post(self.url_login, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['return_code'], 0)

        # Logout para probar sin sesión
        self.client.logout()

        # Test con credenciales inválidas - endpoint sigue siendo accesible
        data = {
            'username': 'testuser',
            'password': 'wrongpass'
        }
        response = self.client.post(self.url_login, data)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(response.data['return_code'], 1)

        # Test login sin credenciales - endpoint accesible pero falla validación
        response = self.client.post(self.url_login, {})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['return_code'], 1)

    def test_user_without_xqueue_group_can_login_but_not_access_other_endpoints(self):
        """Test that user not in xqueue group can login but can't access protected endpoints."""
        # Crear usuario sin grupo xqueue
        _ = User.objects.create_user(
            username='non_xqueue_user_2',
            password='testpass'
        )

        # Login debe funcionar (endpoint público)
        data = {
            'username': 'non_xqueue_user_2',
            'password': 'testpass'
        }
        response = self.client.post(self.url_login, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['return_code'], 0)

        # Pero otros endpoints deben fallar por falta de permisos de grupo
        response = self.client.get(self.get_submission_url, {'queue_name': 'test_queue'})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        payload = {
            'xqueue_header': json.dumps({
                'submission_id': self.submission.id,
                'submission_key': 'test_pull_key'
            }),
            'xqueue_body': json.dumps({'score': 1})
        }
        response = self.client.post(self.url_put_result, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
