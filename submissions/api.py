"""
Public interface for the submissions app.

"""
from __future__ import absolute_import

import itertools
import logging
import operator
from uuid import UUID

import six
from django.conf import settings
from django.core.cache import cache
from django.db import DatabaseError, IntegrityError, transaction

# SubmissionError imported so that code importing this api has access
from submissions.errors import (  # pylint: disable=unused-import
    SubmissionError,
    SubmissionInternalError,
    SubmissionNotFoundError,
    SubmissionRequestError
)
from submissions.models import (
    DELETED,
    Score,
    ScoreAnnotation,
    ScoreSummary,
    StudentItem,
    Submission,
    score_reset,
    score_set
)
from submissions.serializers import (
    ScoreSerializer,
    StudentItemSerializer,
    SubmissionSerializer,
    UnannotatedScoreSerializer
)

logger = logging.getLogger("submissions.api")


# By default, limit the number of top submissions
# Anything above this limit will result in a request error
MAX_TOP_SUBMISSIONS = 100

# Set a relatively low cache timeout for top submissions.
TOP_SUBMISSIONS_CACHE_TIMEOUT = 300


def create_submission(student_item_dict, answer, submitted_at=None, attempt_number=None, team_submission=None):
    """Creates a submission for assessment.

    Generic means by which to submit an answer for assessment.

    Args:
        student_item_dict (dict): The student_item this
            submission is associated with. This is used to determine which
            course, student, and location this submission belongs to.

        answer (JSON-serializable): The answer given by the student to be assessed.

        submitted_at (datetime): The date in which this submission was submitted.
            If not specified, defaults to the current date.

        attempt_number (int): A student may be able to submit multiple attempts
            per question. This allows the designated attempt to be overridden.
            If the attempt is not specified, it will take the most recent
            submission, as specified by the submitted_at time, and use its
            attempt_number plus one.

    Returns:
        dict: A representation of the created Submission. The submission
        contains five attributes: student_item, attempt_number, submitted_at,
        created_at, and answer. 'student_item' is the ID of the related student
        item for the submission. 'attempt_number' is the attempt this submission
        represents for this question. 'submitted_at' represents the time this
        submission was submitted, which can be configured, versus the
        'created_at' date, which is when the submission is first created.

    Raises:
        SubmissionRequestError: Raised when there are validation errors for the
            student item or submission. This can be caused by the student item
            missing required values, the submission being too long, the
            attempt_number is negative, or the given submitted_at time is invalid.
        SubmissionInternalError: Raised when submission access causes an
            internal error.

    Examples:
        >>> student_item_dict = dict(
        >>>    student_id="Tim",
        >>>    item_id="item_1",
        >>>    course_id="course_1",
        >>>    item_type="type_one"
        >>> )
        >>> create_submission(student_item_dict, "The answer is 42.", datetime.utcnow, 1)
        {
            'student_item': 2,
            'attempt_number': 1,
            'submitted_at': datetime.datetime(2014, 1, 29, 17, 14, 52, 649284 tzinfo=<UTC>),
            'created_at': datetime.datetime(2014, 1, 29, 17, 14, 52, 668850, tzinfo=<UTC>),
            'answer': u'The answer is 42.'
        }

    """
    student_item_model = _get_or_create_student_item(student_item_dict)
    if attempt_number is None:
        first_submission = None
        attempt_number = 1
        try:
            first_submission = Submission.objects.filter(student_item=student_item_model).first()
        except DatabaseError:
            error_message = u"An error occurred while filtering submissions for student item: {}".format(
                student_item_dict)
            logger.exception(error_message)
            raise SubmissionInternalError(error_message)

        if first_submission:
            attempt_number = first_submission.attempt_number + 1

    model_kwargs = {
        "student_item": student_item_model.pk,
        "answer": answer,
        "attempt_number": attempt_number,
    }
    if submitted_at:
        model_kwargs["submitted_at"] = submitted_at
    if team_submission:
        model_kwargs["team_submission_uuid"] = team_submission.uuid

    try:
        submission_serializer = SubmissionSerializer(data=model_kwargs)
        if not submission_serializer.is_valid():
            raise SubmissionRequestError(field_errors=submission_serializer.errors)
        submission_serializer.save()

        sub_data = submission_serializer.data
        _log_submission(sub_data, student_item_dict)

        return sub_data

    except DatabaseError:
        error_message = u"An error occurred while creating submission {} for student item: {}".format(
            model_kwargs,
            student_item_dict
        )
        logger.exception(error_message)
        raise SubmissionInternalError(error_message)


