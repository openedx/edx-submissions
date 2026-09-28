"""Permission classes."""
from rest_framework import permissions


class IsXQueueUser(permissions.BasePermission):
    """
    Permission classes for submissions app.
    """

    def has_permission(self, request, view):
        return request.user.groups.filter(name='xqueue').exists()
