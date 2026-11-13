"""
Settings for running this app's migrations against MySQL.

The migrations check in .github/workflows/migrations-check.yml uses these
instead of the SQLite databases in settings.py. The connection details are the
same as openedx-platform's default DATABASES (openedx/envs/common.py), which
openedx-platform's own migrations check runs against, so both repos check their
migrations against the same kind of database.
"""

from settings import *  # pylint: disable=wildcard-import,unused-wildcard-import

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.mysql",
        "HOST": "127.0.0.1",
        "PORT": "3306",
        "NAME": "edxapp",
        "USER": "edxapp001",
        "PASSWORD": "password",
    },
}
# Like openedx-platform, point the read replica at the same database. Migrations
# only run against "default".
DATABASES["read_replica"] = dict(DATABASES["default"])
