"""
Serializers are created to ensure models do not have to be accessed outside the
scope of the submissions API.
"""
import json

from rest_framework import serializers
from rest_framework.fields import Field, DateTimeField, IntegerField
from submissions.models import StudentItem, Submission, Score


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
    def to_representation(self, obj):
        return obj

    def to_internal_value(self, data):
        return data


class StudentItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = StudentItem
        fields = ('student_id', 'course_id', 'item_id', 'item_type')


class SubmissionSerializer(serializers.ModelSerializer):

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
        )


class ScoreSerializer(serializers.ModelSerializer):

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
