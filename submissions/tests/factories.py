""" Test Factories. """
import datetime
from uuid import uuid4

import factory
from django.contrib import auth
from django.utils import timezone
from django.utils.timezone import now
from factory.django import DjangoModelFactory
from pytz import UTC

from submissions import models
from submissions.models import ExternalGraderDetail

User = auth.get_user_model()


class UserFactory(DjangoModelFactory):
    """ Copied from edx-platform/common/djangoapps/student/tests/factories.py """
    class Meta:
        model = User
        django_get_or_create = ('email', 'username')

    _DEFAULT_PASSWORD = 'test'

    username = factory.Sequence('robot{}'.format)
    email = factory.Sequence('robot+test+{}@edx.org'.format)
    password = factory.PostGenerationMethodCall('set_password', _DEFAULT_PASSWORD)
    first_name = factory.Sequence('Robot{}'.format)
    last_name = 'Test'
    is_staff = False
    is_active = True
    is_superuser = False
    last_login = datetime.datetime(2012, 1, 1, tzinfo=UTC)
    date_joined = datetime.datetime(2011, 1, 1, tzinfo=UTC)


class StudentItemFactory(DjangoModelFactory):
    """ A Factory for the StudentItem model. """
    class Meta:
        model = models.StudentItem

    student_id = factory.Faker('sha1')
    course_id = factory.Faker('sha1')
    item_id = factory.Faker('sha1')
    item_type = 'openassessment'


class SubmissionFactory(DjangoModelFactory):
    """ A factory for the Submission model. """
    class Meta:
        model = models.Submission

    uuid = factory.LazyFunction(uuid4)
    student_item = factory.SubFactory(StudentItemFactory)
    attempt_number = 1
    submitted_at = datetime.datetime.now()
    created_at = datetime.datetime.now()
    answer = {}

    status = models.ACTIVE


class TeamSubmissionFactory(DjangoModelFactory):
    """ A factory for TeamSubmission model """
    class Meta:
        model = models.TeamSubmission

    uuid = factory.LazyFunction(uuid4)
    attempt_number = 1
    submitted_at = now()
    course_id = factory.Faker('sha1')
    item_id = factory.Faker('sha1')
    team_id = factory.Faker('sha1')
    submitted_by = factory.SubFactory(UserFactory)


class ExternalGraderDetailFactory(DjangoModelFactory):
    """
    Factory for the ExternalGraderDetail model.
    """
    class Meta:
        model = ExternalGraderDetail

    submission = factory.SubFactory(SubmissionFactory)
    pullkey = factory.Sequence(lambda n: f'test_pull_key_{n}')
    status = 'pending'
    num_failures = 0
    grader_reply = ''
    status_time = factory.LazyFunction(timezone.now)