def _get_submission_model(uuid, read_replica=False):
    """
    Helper to retrieve a given Submission object from the database. Helper is needed to centralize logic that fixes
    EDUCATOR-1090, because uuids are stored both with and without hyphens.
    """
    submission_qs = Submission.objects
    if read_replica:
        submission_qs = _use_read_replica(submission_qs)
    try:
        submission = submission_qs.get(uuid=uuid)
    except Submission.DoesNotExist:
        try:
            hyphenated_value = six.text_type(UUID(uuid))
            query = """
                SELECT
                    `submissions_submission`.`id`,
                    `submissions_submission`.`uuid`,
                    `submissions_submission`.`student_item_id`,
                    `submissions_submission`.`attempt_number`,
                    `submissions_submission`.`submitted_at`,
                    `submissions_submission`.`created_at`,
                    `submissions_submission`.`raw_answer`,
                    `submissions_submission`.`status`
                FROM
                    `submissions_submission`
                WHERE (
                    NOT (`submissions_submission`.`status` = 'D')
                    AND `submissions_submission`.`uuid` = '{}'
                )
            """
            query = query.replace("{}", hyphenated_value)

            # We can use Submission.objects instead of the SoftDeletedManager, we'll include that logic manually
            submission = Submission.objects.raw(query)[0]
        except IndexError:
            raise Submission.DoesNotExist()
        # Avoid the extra hit next time
        submission.save(update_fields=['uuid'])
    return submission


def get_submission(submission_uuid, read_replica=False):
    """Retrieves a single submission by uuid.

    Args:
        submission_uuid (str): Identifier for the submission.

    Kwargs:
        read_replica (bool): If true, attempt to use the read replica database.
            If no read replica is available, use the default database.

    Raises:
        SubmissionNotFoundError: Raised if the submission does not exist.
        SubmissionRequestError: Raised if the search parameter is not a string.
        SubmissionInternalError: Raised for unknown errors.

    Examples:
        >>> get_submission("20b78e0f32df805d21064fc912f40e9ae5ab260d")
        {
            'student_item': 2,
            'attempt_number': 1,
            'submitted_at': datetime.datetime(2014, 1, 29, 23, 14, 52, 649284, tzinfo=<UTC>),
            'created_at': datetime.datetime(2014, 1, 29, 17, 14, 52, 668850, tzinfo=<UTC>),
            'answer': u'The answer is 42.'
        }

    """
    if not isinstance(submission_uuid, six.string_types):
        if isinstance(submission_uuid, UUID):
            submission_uuid = six.text_type(submission_uuid)
        else:
            raise SubmissionRequestError(
                msg="submission_uuid ({!r}) must be serializable".format(submission_uuid)
            )

    cache_key = Submission.get_cache_key(submission_uuid)
    try:
        cached_submission_data = cache.get(cache_key)
    except Exception:  # pylint: disable=broad-except
        # The cache backend could raise an exception
        # (for example, memcache keys that contain spaces)
        logger.exception("Error occurred while retrieving submission from the cache")
        cached_submission_data = None

    if cached_submission_data:
        logger.info("Get submission {} (cached)".format(submission_uuid))
        return cached_submission_data

    try:
        submission = _get_submission_model(submission_uuid, read_replica)
        submission_data = SubmissionSerializer(submission).data
        cache.set(cache_key, submission_data)
    except Submission.DoesNotExist:
        logger.error("Submission {} not found.".format(submission_uuid))
        raise SubmissionNotFoundError(
            u"No submission matching uuid {}".format(submission_uuid)
        )
    except Exception as exc:
        # Something very unexpected has just happened (like DB misconfig)
        err_msg = "Could not get submission due to error: {}".format(exc)
        logger.exception(err_msg)
        raise SubmissionInternalError(err_msg)

    logger.info("Get submission {}".format(submission_uuid))
    return submission_data


