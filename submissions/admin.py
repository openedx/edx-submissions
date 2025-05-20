""" Submissions Admin Views. """

from django.contrib import admin, messages
from django.db.models import Q
from django.urls import reverse
from django.utils.html import format_html

from submissions.models import ExternalGraderDetail, Score, ScoreSummary, StudentItem, Submission, TeamSubmission


class StudentItemAdminMixin:
    """Mix this class into anything that has a student_item fkey."""
    search_fields = (
        'student_item__course_id',
        'student_item__student_id',
        'student_item__item_id',
        'student_item__id'
    )

    @admin.display(
        ordering='student_item__course_id'
    )
    def course_id(self, obj):
        return obj.student_item.course_id

    @admin.display(
        ordering='student_item__item_id'
    )
    def item_id(self, obj):
        return obj.student_item.item_id

    @admin.display(
        ordering='student_item__student_id'
    )
    def student_id(self, obj):
        return obj.student_item.student_id

    @admin.display(
        description='S.I. ID',
        ordering='student_item__id',
    )
    def student_item_id(self, obj):
        """ Formated student item id. """
        url = reverse(
            'admin:submissions_studentitem_change',
            args=[obj.student_item.id]
        )
        return format_html(f'<a href="{url}">{obj.student_item.id}</a>')


@admin.register(StudentItem)
class StudentItemAdmin(admin.ModelAdmin):
    list_display = ('id', 'course_id', 'item_type', 'item_id', 'student_id')
    list_filter = ('item_type',)
    search_fields = ('id', 'course_id', 'item_type', 'item_id', 'student_id')
    readonly_fields = ('course_id', 'item_type', 'item_id', 'student_id')


@admin.register(Submission)
class SubmissionAdmin(admin.ModelAdmin, StudentItemAdminMixin):
    """ Student Submission Admin View. """
    list_display = (
        'id', 'uuid',
        'course_id', 'item_id', 'student_id', 'student_item_id',
        'attempt_number', 'submitted_at',
    )
    list_display_links = ('id', 'uuid')
    list_filter = ('student_item__item_type',)
    readonly_fields = (
        'student_item_id',
        'course_id', 'item_id', 'student_id',
        'attempt_number', 'submitted_at', 'created_at',
        'answer', 'all_scores',
    )
    search_fields = ('id', 'uuid') + StudentItemAdminMixin.search_fields

    # We're creating our own explicit link and displaying parts of the
    # student_item in separate fields -- no need to display this as well.
    exclude = ('student_item',)

    def all_scores(self, submission):
        return "\n".join(
            f"{score.points_earned}/{score.points_possible} - {score.created_at}"
            for score in Score.objects.filter(submission=submission)
        )


class SubmissionInlineAdmin(admin.TabularInline, StudentItemAdminMixin):
    """ Inline admin for TeamSubmissions to view individual Submissions """
    model = Submission
    readonly_fields = ('uuid', 'student_id', 'status')
    exclude = ('student_item', 'attempt_number', 'submitted_at', 'answer')
    extra = 0


@admin.register(TeamSubmission)
class TeamSubmissionAdmin(admin.ModelAdmin):
    """ Student Submission Admin View. """

    list_display = ('id', 'uuid', 'course_id', 'item_id', 'team_id', 'status')
    search_fields = ('uuid', 'course_id', 'item_id', 'team_id')
    fields = ('uuid', 'attempt_number', 'submitted_at', 'course_id', 'item_id', 'team_id', 'submitted_by', 'status')
    inlines = (SubmissionInlineAdmin,)


@admin.register(Score)
class ScoreAdmin(admin.ModelAdmin, StudentItemAdminMixin):
    """ Student Score Admin View. """
    list_display = (
        'id',
        'course_id', 'item_id', 'student_id', 'student_item_id',
        'points', 'created_at'
    )
    list_filter = ('student_item__item_type',)
    readonly_fields = (
        'student_item_id',
        'student_item',
        'submission',
        'points_earned',
        'points_possible',
        'reset',
    )
    search_fields = ('id', ) + StudentItemAdminMixin.search_fields

    def points(self, score):
        return f"{score.points_earned}/{score.points_possible}"


@admin.register(ScoreSummary)
class ScoreSummaryAdmin(admin.ModelAdmin, StudentItemAdminMixin):
    """ Student Score Summary Admin View. """
    list_display = (
        'id',
        'course_id', 'item_id', 'student_id', 'student_item_id',
        'latest', 'highest',
    )
    search_fields = ('id', ) + StudentItemAdminMixin.search_fields
    readonly_fields = (
        'student_item_id', 'student_item', 'highest_link', 'latest_link'
    )
    exclude = ('highest', 'latest')

    @admin.display(
        description='Highest'
    )
    def highest_link(self, score_summary):
        """Returns highest link"""
        url = reverse(
            'admin:submissions_score_change', args=[score_summary.highest.id]
        )
        return format_html(f'<a href="{url}">{score_summary.highest}</a>')

    @admin.display(
        description='Latest'
    )
    def latest_link(self, score_summary):
        """Returns latest link"""
        url = reverse(
            'admin:submissions_score_change', args=[score_summary.latest.id]
        )
        return format_html(f'<a href="{url}">{score_summary.latest}</a>')


