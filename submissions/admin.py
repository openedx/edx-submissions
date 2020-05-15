""" Submissions Admin Views. """
from __future__ import absolute_import

from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html

from submissions.models import Score, ScoreSummary, StudentItem, Submission, TeamSubmission


class StudentItemAdminMixin(object):  # pylint: disable=useless-object-inheritance
    """Mix this class into anything that has a student_item fkey."""
    search_fields = (
        'student_item__course_id',
        'student_item__student_id',
        'student_item__item_id',
        'student_item__id'
    )

    def course_id(self, obj):
        return obj.student_item.course_id
    course_id.admin_order_field = 'student_item__course_id'

    def item_id(self, obj):
        return obj.student_item.item_id
    item_id.admin_order_field = 'student_item__item_id'

    def student_id(self, obj):
        return obj.student_item.student_id
    student_id.admin_order_field = 'student_item__student_id'

    def student_item_id(self, obj):
        """ Formated student item id. """
        url = reverse(
            'admin:submissions_studentitem_change',
            args=[obj.student_item.id]
        )
        return format_html(u'<a href="{}">{}</a>'.format(url, obj.student_item.id))

    student_item_id.admin_order_field = 'student_item__id'
    student_item_id.short_description = 'S.I. ID'


class StudentItemAdmin(admin.ModelAdmin):
    list_display = ('id', 'course_id', 'item_type', 'item_id', 'student_id')
    list_filter = ('item_type',)
    search_fields = ('id', 'course_id', 'item_type', 'item_id', 'student_id')
    readonly_fields = ('course_id', 'item_type', 'item_id', 'student_id')


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
            "{}/{} - {}".format(
                score.points_earned, score.points_possible, score.created_at
            )
            for score in Score.objects.filter(submission=submission)
        )


class SubmissionInlineAdmin(admin.TabularInline, StudentItemAdminMixin):
    """ Inline admin for TeamSubmissions to view individual Submissions """
    model = Submission
    readonly_fields = ('uuid', 'student_id', 'status')
    exclude = ('student_item', 'attempt_number', 'submitted_at', 'answer')
    extra = 0


class TeamSubmissionAdmin(admin.ModelAdmin):
    """ Student Submission Admin View. """

    list_display = ('id', 'uuid', 'course_id', 'item_id', 'team_id', 'status')
    search_fields = ('uuid', 'course_id', 'item_id', 'team_id')
    fields = ('uuid', 'attempt_number', 'submitted_at', 'course_id', 'item_id', 'team_id', 'submitted_by', 'status')
    inlines = (SubmissionInlineAdmin,)


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
        return u"{}/{}".format(score.points_earned, score.points_possible)


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

    def highest_link(self, score_summary):
        url = reverse(
            'admin:submissions_score_change', args=[score_summary.highest.id]
        )
        return format_html(u'<a href="{}">{}</a>'.format(url, score_summary.highest))

    highest_link.short_description = 'Highest'

    def latest_link(self, score_summary):
        url = reverse(
            'admin:submissions_score_change', args=[score_summary.latest.id]
        )
        return format_html(u'<a href="{}">{}</a>'.format(url, score_summary.latest))

    latest_link.short_description = 'Latest'


admin.site.register(Score, ScoreAdmin)
admin.site.register(StudentItem, StudentItemAdmin)
admin.site.register(Submission, SubmissionAdmin)
admin.site.register(TeamSubmission, TeamSubmissionAdmin)
admin.site.register(ScoreSummary, ScoreSummaryAdmin)