def get_submission_and_student(uuid, read_replica=False):
    """
    Retrieve a submission by its unique identifier, including the associated student item.

    Args:
        uuid (str): the unique identifier of the submission.

    Kwargs:
        read_replica (bool): If true, attempt to use the read replica database.
            If no read replica is available, use the default database.

    Returns:
        Serialized Submission model (dict) containing a serialized StudentItem model

    Raises:
        SubmissionNotFoundError: Raised if the submission does not exist.
        SubmissionRequestError: Raised if the search parameter is not a string.
        SubmissionInternalError: Raised for unknown errors.

    """
    # This may raise API exceptions
    submission = get_submission(uuid, read_replica=read_replica)

    # Retrieve the student item from the cache
    cache_key = "submissions.student_item.{}".format(submission['student_item'])
    try:
        cached_student_item = cache.get(cache_key)
    except Exception:  # pylint: disable=broad-except
        # The cache backend could raise an exception
        # (for example, memcache keys that contain spaces)
        logger.exception("Error occurred while retrieving student item from the cache")
        cached_student_item = None

    if cached_student_item is not None:
        submission['student_item'] = cached_student_item
    else:
        # There is probably a more idiomatic way to do this using the Django REST framework
        try:
            student_item_qs = StudentItem.objects
            if read_replica:
                student_item_qs = _use_read_replica(student_item_qs)

            student_item = student_item_qs.get(id=submission['student_item'])
            submission['student_item'] = StudentItemSerializer(student_item).data
            cache.set(cache_key, submission['student_item'])
        except Exception as ex:
            err_msg = "Could not get submission due to error: {}".format(ex)
            logger.exception(err_msg)
            raise SubmissionInternalError(err_msg)

    return submission


def get_submissions(student_item_dict, limit=None):
    """Retrieves the submissions for the specified student item,
    ordered by most recent submitted date.

    Returns the submissions relative to the specified student item. Exception
    thrown if no submission is found relative to this location.

    Args:
        student_item_dict (dict): The location of the problem this submission is
            associated with, as defined by a course, student, and item.
        limit (int): Optional parameter for limiting the returned number of
            submissions associated with this student item. If not specified, all
            associated submissions are returned.

    Returns:
        List dict: A list of dicts for the associated student item. The submission
        contains five attributes: student_item, attempt_number, submitted_at,
        created_at, and answer. 'student_item' is the ID of the related student
        item for the submission. 'attempt_number' is the attempt this submission
        represents for this question. 'submitted_at' represents the time this
        submission was submitted, which can be configured, versus the
        'created_at' date, which is when the submission is first created.

    Raises:
        SubmissionRequestError: Raised when the associated student item fails
            validation.
        SubmissionNotFoundError: Raised when a submission cannot be found for
            the associated student item.

    Examples:
        >>> student_item_dict = dict(
        >>>    student_id="Tim",
        >>>    item_id="item_1",
        >>>    course_id="course_1",
        >>>    item_type="type_one"
        >>> )
        >>> get_submissions(student_item_dict, 3)
        [{
            'student_item': 2,
            'attempt_number': 1,
            'submitted_at': datetime.datetime(2014, 1, 29, 23, 14, 52, 649284, tzinfo=<UTC>),
            'created_at': datetime.datetime(2014, 1, 29, 17, 14, 52, 668850, tzinfo=<UTC>),
            'answer': u'The answer is 42.'
        }]

    """
    student_item_model = _get_or_create_student_item(student_item_dict)
    try:
        submission_models = Submission.objects.filter(
            student_item=student_item_model)
    except DatabaseError:
        error_message = (
            u"Error getting submission request for student item {}"
            .format(student_item_dict)
        )
        logger.exception(error_message)
        raise SubmissionNotFoundError(error_message)

    if limit:
        submission_models = submission_models[:limit]

    return SubmissionSerializer(submission_models, many=True).data


