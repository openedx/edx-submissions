"""Xqueue View set"""

import json
import logging
from datetime import timedelta

from django.contrib.auth import authenticate, login, logout
from django.db import DatabaseError, transaction
from django.db.models import Q
from django.http import HttpResponse
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.authentication import SessionAuthentication
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from submissions.api import get_files_for_grader, set_score
from submissions.errors import SubmissionInternalError, SubmissionNotFoundError
from submissions.models import ExternalGraderDetail
from submissions.permissions import IsXQueueUser

log = logging.getLogger(__name__)


class XQueueViewSet(viewsets.ViewSet):
    """
    A collection of services for xqueue-watcher interactions and authentication.

    This ViewSet provides endpoints for managing external grader results
    and handling user authentication in the system.

    Key features:
    - Handles validation of external grader responses
    - Processes and updates submission scores
    - Provides a secure endpoint for result updates
    - Manages user authentication and session handling

    Endpoints:
    - put_result: Endpoint for graders to submit their assessment results
    - get_submission: Endpoint for fetch pending submissions
    - login: Endpoint for user authentication
    - logout: Endpoint for ending user sessions

    HTTP Status Codes:
    In contrast to previous implementations that always returned HTTP 200 status
    codes and relied solely on the JSON response body to indicate success or failure,
    this implementation returns HTTP status codes that more accurately reflect the
    outcome of each request (such as 400, 401, 403, or 404 for error conditions).
    This change improves API clarity and error handling.

    NOTE: This viewset is intentionally re-building an API-compatible implementation for
    xqueue-watcher. Some non-standard choices (such as response formats and status code
    handling) are made to maintain compatibility with the legacy xqueue-watcher client.
    For more context, see DEPR: https://github.com/openedx/public-engineering/issues/286.
    """

    authentication_classes = [SessionAuthentication]  # Xqueue watcher auth method

    def get_permissions(self):
        """
        Override to implement custom permission logic per action.
        - Login endpoint is public
        - All other endpoints require authentication
        """
        if self.action == 'login':
            permission_classes = [AllowAny]
        else:
            permission_classes = [IsXQueueUser]
        return [permission() for permission in permission_classes]

    @action(detail=False, methods=['post'], url_name='login')
    def login(self, request):
        """
        Endpoint for authenticating users and creating sessions.
        """

        if 'username' not in request.data or 'password' not in request.data:
            log.error('XQueue insufficient login info')
            return Response(
                self.compose_reply(False, 'Insufficient login info'),
                status=status.HTTP_400_BAD_REQUEST
            )

        user = authenticate(
            request,
            username=request.data['username'],
            password=request.data['password']
        )

        if user is None:
            log.error('XQueue username or password incorrect')
            return Response(
                self.compose_reply(False, 'Incorrect login credentials'),
                status=status.HTTP_401_UNAUTHORIZED
            )

        login(request, user)
        log.info(f'XQueue user logged in {request.user.username}')
        return Response(
            self.compose_reply(True, 'Logged in'),
            status=status.HTTP_200_OK
        )

    @action(detail=False, methods=['post'], url_name='logout')
    def logout(self, request):
        """
        Endpoint for ending user sessions.
        """
        logout(request)
        return Response(
            self.compose_reply(True, 'Goodbye'),
            status=status.HTTP_200_OK
        )

    @action(detail=False, methods=['get'], url_name='get_submission')
    @transaction.atomic
    def get_submission(self, request):
        """
        Endpoint for retrieving a single unprocessed submission from a specified queue.
        Query Parameters:
        - queue_name (required): Name of the queue to pull from
        Returns:
        - Submission data with pull information if successful
        - Error message if queue is empty or invalid
        """
        queue_name = request.query_params.get('queue_name')

        if not queue_name:
            log.error("'get_submission' must provide parameter 'queue_name'")
            return Response(
                self.compose_reply(False, "'get_submission' must provide parameter 'queue_name'"),
                status=status.HTTP_400_BAD_REQUEST
            )

        timeout_threshold = timezone.now() - timedelta(minutes=5)
        # DatabaseError handling was removed because with skip_locked=True, locking conflicts
        # are avoided and this exception is no longer expected here.
        external_grader = (
            ExternalGraderDetail.objects
            .select_for_update(skip_locked=True)
            .filter(
                Q(queue_name=queue_name, status='pending') |
                Q(queue_name=queue_name, status='pulled', status_time__lt=timeout_threshold)
            )
            .select_related('submission')
            .order_by('status_time')
            .first()
        )

        if external_grader:
            external_grader.update_status("pulled")
            submission_data = {
                "grader_payload": json.dumps({"grader": external_grader.grader_file_name}),
                "student_info": json.dumps({
                    "anonymous_student_id": str(external_grader.submission.student_item.student_id),
                    "submission_time": str(int(external_grader.created_at.timestamp())),
                    "random_seed": 1
                }),
                "student_response": external_grader.submission.answer
            }

            payload = {
                'xqueue_header': json.dumps({
                    'submission_id': external_grader.submission.id,
                    'submission_key': external_grader.pullkey
                }),
                'xqueue_body': json.dumps(submission_data),
                # Xqueue watcher expects this to be a JSON string
                'xqueue_files': json.dumps(get_files_for_grader(external_grader))
            }

            return Response(
                self.compose_reply(True, content=json.dumps(payload)),
                status=status.HTTP_200_OK
            )

        return Response(
            self.compose_reply(False, f"Queue '{queue_name}' is empty"),
            status=status.HTTP_200_OK
        )

    @action(detail=False, methods=['post'], url_name='put_result')
    @transaction.atomic
    def put_result(self, request):
        """
        Endpoint for graders to post their results and update submission scores.
        """
        (reply_valid, submission_id, submission_key, grader_reply, points_earned) = (
            self.validate_grader_reply(request.data))

        if not reply_valid:
            log.error("Invalid reply from pull-grader: request.data: %s",
                      request.data)
            return Response(
                self.compose_reply(False, 'Incorrect reply format'),
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            external_grader = (
                ExternalGraderDetail.objects.select_for_update(skip_locked=True).get(submission__id=submission_id)
            )
        except ExternalGraderDetail.DoesNotExist:
            log.error(
                "Grader submission_id refers to nonexistent entry in Submission DB: "
                "submission_id: %s, submission_key: %s, grader_reply: %s",
                submission_id,
                submission_key,
                grader_reply
            )
            return Response(
                self.compose_reply(False, 'Submission does not exist'),
                status=status.HTTP_404_NOT_FOUND
            )

        if not external_grader.pullkey or submission_key != external_grader.pullkey:
            log.error(
                "Invalid pullkey for submission_id %s: received '%s', expected '%s'",
                submission_id,
                submission_key,
                external_grader.pullkey
            )
            return Response(
                self.compose_reply(False, 'Incorrect key for submission'),
                status=status.HTTP_403_FORBIDDEN
            )

        try:
            log.info("Attempting to set_score...")
            set_score(str(external_grader.submission.uuid),
                      points_earned,
                      external_grader.points_possible
                      )
            external_grader.update_status('retired', grader_reply)
            log.info("Successfully updated submission score for submission %s", submission_id)

        except (SubmissionNotFoundError, DatabaseError, SubmissionInternalError) as e:
            log.exception("Error when executing set_score: %s", type(e).__name__)
            external_grader.update_status("failed", grader_reply)

        return Response(self.compose_reply(success=True, content=''))

    def validate_grader_reply(self, external_reply):
        """
        Validate the format of external grader reply.

        Returns:
            tuple: (is_valid, submission_id, submission_key, grader_reply)
        """
        fail = (False, -1, '', '', '')

        if not isinstance(external_reply, dict):
            return fail

        try:
            header = external_reply['xqueue_header']
            grader_reply = external_reply['xqueue_body']
        except KeyError:
            return fail

        try:
            header_dict = json.loads(header)
        except (TypeError, ValueError):
            return fail

        try:
            score = json.loads(grader_reply)
            points_earned = score.get("score")
        except (TypeError, ValueError) as e:
            log.error("Failed to parse grader_reply as JSON or extract score: %s. Raw grader_reply: %s",
                      str(e), grader_reply)
            return fail

        if not isinstance(header_dict, dict):
            return fail

        for tag in ['submission_id', 'submission_key']:
            if tag not in header_dict:
                return fail

        submission_id = int(header_dict['submission_id'])
        submission_key = header_dict['submission_key']

        return (True, submission_id, submission_key, grader_reply, points_earned)

    def compose_reply(self, success, content):
        """
        Compose response in Xqueue format.

        Args:
            success (bool): Whether the operation was successful
            content (str): Response message

        Returns:
            dict: Formatted response
        """
        return {
            'return_code': 0 if success else 1,
            'content': content
        }

    @action(detail=False, methods=['post'], url_name='status')
    def status(self, _):
        return HttpResponse(self.compose_reply(success=True, content='OK'))
