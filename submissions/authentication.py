"""Custom authentication classes for the submissions app."""

from rest_framework.authentication import SessionAuthentication


class CsrfExemptSessionAuthentication(SessionAuthentication):
    """
    Session authentication that skips CSRF enforcement.

    The XQueue API is a service-to-service interface used by xqueue-watcher.
    It is not a browser-facing endpoint, so CSRF protection is not applicable.
    Authorization is handled instead by the IsXQueueUser permission class, which
    requires the authenticated user to be a member of the 'xqueue' group.

    Security note: because this class disables CSRF while retaining cookie-based
    session auth, it is important that the 'xqueue' group is restricted strictly
    to dedicated service accounts and never granted to regular user accounts that
    may also authenticate via a browser.  Granting the 'xqueue' group to a
    browser-accessible account would reintroduce a CSRF attack surface against
    the state-changing endpoints (put_result, logout) of this API.
    """

    def enforce_csrf(self, request):
        return  # no-op: CSRF not required for service-to-service API calls
