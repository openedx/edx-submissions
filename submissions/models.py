"""
Submission models hold student responses to problems, scores, and a history of
those scores. It is intended to be a general purpose store that is usable by
different problem types, and is therefore ignorant of ORA workflow.

NOTE: We've switched to migrations, so if you make any edits to this file, you
need to then generate a matching migration for it using:

    ./manage.py makemigrations submissions

"""
from __future__ import absolute_import, unicode_literals

import json
import logging
from uuid import uuid4

from django.contrib.auth.models import User
from django.db import DatabaseError, models
from django.db.models.signals import post_save, pre_save
from django.dispatch import Signal, receiver
from django.utils.encoding import python_2_unicode_compatible
from django.utils.timezone import now
from jsonfield import JSONField
from model_utils.models import TimeStampedModel

from submissions.errors import DuplicateTeamSubmissionsError, TeamSubmissionInternalError, TeamSubmissionNotFoundError

logger = logging.getLogger(__name__)


# Signal to inform listeners that a score has been changed
score_set = Signal(providing_args=[
    'points_possible', 'points_earned', 'anonymous_user_id',
    'course_id', 'item_id', 'created_at'
])

# Signal to inform listeners that a score has been reset
score_reset = Signal(
    providing_args=['anonymous_user_id', 'course_id', 'item_id', 'created_at']
)


class AnonymizedUserIDField(models.CharField):
    """ Field for storing anonymized user ids. """
    description = "The anonymized User ID that the XBlock sees"

    def __init__(self, *args, **kwargs):
        kwargs['max_length'] = 255
        kwargs['db_index'] = True
        super(AnonymizedUserIDField, self).__init__(*args, **kwargs)

    def deconstruct(self):
        name, path, args, kwargs = super(AnonymizedUserIDField, self).deconstruct()
        del kwargs["max_length"]
        del kwargs["db_index"]
        return name, path, args, kwargs


@python_2_unicode_compatible
class StudentItem(models.Model):
    """Represents a single item for a single course for a single user.

    This is typically an XBlock problem, but could be something more generic
    like class participation.

    """
    # The anonymized Student ID that the XBlock sees, not their real ID.
    student_id = AnonymizedUserIDField()

    # Not sure yet whether these are legacy course_ids or new course_ids
    course_id = models.CharField(max_length=255, blank=False, db_index=True)

    # Version independent, course-local content identifier, i.e. the problem
    # This is the block_id for XBlock items.
    item_id = models.CharField(max_length=255, blank=False, db_index=True)

    # What kind of problem is this? The XBlock tag if it's an XBlock
    item_type = models.CharField(max_length=100)

    def __repr__(self):
        return repr(self.student_item_dict)

    @property
    def student_item_dict(self):
        return dict(
            student_id=self.student_id,
            course_id=self.course_id,
            item_id=self.item_id,
            item_type=self.item_type,
        )

    def __str__(self):
        return u"({0.student_id}, {0.course_id}, {0.item_type}, {0.item_id})".format(self)

    class Meta:
        app_label = u"submissions"
        unique_together = (
            # For integrity reasons, and looking up all of a student's items
            ("course_id", "student_id", "item_id"),
        )


class UpdatedJSONField(JSONField):
    """
    Class inherits JSONFiled from jsonfiled2 and provides overridden implementation
    """
    # We need to this custom class to represent JSONField instead of standard JSONField
    # because we're using jsonfield2 version 3.0.3 and it has a known issue while performing
    # select_related queries, it has been fixed in version 3.1.0 but python3.5 support is also
    # dropped in that version, for now we've put the fix here
    def from_db_value(self, value, expression, connection):  # pylint: disable=arguments-differ
        if value is None:
            return None
        return json.loads(value, **self.load_kwargs)


# Has this submission been soft-deleted? This allows instructors to reset student
# state on an item, while preserving the previous value for potential analytics use.
DELETED = 'D'
ACTIVE = 'A'
STATUS_CHOICES = (
    (DELETED, 'Deleted'),
    (ACTIVE, 'Active'),
)


