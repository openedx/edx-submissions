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
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from submissions.api import get_files_for_grader, set_score
from submissions.errors import SubmissionInternalError, SubmissionNotFoundError
from submissions.models import ExternalGraderDetail

log = logging.getLogger(__name__)


class XqueueViewSet(viewsets.ViewSet):
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
            permission_classes = [IsAuthenticated]
        return [permission() for permission in permission_classes]

    @action(detail=False, methods=['post'], url_name='login')
    def login(self, request):
        """
        Endpoint for authenticating users and creating sessions.
        """
        log.info(f"Login attempt with data: {request.data}")

        if 'username' not in request.data or 'password' not in request.data:
            return Response(
                {'return_code': 1, 'content': 'Insufficient login info'},
                status=status.HTTP_400_BAD_REQUEST
            )

        user = authenticate(
            request,
            username=request.data['username'],
            password=request.data['password']
        )

        if user is not None:
            login(request, user)
            response = Response(
                {'return_code': 0, 'content': 'Logged in'},
                status=status.HTTP_200_OK
            )

            return response

        return Response(
            {'return_code': 1, 'content': 'Incorrect login credentials'},
            status=status.HTTP_401_UNAUTHORIZED
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
            return Response(
                self.compose_reply(False, "'get_submission' must provide parameter 'queue_name'"),
                status=status.HTTP_400_BAD_REQUEST
            )

        timeout_threshold = timezone.now() - timedelta(minutes=5)
        try:
            external_grader = (
                ExternalGraderDetail.objects
                .select_for_update(nowait=True)
                .filter(
                    Q(queue_name=queue_name, status='pending') |
                    Q(queue_name=queue_name, status='retry') |
                    Q(queue_name=queue_name, status='pulled', status_time__lt=timeout_threshold)
                )
                .select_related('submission')
                .order_by('status_time')
                .first()
            )
        except DatabaseError:
            return Response(
                self.compose_reply(False, "Submission already in process"),
                status=status.HTTP_409_CONFLICT
            )

        if external_grader:
            try:
                if external_grader.status != "pulled":
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
                    'xqueue_files': json.dumps(get_files_for_grader(external_grader))
                }

                return Response(
                    self.compose_reply(True, content=json.dumps(payload)),
                    status=status.HTTP_200_OK
                )

            except ValueError as e:
                return Response(
                    self.compose_reply(False, f"Error processing submission: {str(e)}"),
                    status=status.HTTP_400_BAD_REQUEST
                )

        return Response(
            self.compose_reply(False, f"Queue '{queue_name}' is empty"),
            status=status.HTTP_404_NOT_FOUND
        )

    @action(detail=False, methods=['post'], url_name='put_result')
    @transaction.atomic
    def put_result(self, request):
        """
        Endpoint for graders to post their results and update submission scores.
        """
        (reply_valid, submission_id, submission_key, score_msg, points_earned) = (
            self.validate_grader_reply(request.data))

        if not reply_valid:
            log.error("Invalid reply from pull-grader: request.data: %s",
                      request.data)
            return Response(
                self.compose_reply(False, 'Incorrect reply format'),
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            external_grader = ExternalGraderDetail.objects.select_for_update(
                                                                        nowait=True).get(submission__id=submission_id)
        except ExternalGraderDetail.DoesNotExist:
            log.error(
                "Grader submission_id refers to nonexistent entry in Submission DB: "
                "grader: %s, submission_key: %s, score_msg: %s",
                submission_id,
                submission_key,
                score_msg
            )
            return Response(
                self.compose_reply(False, 'Submission does not exist'),
                status=status.HTTP_404_NOT_FOUND
            )

        if not external_grader.pullkey or submission_key != external_grader.pullkey:
            log.error(f"Invalid pullkey: submission key from xwatcher {submission_key} "
                      f"and submission key stored {external_grader.pullkey} are different")
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
            external_grader.update_status('retired', score_msg)
            log.info("Successfully updated submission score for submission %s", submission_id)

        except (SubmissionNotFoundError, DatabaseError, SubmissionInternalError) as e:
            log.exception("Error when executing set_score: %s", type(e).__name__)
            external_grader.update_status("failed", score_msg)

        return Response(self.compose_reply(success=True, content=''))

    def validate_grader_reply(self, external_reply):
        """
        Validate the format of external grader reply.

        Returns:
            tuple: (is_valid, submission_id, submission_key, score_msg)
        """
        fail = (False, -1, '', '', '')

        if not isinstance(external_reply, dict):
            return fail

        try:
            header = external_reply['xqueue_header']
            score_msg = external_reply['xqueue_body']
        except KeyError:
            return fail

        try:
            header_dict = json.loads(header)
        except (TypeError, ValueError):
            return fail

        try:
            score = json.loads(score_msg)
            points_earned = score.get("score")
        except (TypeError, ValueError):
            return fail

        if not isinstance(header_dict, dict):
            return fail

        for tag in ['submission_id', 'submission_key']:
            if tag not in header_dict:
                return fail

        submission_id = int(header_dict['submission_id'])
        submission_key = header_dict['submission_key']

        return (True, submission_id, submission_key, score_msg, points_earned)

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
