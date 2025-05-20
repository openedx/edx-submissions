"""
Tests for admin.
"""
from unittest import mock

from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.backends.db import SessionStore
from django.test import RequestFactory, TestCase

from submissions.admin import ExternalGraderDetailAdmin
from submissions.models import ExternalGraderDetail, StudentItem, Submission

User = get_user_model()


class TestExternalGraderDetailAdmin(TestCase):
    """
    Test the ExternalGraderDetailAdmin functionality.
    """

    def setUp(self):
        """Set up common test data."""
        # Create test user
        self.user = User.objects.create_superuser(
            username='admin',
            email='admin@test.com',
            password='testpass'
        )

        self.regular_user = User.objects.create_user(
            username='regular',
            email='regular@test.com',
            password='testpass'
        )

        # Create test data
        self.student_item = StudentItem.objects.create(
            student_id="test_student_123",
            course_id="test_course_456",
            item_id="test_item_789"
        )

        self.submission = Submission.objects.create(
            student_item=self.student_item,
            answer="test answer content",
            attempt_number=1
        )

        self.external_grader_pending = ExternalGraderDetail.objects.create(
            submission=self.submission,
            queue_name="test_queue",
            status="pending"
        )

        # Create a second submission for testing bulk actions
        self.student_item2 = StudentItem.objects.create(
            student_id="test_student_456",
            course_id="test_course_789",
            item_id="test_item_123"
        )

        self.submission2 = Submission.objects.create(
            student_item=self.student_item2,
            answer="test answer 2",
            attempt_number=1
        )

        self.external_grader_failed = ExternalGraderDetail.objects.create(
            submission=self.submission2,
            queue_name="test_queue_2",
            status="failed",
            num_failures=3
        )

        # Setup admin
        self.site = AdminSite()
        self.admin = ExternalGraderDetailAdmin(ExternalGraderDetail, self.site)

        # Setup request factory
        self.factory = RequestFactory()

    def _get_request(self, user=None, add_session=True):
        """Helper method to create a request with session and messages."""
        request = self.factory.get('/')
        request.user = user or self.user

        if add_session:
            # Add session using a simple mock
            request.session = SessionStore()
            request.session.save()

            # Add messages
            messages = FallbackStorage(request)
            request._messages = messages  # pylint: disable=protected-access

        return request

    def test_submission_info_display(self):
        """Test that submission_info displays formatted student information."""
        result = self.admin.submission_info(self.external_grader_pending)

        # Check that all student info is present
        self.assertIn("test_student_123", result)
        self.assertIn("test_course_456", result)
        self.assertIn("test_item_789", result)
        self.assertIn("<strong>Student:</strong>", result)
        self.assertIn("<strong>Course:</strong>", result)
        self.assertIn("<strong>Item:</strong>", result)

    def test_status_badge_colors(self):
        """Test that status_badge returns correctly colored badges for different statuses."""
        # Test pending status (yellow)
        pending_badge = self.admin.status_badge(self.external_grader_pending)
        self.assertIn("#ffc107", pending_badge)  # Yellow color
        self.assertIn("Pending", pending_badge)

        # Test failed status (red)
        failed_badge = self.admin.status_badge(self.external_grader_failed)
        self.assertIn("#dc3545", failed_badge)  # Red color
        self.assertIn("Failed", failed_badge)

        # Test pulled status
        self.external_grader_pending.update_status('pulled')
        pulled_badge = self.admin.status_badge(self.external_grader_pending)
        self.assertIn("#17a2b8", pulled_badge)  # Blue color
        self.assertIn("Pulled", pulled_badge)

    def test_reset_failed_to_pending_success(self):
        """Test successful bulk action to reset failed submissions to pending."""
        request = self._get_request()

        # Create queryset with only failed submission
        queryset = ExternalGraderDetail.objects.filter(id=self.external_grader_failed.id)

        # Execute the action
        self.admin.reset_failed_to_pending(request, queryset)

        # Refresh from database
        self.external_grader_failed.refresh_from_db()

        # Check status changed to pending
        self.assertEqual(self.external_grader_failed.status, 'pending')

    def test_reset_failed_to_pending_no_failed_submissions(self):
        """Test bulk action when no failed submissions are selected."""
        request = self._get_request()

        # Create queryset with only pending submission
        queryset = ExternalGraderDetail.objects.filter(id=self.external_grader_pending.id)

        # Execute the action
        self.admin.reset_failed_to_pending(request, queryset)

        # Check that pending submission status didn't change
        self.external_grader_pending.refresh_from_db()
        self.assertEqual(self.external_grader_pending.status, 'pending')

    def test_reset_failed_to_pending_mixed_statuses(self):
        """Test bulk action with mixed status submissions."""
        request = self._get_request()

        # Create queryset with both pending and failed submissions
        queryset = ExternalGraderDetail.objects.filter(
            id__in=[self.external_grader_pending.id, self.external_grader_failed.id]
        )

        # Execute the action
        self.admin.reset_failed_to_pending(request, queryset)

        # Refresh from database
        self.external_grader_pending.refresh_from_db()
        self.external_grader_failed.refresh_from_db()

        # Check that only failed submission changed
        self.assertEqual(self.external_grader_pending.status, 'pending')  # Unchanged
        self.assertEqual(self.external_grader_failed.status, 'pending')  # Changed

    def test_get_search_results_submission_fields(self):
        """Test custom search functionality includes submission-related fields."""
        request = self._get_request()
        queryset = ExternalGraderDetail.objects.all()

        # Search for student_id
        result_queryset, use_distinct = self.admin.get_search_results(
            request, queryset, "test_student_123"
        )
        self.assertTrue(use_distinct)
        self.assertIn(self.external_grader_pending, result_queryset)

        # Search for course_id
        result_queryset, use_distinct = self.admin.get_search_results(
            request, queryset, "test_course_456"
        )
        self.assertTrue(use_distinct)
        self.assertIn(self.external_grader_pending, result_queryset)

        # Search for queue_name (regular search field)
        result_queryset, use_distinct = self.admin.get_search_results(
            request, queryset, "test_queue"
        )
        self.assertIn(self.external_grader_pending, result_queryset)

    def test_get_search_results_no_search_term(self):
        """Test search functionality when no search term is provided."""
        request = self._get_request()
        queryset = ExternalGraderDetail.objects.all()

        result_queryset, _ = self.admin.get_search_results(
            request, queryset, ""
        )

        # Should return original queryset
        self.assertEqual(list(result_queryset), list(queryset))

    def test_get_readonly_fields_existing_object(self):
        """Test that all fields are readonly when editing existing object."""
        request = self._get_request()

        # Test with existing object
        readonly_fields = self.admin.get_readonly_fields(request, self.external_grader_pending)

        # Should include all model fields
        model_field_names = [field.name for field in ExternalGraderDetail._meta.fields]
        self.assertEqual(set(readonly_fields), set(model_field_names))

    def test_get_readonly_fields_new_object(self):
        """Test readonly fields for new object creation."""
        request = self._get_request()

        # Test with no object (new object)
        readonly_fields = self.admin.get_readonly_fields(request, None)

        # Should only include default readonly fields
        expected_readonly = ['submission', 'pullkey', 'status_time', 'created_at']
        self.assertEqual(readonly_fields, expected_readonly)

    def test_has_change_permission(self):
        """Test change permissions for different users."""
        request = self._get_request(self.user)

        # Should allow change permission
        self.assertTrue(self.admin.has_change_permission(request))
        self.assertTrue(self.admin.has_change_permission(request, self.external_grader_pending))

    def test_has_delete_permission_superuser(self):
        """Test delete permissions for superuser."""
        request = self._get_request(self.user)  # superuser

        # Superuser should have delete permission
        self.assertTrue(self.admin.has_delete_permission(request))
        self.assertTrue(self.admin.has_delete_permission(request, self.external_grader_pending))

    def test_has_delete_permission_regular_user(self):
        """Test delete permissions for regular user."""
        request = self._get_request(self.regular_user)  # regular user

        # Regular user should not have delete permission
        self.assertFalse(self.admin.has_delete_permission(request))
        self.assertFalse(self.admin.has_delete_permission(request, self.external_grader_pending))

    def test_get_queryset_optimization(self):
        """Test that get_queryset uses select_related for optimization."""
        request = self._get_request()

        queryset = self.admin.get_queryset(request)

        # Check that the queryset is returned and has the expected objects
        self.assertTrue(queryset.exists())
        self.assertIn(self.external_grader_pending, queryset)
        self.assertIn(self.external_grader_failed, queryset)

        # Verify we can access related fields without additional errors
        for obj in queryset:
            # These should work without causing errors due to select_related
            student_id = obj.submission.student_item.student_id
            self.assertIsInstance(student_id, str)

    def test_admin_list_display_methods(self):
        """Test that list_display methods work correctly."""
        # Test that submission_info has correct short_description
        self.assertEqual(self.admin.submission_info.short_description, "Submission Info")

        # Test that status_badge has correct configuration
        self.assertEqual(self.admin.status_badge.short_description, "Status")
        self.assertEqual(self.admin.status_badge.admin_order_field, 'status')

    def test_admin_action_description(self):
        """Test that bulk action has correct description."""
        self.assertEqual(
            self.admin.reset_failed_to_pending.short_description,
            "Reset failed submissions to pending"
        )

    def test_fieldsets_structure(self):
        """Test that fieldsets are properly configured."""
        fieldsets = self.admin.fieldsets

        # Check fieldsets structure
        self.assertEqual(len(fieldsets), 4)

        # Check section names
        section_names = [fieldset[0] for fieldset in fieldsets]
        expected_sections = [
            'Submission Information',
            'Queue Details',
            'Status Information',
            'Timestamps'
        ]
        self.assertEqual(section_names, expected_sections)

        # Check that Timestamps section is collapsible
        timestamps_section = fieldsets[3]
        self.assertIn('collapse', timestamps_section[1]['classes'])

    def test_reset_failed_to_pending_with_update_error(self):
        """Test bulk action when update_status raises an exception."""
        request = self._get_request()

        # Create queryset with failed submission
        queryset = ExternalGraderDetail.objects.filter(id=self.external_grader_failed.id)

        # Mock update_status at the class level to raise an exception
        with mock.patch.object(ExternalGraderDetail, 'update_status') as mock_update:
            mock_update.side_effect = Exception("Database connection error")

            # Execute the action
            self.admin.reset_failed_to_pending(request, queryset)

            # Verify update_status was called
            mock_update.assert_called_once_with('pending')

        # Verify original status is unchanged (due to the exception)
        self.external_grader_failed.refresh_from_db()
        self.assertEqual(self.external_grader_failed.status, 'failed')

    def test_get_request_without_session(self):
        """Test _get_request helper method without session."""
        request = self._get_request(add_session=False)
        self.assertEqual(request.user, self.user)
        self.assertFalse(hasattr(request, 'session'))
