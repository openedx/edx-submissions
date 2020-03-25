"""
Public interface for team submissions API.
"""

# We're going to need common things like `SubmissionError`
from submissions import api as _api

# Consider creating new types of exceptions that are specific to teams, e.g.
class TeamSubmissionNotFoundError(_api.SubmissionNotFoundError):
    pass


def create_submission_for_team(
        course_id, item_id, team_id, submitting_user_id, team_member_ids, answer, submitted_at=None, attempt_number=None
):
    """
    For now, let's take the position that this will:
      1. Create a `TeamSubmission` record, and
      2. Create `Submission` records for every member of the team.

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
        SubmissionRequestError: Raised when there are validation errors for the
            student item or submission. This can be caused by the student item
            missing required values, the submission being too long, the
            attempt_number is negative, or the given submitted_at time is invalid.
        SubmissionInternalError: Raised when submission access causes an
            internal error.

    Examples:
        >>>submitting_user_id = "Tim"
        >>>item_id = "item_1"
        >>>course_id = "course_1"
        >>>team_id = "A Team"
        >>>team_member_ids = ["Alice", "Bob", "Carol", "Tim"]
        >>>answer = "The answer is 42."
        >>> )
        >>> create_submission_for_team(
                course_id, item_id, team_id, submitting_user_id, team_member_ids, answer, datetime.utcnow, 1
            )
        {
            'team_submission_uuid': 'blah',
            'item_id': "item_1",
            'course_id': "course_1",
            'team_id': "A Team",
            'submitted_by': "Tim",
            'attempt_number': 1,
            'submitted_at': datetime.datetime(2014, 1, 29, 17, 14, 52, 649284 tzinfo=<UTC>),
            'created_at': datetime.datetime(2014, 1, 29, 17, 14, 52, 668850, tzinfo=<UTC>),
            'answer': u'The answer is 42.',
            'submission_uuids': ['alice-uuid', 'bob-uuid', 'carol-uuid', 'tim-uuid'],
        }
    """
    raise NotImplementedError


def get_team_submission(team_submission_uuid):
    """
    Returns a single, serialized, team submission for the given key.

    Remember that there’s a FK b/w Submission and TeamSubmission, so from the team submission,
    you can get the “child” submission UUIDs.

    A note about that `api._get_submission_model()` function: we shouldn't have to do that here.
    That helper exists to address a bug (https://openedx.atlassian.net/browse/EDUCATOR-1090)
    that arose due to switching the default type of UUID value that was stored for the `Submission.uuid` field.
    """
    raise NotImplementedError


def get_team_submission_for_team(team_id, course_id, item_id):
    """
    Returns the (active) team submission (serialized) for the given team in the given (course, item).

    Should raise a TeamSubmissionNotFoundError when no such team submission exists.
    """
    raise NotImplementedError


def get_all_team_submissions(course_id, item_id):
    """
    Returns all of the (active) team submission (serialized) in the given (course, item).

    May return an empty iterable if no team submissions exist for this (course, item).
    """
    raise NotImplementedError



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
        SubmissionInternalError: Thrown if there was an internal error while
            attempting to save the score.
        SubmissionRequestError: Thrown if the given student item or submission
            are not found.
    """
    raise NotImplementedError
