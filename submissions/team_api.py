"""
Public interface for team submissions API.
"""

import logging

from django.db import DatabaseError, transaction

from submissions import api as _api
from submissions.errors import TeamSubmissionInternalError, TeamSubmissionRequestError
from submissions.models import TeamSubmission
from submissions.serializers import TeamSubmissionSerializer

logger = logging.getLogger(__name__)


@transaction.atomic
def create_submission_for_team(
    course_id,
    item_id,
    team_id,
    submitting_user_id,
    team_member_ids,
    answer,
    submitted_at=None,
    attempt_number=1,
    item_type='openassessment',
):
    """
    This api function:
      1. Creates a `TeamSubmission` record, and
      2. Creates `Submission` records for every member of the team by calling api.create_submission()

    This means that the ORA `SubmissionMixin` must first collect all of the files of the submitting user
    and the team into the `answer` dict.

    Returns:
        dict: A representation of the created TeamSubmission, with the following keys:
          'team_submission_uuid' Is the `uuid` field of the created `TeamSubmission`.
          'course_id' Is the ID of the course.
          'item_id' Is the ID of the item (e.g. the block).
          'team_id' Is the ID of the team.
          'submitted_by' Is the ID of the submitting user (same as `submitting_user_id`)
          'attempt_number' is the attempt number this submission represents for this question.
          'submitted_at' represents the time this submission was submitted, which can be configured, versus the...
          'created_at' date, which is when the submission is first created.
          'submission_uuids' Is a list of the UUIDs of each of the individual `Submission` records that is created.

    Raises:
        TeamSubmissionRequestError: Raised when there are validation errors for the
            student item or team submission. This can be caused by the student item
            missing required values, the submission being too long, the
            attempt_number is negative, or the given submitted_at time is invalid.
        SubmissionRequestError: Raised when there are validation errors for the underlying
            student item or submission. This can be caused by the same reason as
            the TeamSubmissionRequestError
        TeamSubmissionInternalError: Raised when submission access causes an
            internal error.
        TeamSubmissionInternalError: Raised when submission access causes an
            internal error when creating the underlying submissions.

    Examples:
        >>>course_id = "course_1"
        >>>item_id = "item_1"
        >>>team_id = "A Team"
        >>>submitting_user_id = "Tim"
        >>>team_member_ids = ["Alice", "Bob", "Carol", "Tim"]
        >>>answer = "The answer is 42."
        >>> )
        >>> create_submission_for_team(
                course_id, item_id, team_id, submitting_user_id, team_member_ids, answer, datetime.utcnow, 1
            )
        {
            'team_submission_uuid': 'blah',
            'course_id': "course_1",
            'item_id': "item_1",
            'team_id': "A Team",
            'submitted_by': "Tim",
            'attempt_number': 1,
            'submitted_at': datetime.datetime(2014, 1, 29, 17, 14, 52, 649284 tzinfo=<UTC>),
            'created_at': datetime.datetime(2014, 1, 29, 17, 14, 52, 668850, tzinfo=<UTC>),
            'answer': u'The answer is 42.',
            'submission_uuids': ['alice-uuid', 'bob-uuid', 'carol-uuid', 'tim-uuid'],
        }
    """

    # I have no clue what to do with attempt_number. The normal API checks if there are any duplicate submissions and
    # incrememnts attempt_number, but we prevent duplicate team submissions, so I can't copy that logic flow.
    # I thought maybe we should look for deleted submissions and incrememnt based of of that, but looking at
    # production data I can't find a single case where that happens.
    # For now ... I'm just gonna default it to 1?

    model_kwargs = {
        'course_id': course_id,
        'item_id': item_id,
        'team_id': team_id,
        'submitted_by': submitting_user_id,
        'attempt_number': attempt_number,
    }
    if submitted_at:
        model_kwargs["submitted_at"] = submitted_at

    try:
        team_submission_serializer = TeamSubmissionSerializer(data=model_kwargs, context={'answer': answer})
        if not team_submission_serializer.is_valid():
            raise TeamSubmissionRequestError(field_errors=team_submission_serializer.errors)
        team_submission = team_submission_serializer.save()
        _log_team_submission(team_submission_serializer.data)
    except DatabaseError as exc:
        error_message = "An error occurred while creating team submission {}: {}".format(
            model_kwargs,
            exc
        )
        logger.exception(error_message)
        raise TeamSubmissionInternalError(error_message)

    base_student_item_dict = {
        'course_id': course_id,
        'item_id': item_id,
        'item_type': item_type
    }
    for team_member_id in team_member_ids:
        team_member_student_item_dict = dict(base_student_item_dict)
        team_member_student_item_dict['student_id'] = team_member_id
        _api.create_submission(
            team_member_student_item_dict,
            answer,
            submitted_at=submitted_at,
            attempt_number=attempt_number,
            team_submission=team_submission
        )

    model_kwargs = {
        "answer": answer,
    }
    # We must serialize the model, since the existing serializer doesn't have info about the individual submissions
    model_serializer = TeamSubmissionSerializer(team_submission, context={"answer": answer})
    return model_serializer.data