@python_2_unicode_compatible
class TeamSubmission(TimeStampedModel):
    """
    A single response by a team for a given problem (ORA2) in a given course.
    An abstraction layer over Submission used to for teams. Since we create a submission record for every team member,
    there is a need to have a single point to connect the team to the workflows.
    TeamSubmission is a 1 to many with Submission
    """

    uuid = models.UUIDField(db_index=True, default=uuid4, null=False)

    # Which attempt is this? Consecutive Submissions do not necessarily have
    # increasing attempt_number entries -- e.g. re-scoring a buggy problem.
    attempt_number = models.PositiveIntegerField()

    # submitted_at is separate from created_at to support re-scoring and other
    # processes that might create Submission objects for past user actions.
    submitted_at = models.DateTimeField(default=now, db_index=True)

    course_id = models.CharField(max_length=255, null=False, db_index=True)

    item_id = models.CharField(max_length=255, null=False, db_index=True)

    team_id = models.CharField(max_length=255, null=False, db_index=True)

    submitted_by = models.ForeignKey(User, null=True, on_delete=models.SET_NULL)

    status = models.CharField(max_length=1, choices=STATUS_CHOICES, default=ACTIVE)

    # Override the default Manager with our custom one to filter out soft-deleted items
    class SoftDeletedManager(models.Manager):
        def get_queryset(self):
            return super(TeamSubmission.SoftDeletedManager, self).get_queryset().exclude(status=DELETED)

    objects = SoftDeletedManager()
    _objects = models.Manager()  # Don't use this unless you know and can explain why objects doesn't work for you

    @staticmethod
    def get_cache_key(sub_uuid):
        return "submissions.team_submission.{}".format(sub_uuid)

    @staticmethod
    def get_team_submission_by_uuid(team_submission_uuid):
        """
        Given a uuid, return the matching team submission.

        Raises:
            - TeamSubmissionNotFoundError if there is no matching team submission
            - TeamSubmissionInternalError if there is some other error looking up the team submission.
        """
        try:
            return TeamSubmission.objects.prefetch_related('submissions').get(uuid=team_submission_uuid)
        except TeamSubmission.DoesNotExist:
            logger.error("Team Submission {} not found.".format(team_submission_uuid))
            raise TeamSubmissionNotFoundError(
                "No team submission matching uuid {}".format(team_submission_uuid)
            )
        except Exception as exc:
            err_msg = "Attempt to get team submission for uuid {uuid} caused error: {exc}".format(
                uuid=team_submission_uuid,
                exc=exc
            )
            logger.error(err_msg)
            raise TeamSubmissionInternalError(err_msg)

    @staticmethod
    def get_team_submission_by_course_item_team(course_id, item_id, team_id):
        """
        Given a course_id, item_id, and team_id, return team submission for the team assignment

        Raises:
            - TeamSubmissionNotFoundError if there is no matching team submission
            - TeamSubmissionInternalError if there is some other error looking up the team submission.

        """
        model_query_params = dict(course_id=course_id, item_id=item_id, team_id=team_id)
        query_params_string = "course_id={course_id} item_id={item_id} team_id={team_id}".format(**model_query_params)
        try:
            # In the equivalent non-teams api call, we're filtering on student item and then getting first(),
            # which will get us the most recent active submission due to the sort order of the model.
            # However, for this model, we have a uniqueness constraint (non-db, as a signal handler)
            # that means we can only ever have one submission per team per assignment. I don't fully understand
            # the logic behind the non-teams api, but this shouldn't have to do that filter.
            team_submission = TeamSubmission.objects.prefetch_related(
                'submissions'
            ).get(
                **model_query_params
            )
        except TeamSubmission.DoesNotExist:
            logger.error("Team submission for {} not found.".format(query_params_string))
            raise TeamSubmissionNotFoundError(
                "No team submission matching {}".format(query_params_string)
            )
        except Exception as exc:
            err_msg = "Attempt to get team submission for {params} caused error: {exc}".format(
                params=query_params_string,
                exc=exc
            )
            logger.error(err_msg)
            raise TeamSubmissionInternalError(err_msg)
        return team_submission

    @staticmethod
    def get_team_submission_by_student_item(student_item):
        """
        Return the team submission that has an individual submission tied to the given StudentItem

        Raises:
            - TeamSubmissionNotFoundError if there is no matching team submission
            - TeamSubmissionInternalError if there is some other error looking up the team submission.

        """
        try:
            return TeamSubmission.objects.prefetch_related('submissions').get(submissions__student_item=student_item)
        except TeamSubmission.DoesNotExist:
            logger.error("Team submission for {} not found.".format(student_item))
            raise TeamSubmissionNotFoundError(
                "No team submission matching {}".format(student_item)
            )
        except Exception as exc:
            err_msg = "Attempt to get team submission for {student_item} caused error: {exc}".format(
                student_item=student_item,
                exc=exc
            )
            logger.error(err_msg)
            raise TeamSubmissionInternalError(err_msg)

    @staticmethod
    def get_all_team_submissions_for_course_item(course_id, item_id):
        """
        Given a course_id and item_id, return all team submissions for the team assignment in the course

        Raises:
            - TeamSubmissionInternalError if there is some error looking up the team submissions.
        """
        try:
            return TeamSubmission.objects.prefetch_related('submissions').filter(
                course_id=course_id,
                item_id=item_id,
            ).all()
        except Exception as exc:
            query_params_string = "course_id={course_id} item_id={item_id}".format(
                course_id=course_id,
                item_id=item_id,
            )
            err_msg = "Attempt to get team submissions for {params} caused error: {exc}".format(
                params=query_params_string,
                exc=exc
            )
            logger.error(err_msg)
            raise TeamSubmissionInternalError(err_msg)

    def __repr__(self):
        return repr(dict(
            uuid=self.uuid,
            submitted_by=self.submitted_by,
            attempt_number=self.attempt_number,
            submitted_at=self.submitted_at,
            created=self.created,
            modified=self.modified,
        ))

    def __str__(self):
        return "Team Submission {}".format(self.uuid)

    class Meta:
        app_label = "submissions"
        ordering = ["-submitted_at", "-id"]