def get_all_submissions(course_id, item_id, item_type, read_replica=True):
    """For the given item, get the most recent submission for every student who has submitted.

    This may return a very large result set! It is implemented as a generator for efficiency.

    Args:
        course_id, item_id, item_type (string): The values of the respective student_item fields
            to filter the submissions by.
        read_replica (bool): If true, attempt to use the read replica database.
            If no read replica is available, use the default database.

    Yields:
        Dicts representing the submissions with the following fields:
            student_item
            student_id
            attempt_number
            submitted_at
            created_at
            answer

    Raises:
        Cannot fail unless there's a database error, but may return an empty iterable.
    """
    submission_qs = Submission.objects
    if read_replica:
        submission_qs = _use_read_replica(submission_qs)
    # We cannot use SELECT DISTINCT ON because it's PostgreSQL only, so unfortunately
    # our results will contain every entry of each student, not just the most recent.
    # We sort by student_id and primary key, so the reults will be grouped be grouped by
    # student, with the most recent submission being the first one in each group.
    query = submission_qs.select_related('student_item').filter(
        student_item__course_id=course_id,
        student_item__item_id=item_id,
        student_item__item_type=item_type,
    ).order_by('student_item__student_id', '-submitted_at', '-id').iterator()

    for unused_student_id, row_iter in itertools.groupby(query, operator.attrgetter('student_item.student_id')):
        submission = next(row_iter)  # pylint: disable= stop-iteration-return
        data = SubmissionSerializer(submission).data
        data['student_id'] = submission.student_item.student_id
        yield data


def get_all_course_submission_information(course_id, item_type, read_replica=True):
    """ For the given course, get all student items of the given item type, all the submissions for those itemes,
    and the latest scores for each item. If a submission was given a score that is not the latest score for the
    relevant student item, it will still be included but without score.

    Args:
        course_id (str): The course that we are getting submissions from.
        item_type (str): The type of items that we are getting submissions for.
        read_replica (bool): Try to use the database's read replica if it's available.

    Yields:
        A tuple of three dictionaries representing:
        (1) a student item with the following fields:
            student_id
            course_id
            student_item
            item_type
        (2) a submission with the following fields:
            student_item
            attempt_number
            submitted_at
            created_at
            answer
        (3) a score with the following fields, if one exists and it is the latest score:
            (if both conditions are not met, an empty dict is returned here)
            student_item
            submission
            points_earned
            points_possible
            created_at
            submission_uuid
    """

    submission_qs = Submission.objects
    if read_replica:
        submission_qs = _use_read_replica(submission_qs)

    query = submission_qs.select_related('student_item__scoresummary__latest__submission').filter(
        student_item__course_id=course_id,
        student_item__item_type=item_type,
    ).iterator()

    for submission in query:
        student_item = submission.student_item
        serialized_score = {}
        if hasattr(student_item, 'scoresummary'):
            latest_score = student_item.scoresummary.latest

            # Only include the score if it is not a reset score (is_hidden), and if the current submission is the same
            # as the student_item's latest score's submission. This matches the behavior of the API's get_score method.
            if (not latest_score.is_hidden()) and latest_score.submission.uuid == submission.uuid:
                serialized_score = ScoreSerializer(latest_score).data
        yield (
            StudentItemSerializer(student_item).data,
            SubmissionSerializer(submission).data,
            serialized_score
        )


