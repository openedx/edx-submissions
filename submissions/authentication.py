"""Custom authentication classes for the submissions app."""

from rest_framework.authentication import SessionAuthentication


class CsrfExemptSessionAuthentication(SessionAuthentication):
    """
    Session authentication that skips CSRF enforcement.

    The XQueue API is a service-to-service interface used by xqueue-watcher.
    It is not a browser-facing endpoint, so CSRF protection is not applicable.
    Authorization is handled instead by the IsXQueueUser permission class, which
    requires the authenticated user to be a member of the 'xqueue' group.
    """

    def enforce_csrf(self, request):
        return  # no-op: CSRF not required for service-to-service API calls