def _log_team_submission(team_submission_data):
    """
    Log the creation of a team submission.

    Args:
        team_submission_data (dict): The serialized team submission model.

    Returns:
        None
    """
    logger.info(
        "Created team submission uuid={team_submission_uuid} for "
        "(course_id={course_id}, item_id={item_id}, team_id={team_id}) "
        "submitted_by={submitted_by}"
        .format(
            team_submission_uuid=team_submission_data["team_submission_uuid"],
            course_id=team_submission_data["course_id"],
            item_id=team_submission_data["item_id"],
            team_id=team_submission_data["team_id"],
            submitted_by=team_submission_data["submitted_by"],
        )
    )


def get_team_submission(team_submission_uuid):
    """
    Returns a single, serialized, team submission for the given key.

    Raises:
        - TeamSubmissionNotFoundError when no such team submission exists.
        - TeamSubmissionInternalError if there is some other error looking up the team submission.
    """
    team_submission = TeamSubmission.get_team_submission_by_uuid(team_submission_uuid)
    return TeamSubmissionSerializer(team_submission).data


def get_team_submission_for_team(course_id, item_id, team_id):
    """
    Returns a single team submission (serialized) for the given team in the given (course, item).

    Raises:
        - TeamSubmissionNotFoundError when no such team submission exists.
        - TeamSubmissionInternalError if there is some other error looking up the team submission.
    """
    team_submission = TeamSubmission.get_team_submission_by_course_item_team(course_id, item_id, team_id)
    return TeamSubmissionSerializer(team_submission).data


def get_all_team_submissions(course_id, item_id):
    """
    Returns all of the (active) team submissions (serialized) in the given (course, item).

    Returns an empty iterable if no team submissions exist for this (course, item).

    Raises:
        - TeamSubmissionInternalError if there is some other error looking up the team submission.
    """
    team_submissions = TeamSubmission.get_all_team_submissions_for_course_item(course_id, item_id)
    return TeamSubmissionSerializer(team_submissions, many=True).data


def set_score(team_submission_uuid, points_earned, points_possible,
              annotation_creator=None, annotation_type=None, annotation_reason=None):
    """Set a score for a particular team submission.  This score is calculated
    externally to the API.  Should call _api.set_score(...) for each child submission
    of the TeamSubmission.

    Args:
        team_submission_uuid (str): UUID for the team submission (must exist).
        points_earned (int): The earned points for this submission.
        points_possible (int): The total points possible for this particular student item.

        annotation_creator (str): An optional field for recording who gave this particular score
        annotation_type (str): An optional field for recording what type of annotation should be created,
                                e.g. "staff_override".
        annotation_reason (str): An optional field for recording why this score was set to its value.

    Returns:
        None

    Raises:
        TeamSubmissionNotFoundError if the specified team submission does not exist
        TeamSubmissionInternalError if there was an internal error when looking up the submission
        SubmissionNotFoundError if a child submission could not be found
        SubmissionRequestError if there is an error looking up a child submission
        SubmissionInternalError if there is an error saving an individual error

    """
    team_submission_dict = get_team_submission(team_submission_uuid)
    debug_msg = (
        'Setting score for team submission uuid {uuid}, child submission uuids {individual_uuids}. '
        '{earned} / {possible}'
    ).format(
        uuid=team_submission_dict['team_submission_uuid'],
        individual_uuids=team_submission_dict['submission_uuids'],
        earned=points_earned,
        possible=points_possible
    )
    logger.info(debug_msg)

    with transaction.atomic():
        for individual_submission_uuid in team_submission_dict['submission_uuids']:
            _api.set_score(
                individual_submission_uuid,
                points_earned, points_possible,
                annotation_creator,
                annotation_type,
                annotation_reason
            )