def get_top_submissions(course_id, item_id, item_type, number_of_top_scores, use_cache=True, read_replica=True):
    """Get a number of top scores for an assessment based on a particular student item

    This function will return top scores for the piece of assessment.
    It will consider only the latest and greater than 0 score for a piece of assessment.
    A score is only calculated for a student item if it has completed the workflow for
    a particular assessment module.

    In general, users of top submissions can tolerate some latency
    in the search results, so by default this call uses
    a cache and the read replica (if available).

    Args:
        course_id (str): The course to retrieve for the top scores
        item_id (str): The item within the course to retrieve for the top scores
        item_type (str): The type of item to retrieve
        number_of_top_scores (int): The number of scores to return, greater than 0 and no
        more than 100.

    Kwargs:
        use_cache (bool): If true, check the cache before retrieving querying the database.
        read_replica (bool): If true, attempt to use the read replica database.
            If no read replica is available, use the default database.

    Returns:
        topscores (dict): The top scores for the assessment for the student item.
            An empty array if there are no scores or all scores are 0.

    Raises:
        SubmissionNotFoundError: Raised when a submission cannot be found for
            the associated student item.
        SubmissionRequestError: Raised when the number of top scores is higher than the
            MAX_TOP_SUBMISSIONS constant.

    Examples:
        >>> course_id = "TestCourse"
        >>> item_id = "u_67"
        >>> item_type = "openassessment"
        >>> number_of_top_scores = 10
        >>>
        >>> get_top_submissions(course_id, item_id, item_type, number_of_top_scores)
        [{
            'score': 20,
            'content': "Platypus"
        },{
            'score': 16,
            'content': "Frog"
        }]

    """
    if number_of_top_scores < 1 or number_of_top_scores > MAX_TOP_SUBMISSIONS:
        error_msg = (
            u"Number of top scores must be a number between 1 and {}.".format(MAX_TOP_SUBMISSIONS)
        )
        logger.exception(error_msg)
        raise SubmissionRequestError(msg=error_msg)

    # First check the cache (unless caching is disabled)
    cache_key = "submissions.top_submissions.{course}.{item}.{type}.{number}".format(
        course=course_id,
        item=item_id,
        type=item_type,
        number=number_of_top_scores
    )
    top_submissions = cache.get(cache_key) if use_cache else None

    # If we can't find it in the cache (or caching is disabled), check the database
    # By default, prefer the read-replica.
    if top_submissions is None:
        try:
            query = ScoreSummary.objects.filter(
                student_item__course_id=course_id,
                student_item__item_id=item_id,
                student_item__item_type=item_type,
                latest__points_earned__gt=0
            ).select_related('latest', 'latest__submission').order_by("-latest__points_earned")

            if read_replica:
                query = _use_read_replica(query)
            score_summaries = query[:number_of_top_scores]
        except DatabaseError:
            msg = u"Could not fetch top score summaries for course {}, item {} of type {}".format(
                course_id, item_id, item_type
            )
            logger.exception(msg)
            raise SubmissionInternalError(msg)

        # Retrieve the submission content for each top score
        top_submissions = [
            {
                "score": score_summary.latest.points_earned,
                "content": SubmissionSerializer(score_summary.latest.submission).data['answer']
            }
            for score_summary in score_summaries
        ]

        # Always store the retrieved list in the cache
        cache.set(cache_key, top_submissions, TOP_SUBMISSIONS_CACHE_TIMEOUT)

    return top_submissions


def get_score(student_item):
    """Get the score for a particular student item

    Each student item should have a unique score. This function will return the
    score if it is available. A score is only calculated for a student item if
    it has completed the workflow for a particular assessment module.

    Args:
        student_item (dict): The dictionary representation of a student item.
            Function returns the score related to this student item.

    Returns:
        score (dict): The score associated with this student item. None if there
            is no score found.

    Raises:
        SubmissionInternalError: Raised if a score cannot be retrieved because
            of an internal server error.

    Examples:
        >>> student_item = {
        >>>     "student_id":"Tim",
        >>>     "course_id":"TestCourse",
        >>>     "item_id":"u_67",
        >>>     "item_type":"openassessment"
        >>> }
        >>>
        >>> get_score(student_item)
        [{
            'student_item': 2,
            'submission': 2,
            'points_earned': 8,
            'points_possible': 20,
            'created_at': datetime.datetime(2014, 2, 7, 18, 30, 1, 807911, tzinfo=<UTC>)
        }]

    """
    try:
        student_item_model = StudentItem.objects.get(**student_item)
        score = ScoreSummary.objects.get(student_item=student_item_model).latest
    except (ScoreSummary.DoesNotExist, StudentItem.DoesNotExist):
        return None

    # By convention, scores are hidden if "points possible" is set to 0.
    # This can occur when an instructor has reset scores for a student.
    if score.is_hidden():
        return None
    else:
        return ScoreSerializer(score).data


def get_scores(course_id, student_id):
    """Return a dict mapping item_ids to scores.

    Scores are represented by serialized Score objects in JSON-like dict
    format.

    This method would be used by an LMS to find all the scores for a given
    student in a given course.

    Scores that are "hidden" (because they have points earned set to zero)
    are excluded from the results.

    Args:
        course_id (str): Course ID, used to do a lookup on the `StudentItem`.
        student_id (str): Student ID, used to do a lookup on the `StudentItem`.

    Returns:
        dict: The keys are `item_id`s (`str`) and the values are tuples of
        `(points_earned, points_possible)`. All points are integer values and
        represent the raw, unweighted scores. Submissions does not have any
        concept of weights. If there are no entries matching the `course_id` or
        `student_id`, we simply return an empty dictionary. This is not
        considered an error because there might be many queries for the progress
        page of a person who has never submitted anything.

    Raises:
        SubmissionInternalError: An unexpected error occurred while resetting scores.
    """
    try:
        score_summaries = ScoreSummary.objects.filter(
            student_item__course_id=course_id,
            student_item__student_id=student_id,
        ).select_related('latest', 'latest__submission', 'student_item')
    except DatabaseError:
        msg = u"Could not fetch scores for course {}, student {}".format(
            course_id, student_id
        )
        logger.exception(msg)
        raise SubmissionInternalError(msg)
    scores = {
        summary.student_item.item_id: UnannotatedScoreSerializer(summary.latest).data
        for summary in score_summaries if not summary.latest.is_hidden()
    }
    return scores