@admin.register(ExternalGraderDetail)
class ExternalGraderDetailAdmin(admin.ModelAdmin):
    """
    Admin interface for ExternalGraderDetail model with bulk status updates.
    """

    list_display = [
        'id',
        'submission_info',
        'queue_name',
        'status_badge',
        'num_failures',
        'status_time',
        'created_at',
    ]

    list_filter = [
        'status',
        'queue_name',
        'num_failures',
        'status_time',
        'created_at',
    ]

    search_fields = [
        'queue_name',
        'pullkey',
        'grader_file_name',
        'grader_reply',
    ]

    def get_readonly_fields(self, request, obj=None):
        """Make all fields readonly when viewing/editing individual objects."""
        if obj:  # Editing an existing object
            return [field.name for field in self.model._meta.fields]
        return self.readonly_fields

    readonly_fields = [
        'submission',
        'pullkey',
        'status_time',
        'created_at',
    ]

    ordering = ['-status_time']

    actions = ['reset_failed_to_pending']

    def submission_info(self, obj):
        """Display submission information in a readable format."""
        student_item = obj.submission.student_item
        return format_html(
            "<strong>Student:</strong> {}<br>"
            "<strong>Course:</strong> {}<br>"
            "<strong>Item:</strong> {}",
            student_item.student_id,
            student_item.course_id,
            student_item.item_id
        )

    submission_info.short_description = "Submission Info"

    def status_badge(self, obj):
        """Display status as a colored badge."""
        colors = {
            'pending': '#ffc107',  # Yellow
            'pulled': '#17a2b8',  # Blue
            'failed': '#dc3545',  # Red
            'retired': '#6c757d',  # Gray
        }
        color = colors.get(obj.status, '#6c757d')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 8px; '
            'border-radius: 3px; font-size: 12px; font-weight: bold;">{}</span>',
            color,
            obj.get_status_display()
        )

    status_badge.short_description = "Status"
    status_badge.admin_order_field = 'status'

    def reset_failed_to_pending(self, request, queryset):
        """
        Bulk action to reset failed submissions back to pending status.
        Only allows transition from 'failed' to 'pending'.
        """
        # Filter only failed submissions
        failed_submissions = queryset.filter(status='failed')

        if not failed_submissions.exists():
            self.message_user(
                request,
                "No failed submissions were selected. Only failed submissions can be reset to pending.",
                level=messages.WARNING
            )
            return

        # Check if any non-failed submissions were selected
        non_failed_count = queryset.exclude(status='failed').count()
        if non_failed_count > 0:
            self.message_user(
                request,
                f"Skipped {non_failed_count} submission(s) that were not in 'failed' status. "
                f"Only failed submissions can be reset to pending.",
                level=messages.WARNING
            )

        # Update failed submissions to pending
        updated_count = 0
        for submission in failed_submissions:
            # pylint: disable=broad-exception-caught
            try:
                submission.update_status('pending')
                updated_count += 1
            except Exception as e:
                self.message_user(
                    request,
                    f"Error updating submission {submission.id}: {str(e)}",
                    level=messages.ERROR
                )

        if updated_count > 0:
            self.message_user(
                request,
                f"Successfully reset {updated_count} failed submission(s) to pending status.",
                level=messages.SUCCESS
            )

    reset_failed_to_pending.short_description = "Reset failed submissions to pending"

    def get_search_results(self, request, queryset, search_term):
        """
        Custom search that includes submission-related fields.
        """
        if not search_term:
            return super().get_search_results(request, queryset, search_term)

        # Combine default search fields with submission-related fields
        search_q = (
            # Default search fields
            Q(queue_name__icontains=search_term) |
            Q(pullkey__icontains=search_term) |
            Q(grader_file_name__icontains=search_term) |
            Q(grader_reply__icontains=search_term) |
            # Submission-related fields
            Q(submission__student_item__student_id__icontains=search_term) |
            Q(submission__student_item__course_id__icontains=search_term) |
            Q(submission__student_item__item_id__icontains=search_term)
        )

        # Apply the combined search to the original queryset
        queryset = queryset.filter(search_q)
        use_distinct = True

        return queryset, use_distinct

    def get_queryset(self, request):
        """Optimize queryset with select_related to reduce database queries."""
        return super().get_queryset(request).select_related(
            'submission__student_item'
        )

    def has_change_permission(self, request, obj=None):
        """Allow viewing and bulk actions but restrict individual editing."""
        return True

    def has_delete_permission(self, request, obj=None):
        """Restrict deletion permissions."""
        return request.user.is_superuser

    fieldsets = (
        ('Submission Information', {
            'fields': ('submission',)
        }),
        ('Queue Details', {
            'fields': ('queue_name', 'grader_file_name', 'points_possible')
        }),
        ('Status Information', {
            'fields': ('status', 'num_failures', 'pullkey', 'grader_reply')
        }),
        ('Timestamps', {
            'fields': ('status_time', 'created_at'),
            'classes': ('collapse',)
        }),
    )
