"""
Serializers are created to ensure models do not have to be accessed outside the
scope of the submissions API.
"""
from __future__ import absolute_import

import json

from rest_framework import serializers
from rest_framework.fields import DateTimeField, Field, IntegerField

from submissions.models import Score, ScoreAnnotation, StudentItem, Submission, TeamSubmission


class RawField(Field):
    """
    Serializer field that does NOT modify its value.

    This is useful when the Django model field is handling serialization/deserialization.
    For example, `JsonField` already converts its value to JSON internally.  If we use
    the default DRF text field, the value would be converted to a string, which would then
    be encoded as JSON:

    1) field value is {"foo": "bar"} (a dict)
    2) DRF's default field implementation converts the dict to a string: "{'foo': 'bar'}"
    3) JsonField encodes the string as JSON: '"{\'foo\': \'bar\'}"'

    This is a problem, because when we load the data back from the database, we'll end
    up with a string instead of a dictionary!

    """
    def to_representation(self, obj):  # pylint: disable=arguments-differ
        return obj

    def to_internal_value(self, data):
        return data


class StudentItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = StudentItem
        fields = ('student_id', 'course_id', 'item_id', 'item_type')


class TeamSubmissionSerializer(serializers.ModelSerializer):
    """ Serializer for TeamSubmissions """

    team_submission_uuid = serializers.UUIDField(source='uuid', read_only=True)
    submission_uuids = serializers.SlugRelatedField(
        source='submissions',
        many=True,
        read_only=True,
        slug_field='uuid'
    )

    # See comments on SubmissionSerializer below
    submitted_at = DateTimeField(format=None, required=False)
    created_at = DateTimeField(source='created', format=None, required=False)
    attempt_number = IntegerField(min_value=0)
    # Prevent Django Rest Framework from converting the answer (dict or str)
    # to a string.
    # answer is not a part of TeamSubmission model. We populate it externally.
    answer = serializers.SerializerMethodField()

    def get_answer(self, obj):
        """
        Regular submissions are created after a team submission. In this case, the answer is passed as part of context
        otherwise, get the answer from its related submission. All individual submissions are identical except for
        student data. Therefore, get the answer of the first submitter
        """
        answer = self.context.get("answer")
        if answer is None and obj.submissions is not None:
            #  retrieve answer submissions from the linked submission model. There are n identical submissions
            answer = obj.submissions.first().answer
        return answer

    def validate_answer(self, value):
        """
        Check that the answer is JSON-serializable and not too long.
        """
        # Check that the answer is JSON-serializable
        try:
            serialized = json.dumps(value)
        except (ValueError, TypeError):
            raise serializers.ValidationError("Answer value must be JSON-serializable")

        # Check the length of the serialized representation
        if len(serialized) > Submission.MAXSIZE:
            raise serializers.ValidationError("Maximum answer size exceeded.")

        return value

    class Meta:
        model = TeamSubmission
        fields = (
            'team_submission_uuid',
            'attempt_number',
            'submitted_at',
            'course_id',
            'item_id',
            'team_id',
            'submitted_by',
            'created_at',
            'answer',
            'submission_uuids'
        )


class SubmissionSerializer(serializers.ModelSerializer):
    """ Submission Serializer. """

    # Django Rest Framework v3 uses the Django setting `DATETIME_FORMAT`
    # when serializing datetimes.  This differs from v2, which always
    # returned a datetime.  To preserve the old behavior, we explicitly
    # set `format` to None.
    # http://www.django-rest-framework.org/api-guide/fields/#datetimefield
    submitted_at = DateTimeField(format=None, required=False)
    created_at = DateTimeField(format=None, required=False)

    # Django Rest Framework v3 apparently no longer validates that
    # `PositiveIntegerField`s are positive!
    attempt_number = IntegerField(min_value=0)

    # Prevent Django Rest Framework from converting the answer (dict or str)
    # to a string.
    answer = RawField()

    team_submission_uuid = serializers.SlugRelatedField(
        slug_field='uuid',
        source='team_submission',
        queryset=TeamSubmission.objects.all(),
        allow_null=True,
        required=False,
    )

    def validate_answer(self, value):
        """
        Check that the answer is JSON-serializable and not too long.
        """
        # Check that the answer is JSON-serializable
        try:
            serialized = json.dumps(value)
        except (ValueError, TypeError):
            raise serializers.ValidationError("Answer value must be JSON-serializable")

        # Check the length of the serialized representation
        if len(serialized) > Submission.MAXSIZE:
            raise serializers.ValidationError("Maximum answer size exceeded.")

        return value

    class Meta:
        model = Submission
        fields = (
            'uuid',
            'student_item',
            'attempt_number',
            'submitted_at',
            'created_at',
            'answer',
            'team_submission_uuid'
        )


class ScoreAnnotationSerializer(serializers.ModelSerializer):

    class Meta:
        model = ScoreAnnotation
        fields = (
            'creator',
            'reason',
            'annotation_type',
        )


class UnannotatedScoreSerializer(serializers.ModelSerializer):
    """ Submissions unannotated score serializer. """

    # Ensure that the created_at datetime is not converted to a string.
    created_at = DateTimeField(format=None, required=False)

    class Meta:
        model = Score
        fields = (
            'student_item',
            'submission',
            'points_earned',
            'points_possible',
            'created_at',

            # Computed
            'submission_uuid',
        )


class ScoreSerializer(serializers.ModelSerializer):
    """ Submissions score serializer class. """
    # Ensure that the created_at datetime is not converted to a string.
    created_at = DateTimeField(format=None, required=False)
    annotations = serializers.SerializerMethodField()

    def get_annotations(self, obj):
        """
        Inspect ScoreAnnotations to attach all relevant annotations.
        """
        annotations = ScoreAnnotation.objects.filter(score_id=obj.id)
        return [
            ScoreAnnotationSerializer(instance=annotation).data
            for annotation in annotations
        ]

    class Meta:
        model = Score
        fields = (
            'student_item',
            'submission',
            'points_earned',
            'points_possible',
            'created_at',

            # Computed
            'submission_uuid',
            'annotations',
        )