@receiver(pre_save, sender=TeamSubmission)
def validate_only_one_submission_per_team(sender, **kwargs):
    """
    Ensures that there is only one active submission per team.
    """
    ts = kwargs['instance']
    if TeamSubmission.objects.filter(
            course_id=ts.course_id,
            item_id=ts.item_id,
            team_id=ts.team_id,
            status='A'
    ).exclude(id=ts.id).exists():
        raise DuplicateTeamSubmissionsError('Can only have one submission per team.')


@python_2_unicode_compatible
class Submission(models.Model):
    """A single response by a student for a given problem in a given course.

    A student may have multiple submissions for the same problem. Submissions
    should never be mutated. If the student makes another Submission, or if we
    have to make corrective Submissions to fix bugs, those should be new
    objects. We want to keep Submissions immutable both for audit purposes, and
    because it makes caching trivial.

    """
    MAXSIZE = 1024*100  # 100KB

    uuid = models.UUIDField(db_index=True, default=uuid4)

    student_item = models.ForeignKey(StudentItem, on_delete=models.CASCADE)

    # Which attempt is this? Consecutive Submissions do not necessarily have
    # increasing attempt_number entries -- e.g. re-scoring a buggy problem.
    attempt_number = models.PositiveIntegerField()

    # submitted_at is separate from created_at to support re-scoring and other
    # processes that might create Submission objects for past user actions.
    submitted_at = models.DateTimeField(default=now, db_index=True)

    # When this row was created.
    created_at = models.DateTimeField(editable=False, default=now, db_index=True)

    # The answer (JSON-serialized)
    # NOTE: previously, this field was a TextField named `raw_answer`.
    # Since JSONField is a subclass of TextField, we can use it as a drop-in
    # replacement for TextField that performs JSON serialization/deserialization.
    # For backwards compatibility, we override the default database column
    # name so it continues to use `raw_answer`.
    answer = UpdatedJSONField(blank=True, db_column="raw_answer")

    status = models.CharField(max_length=1, choices=STATUS_CHOICES, default=ACTIVE)

    team_submission = models.ForeignKey(
        TeamSubmission,
        related_name='submissions',
        null=True,
        db_index=True,
        on_delete=models.SET_NULL
    )

    # Override the default Manager with our custom one to filter out soft-deleted items
    class SoftDeletedManager(models.Manager):
        def get_queryset(self):
            return super(Submission.SoftDeletedManager, self).get_queryset().exclude(status=DELETED)

    objects = SoftDeletedManager()
    _objects = models.Manager()  # Don't use this unless you know and can explain why objects doesn't work for you

    @staticmethod
    def get_cache_key(sub_uuid):
        return u"submissions.submission.{}".format(sub_uuid)

    def __repr__(self):
        return repr(dict(
            uuid=self.uuid,
            student_item=self.student_item,
            attempt_number=self.attempt_number,
            submitted_at=self.submitted_at,
            created_at=self.created_at,
            answer=self.answer,
        ))

    def __str__(self):
        return u"Submission {}".format(self.uuid)

    class Meta:
        app_label = u"submissions"
        ordering = ["-submitted_at", "-id"]