def get_latest_score_for_submission(submission_uuid, read_replica=False):
    """
    Retrieve the latest score for a particular submission.

    Args:
        submission_uuid (str): The UUID of the submission to retrieve.

    Kwargs:
        read_replica (bool): If true, attempt to use the read replica database.
            If no read replica is available, use the default database.

    Returns:
        dict: The serialized score model, or None if no score is available.

    """
    try:
        # Ensure that submission_uuid is valid before fetching score
        submission_model = _get_submission_model(submission_uuid, read_replica)
        score_qs = Score.objects.filter(
            submission__uuid=submission_model.uuid
        ).order_by("-id").select_related("submission")

        if read_replica:
            score_qs = _use_read_replica(score_qs)

        score = score_qs[0]
        if score.is_hidden():
            return None
    except (IndexError, Submission.DoesNotExist):
        return None

    return ScoreSerializer(score).data


def reset_score(student_id, course_id, item_id, clear_state=False, emit_signal=True):
    """
    Reset scores for a specific student on a specific problem.

    Note: this does *not* delete `Score` models from the database,
    since these are immutable.  It simply creates a new score with
    the "reset" flag set to True.

    Args:
        student_id (unicode): The ID of the student for whom to reset scores.
        course_id (unicode): The ID of the course containing the item to reset.
        item_id (unicode): The ID of the item for which to reset scores.
        clear_state (bool): If True, will appear to delete any submissions associated with the specified StudentItem

    Returns:
        None

    Raises:
        SubmissionInternalError: An unexpected error occurred while resetting scores.

    """
    # Retrieve the student item
    try:
        student_item = StudentItem.objects.get(
            student_id=student_id, course_id=course_id, item_id=item_id
        )
    except StudentItem.DoesNotExist:
        # If there is no student item, then there is no score to reset,
        # so we can return immediately.
        return

    # Create a "reset" score
    try:
        score = Score.create_reset_score(student_item)
        if emit_signal:
            # Send a signal out to any listeners who are waiting for scoring events.
            score_reset.send(
                sender=None,
                anonymous_user_id=student_id,
                course_id=course_id,
                item_id=item_id,
                created_at=score.created_at,
            )

        if clear_state:
            for sub in student_item.submission_set.all():
                # soft-delete the Submission
                sub.status = DELETED
                sub.save(update_fields=["status"])

                # Also clear out cached values
                cache_key = Submission.get_cache_key(sub.uuid)
                cache.delete(cache_key)

    except DatabaseError:
        msg = (
            u"Error occurred while reseting scores for"
            u" item {item_id} in course {course_id} for student {student_id}"
        ).format(item_id=item_id, course_id=course_id, student_id=student_id)
        logger.exception(msg)
        raise SubmissionInternalError(msg)
    else:
        msg = u"Score reset for item {item_id} in course {course_id} for student {student_id}".format(
            item_id=item_id, course_id=course_id, student_id=student_id
        )
        logger.info(msg)