@python_2_unicode_compatible
class Score(models.Model):
    """What the user scored for a given StudentItem at a given time.

    Note that while a Score *can* be tied to a Submission, it doesn't *have* to.
    Specifically, if we want to have scores for things that are not a part of
    the courseware (like "class participation"), there would be no corresponding
    Submission.
    """
    student_item = models.ForeignKey(StudentItem, on_delete=models.CASCADE)
    submission = models.ForeignKey(Submission, null=True, on_delete=models.CASCADE)
    points_earned = models.PositiveIntegerField(default=0)
    points_possible = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(editable=False, default=now, db_index=True)

    # Flag to indicate that this score should reset the current "highest" score
    reset = models.BooleanField(default=False)

    class Meta:
        app_label = u"submissions"

    @property
    def submission_uuid(self):
        """
        Retrieve the submission UUID associated with this score.
        If the score isn't associated with a submission (for example, if this is
        a "reset" score or a a non-courseware item like "class participation"),
        then this will return None.

        Returns:
            str or None

        """
        if self.submission is not None:
            return str(self.submission.uuid)
        else:
            return None

    def to_float(self):
        """
        Calculate (points earned) / (points possible).
        If points possible is None (e.g. this is a "hidden" score)
        then return None.

        Returns:
            float or None

        """
        if self.points_possible == 0:
            return None
        return float(self.points_earned) / self.points_possible

    def __repr__(self):
        return repr(dict(
            student_item=self.student_item,
            submission=self.submission,
            created_at=self.created_at,
            points_earned=self.points_earned,
            points_possible=self.points_possible,
        ))

    def is_hidden(self):
        """
        By convention, a score of 0/0 is not displayed to users.
        Hidden scores are filtered by the submissions API.

        Returns:
            bool: Whether the score should be hidden.

        """
        return self.points_possible == 0

    @classmethod
    def create_reset_score(cls, student_item):
        """
        Create a "reset" score (a score with a null submission).

        Only scores created after the most recent "reset" score
        should be used to determine a student's effective score.

        Args:
            student_item (StudentItem): The student item model.

        Returns:
            Score: The newly created "reset" score.

        Raises:
            DatabaseError: An error occurred while creating the score

        """
        # By setting the "reset" flag, we ensure that the "highest"
        # score in the score summary will point to this score.
        # By setting points earned and points possible to 0,
        # we ensure that this score will be hidden from the user.
        return cls.objects.create(
            student_item=student_item,
            submission=None,
            points_earned=0,
            points_possible=0,
            reset=True,
        )

    def __str__(self):
        return u"{0.points_earned}/{0.points_possible}".format(self)


class ScoreSummary(models.Model):
    """Running store of the highest and most recent Scores for a StudentItem."""
    student_item = models.OneToOneField(StudentItem, on_delete=models.CASCADE)

    highest = models.ForeignKey(Score, related_name=u"+", on_delete=models.CASCADE)
    latest = models.ForeignKey(Score, related_name=u"+", on_delete=models.CASCADE)

    class Meta:
        app_label = u"submissions"
        verbose_name_plural = u"Score Summaries"

    @receiver(post_save, sender=Score)
    def update_score_summary(sender, **kwargs):  # pylint: disable=no-self-argument
        """
        Listen for new Scores and update the relevant ScoreSummary.

        Args:
            sender: not used

        Kwargs:
            instance (Score): The score model whose save triggered this receiver.

        """
        score = kwargs['instance']
        try:
            score_summary = ScoreSummary.objects.get(
                student_item=score.student_item
            )
            score_summary.latest = score

            # A score with the "reset" flag set will always replace the current highest score
            if score.reset:
                score_summary.highest = score
            # The conversion to a float may return None if points possible is zero
            elif score_summary.highest.to_float() is None and score.to_float() is not None:
                # Any score with non-null points possible will take precedence if the current
                # highest score is None
                score_summary.highest = score
            elif (
                score.to_float() is not None and
                score_summary.highest.to_float() is not None and
                score.to_float() > score_summary.highest.to_float()
            ):
                # If both scores are non-null we can do a normal comparison
                score_summary.highest = score
            score_summary.save()
        except ScoreSummary.DoesNotExist:
            ScoreSummary.objects.create(
                student_item=score.student_item,
                highest=score,
                latest=score,
            )
        except DatabaseError:
            logger.exception(
                u"Error while updating score summary for student item {}"
                .format(score.student_item)
            )


class ScoreAnnotation(models.Model):
    """ Annotate individual scores with extra information if necessary. """

    class Meta:
        app_label = u"submissions"

    score = models.ForeignKey(Score, on_delete=models.CASCADE)
    # A string that will represent the 'type' of annotation,
    # e.g. staff_override, etc.
    annotation_type = models.CharField(max_length=255, blank=False, db_index=True)

    creator = AnonymizedUserIDField()
    reason = models.TextField()