def set_score(submission_uuid, points_earned, points_possible,
              annotation_creator=None, annotation_type=None, annotation_reason=None):
    """Set a score for a particular submission.

    Sets the score for a particular submission. This score is calculated
    externally to the API.

    Args:
        submission_uuid (str): UUID for the submission (must exist).
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

    Examples:
        >>> set_score("a778b933-9fb3-11e3-9c0f-040ccee02800", 11, 12)
        {
            'student_item': 2,
            'submission': 1,
            'points_earned': 11,
            'points_possible': 12,
            'created_at': datetime.datetime(2014, 2, 7, 20, 6, 42, 331156, tzinfo=<UTC>)
        }

    """
    try:
        submission_model = _get_submission_model(submission_uuid)
    except Submission.DoesNotExist:
        raise SubmissionNotFoundError(
            u"No submission matching uuid {}".format(submission_uuid)
        )
    except DatabaseError:
        error_msg = u"Could not retrieve submission {}.".format(
            submission_uuid
        )
        logger.exception(error_msg)
        raise SubmissionRequestError(msg=error_msg)

    score = ScoreSerializer(
        data={
            "student_item": submission_model.student_item.pk,
            "submission": submission_model.pk,
            "points_earned": points_earned,
            "points_possible": points_possible,
        }
    )
    if not score.is_valid():
        logger.exception(score.errors)
        raise SubmissionInternalError(score.errors)

    # When we save the score, a score summary will be created if
    # it does not already exist.
    # When the database's isolation level is set to repeatable-read,
    # it's possible for a score summary to exist for this student item,
    # even though we cannot retrieve it.
    # In this case, we assume that someone else has already created
    # a score summary and ignore the error.
    try:
        with transaction.atomic():
            score_model = score.save()
            _log_score(score_model)
            if annotation_creator is not None:
                score_annotation = ScoreAnnotation(
                    score=score_model,
                    creator=annotation_creator,
                    annotation_type=annotation_type,
                    reason=annotation_reason
                )
                score_annotation.save()
        # Send a signal out to any listeners who are waiting for scoring events.
        score_set.send(
            sender=None,
            points_possible=points_possible,
            points_earned=points_earned,
            anonymous_user_id=submission_model.student_item.student_id,
            course_id=submission_model.student_item.course_id,
            item_id=submission_model.student_item.item_id,
            created_at=score_model.created_at,
        )
    except IntegrityError:
        pass


def _log_submission(submission, student_item):
    """
    Log the creation of a submission.

    Args:
        submission (dict): The serialized submission model.
        student_item (dict): The serialized student item model.

    Returns:
        None
    """
    logger.info(
        u"Created submission uuid={submission_uuid} for "
        u"(course_id={course_id}, item_id={item_id}, "
        u"anonymous_student_id={anonymous_student_id})"
        .format(
            submission_uuid=submission["uuid"],
            course_id=student_item["course_id"],
            item_id=student_item["item_id"],
            anonymous_student_id=student_item["student_id"]
        )
    )


def _log_score(score):
    """
    Log the creation of a score.

    Args:
        score (Score): The score model.

    Returns:
        None
    """
    logger.info(
        "Score of ({}/{}) set for submission {}"
        .format(score.points_earned, score.points_possible, score.submission.uuid)
    )


def _get_or_create_student_item(student_item_dict):
    """Gets or creates a Student Item that matches the values specified.

    Attempts to get the specified Student Item. If it does not exist, the
    specified parameters are validated, and a new Student Item is created.

    Args:
        student_item_dict (dict): The dict containing the student_id, item_id,
            course_id, and item_type that uniquely defines a student item.

    Returns:
        StudentItem: The student item that was retrieved or created.

    Raises:
        SubmissionInternalError: Thrown if there was an internal error while
            attempting to create or retrieve the specified student item.
        SubmissionRequestError: Thrown if the given student item parameters fail
            validation.

    Examples:
        >>> student_item_dict = dict(
        >>>    student_id="Tim",
        >>>    item_id="item_1",
        >>>    course_id="course_1",
        >>>    item_type="type_one"
        >>> )
        >>> _get_or_create_student_item(student_item_dict)
        {'item_id': 'item_1', 'item_type': 'type_one', 'course_id': 'course_1', 'student_id': 'Tim'}

    """
    try:
        try:
            return StudentItem.objects.get(**student_item_dict)
        except StudentItem.DoesNotExist:
            student_item_serializer = StudentItemSerializer(
                data=student_item_dict
            )
            if not student_item_serializer.is_valid():
                logger.error(
                    u"Invalid StudentItemSerializer: errors:{} data:{}".format(
                        student_item_serializer.errors,
                        student_item_dict
                    )
                )
                raise SubmissionRequestError(field_errors=student_item_serializer.errors)
            return student_item_serializer.save()
    except DatabaseError:
        error_message = u"An error occurred creating student item: {}".format(
            student_item_dict
        )
        logger.exception(error_message)
        raise SubmissionInternalError(error_message)


def _use_read_replica(queryset):
    """
    Use the read replica if it's available.

    Args:
        queryset (QuerySet)

    Returns:
        QuerySet

    """
    return (
        queryset.using("read_replica")
        if "read_replica" in settings.DATABASES
        else queryset
    )
