"""
Settings for the submissions app.
"""

from __future__ import absolute_import

import warnings

from django.core.cache import CacheKeyWarning
from django.utils.crypto import get_random_string

DEBUG = True
TEMPLATE_DEBUG = DEBUG

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': 'submissions_db',
        'TEST': {
            'NAME': 'submissions_test_db',
        }
    },
    'read_replica': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': 'submissions_read_replica_db',
        'TEST': {
            'MIRROR': 'default',
        },
    },
}

CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'default_loc_mem',
    },
}

ROOT_URLCONF = 'urls'
SITE_ID = 1
USE_TZ = True

SECRET_KEY = get_random_string(50, 'abcdefghijklmnopqrstuvwxyz0123456789!@#$%^&*(-_=+)')

# Silence cache key warnings
# https://docs.djangoproject.com/en/1.4/topics/cache/#cache-key-warnings
warnings.simplefilter("ignore", CacheKeyWarning)

INSTALLED_APPS = (
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.sites',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.admin',
    'django.contrib.admindocs',

    # Test
    'django_nose',

    # Submissions
    'submissions'
)

MIDDLEWARE_CLASSES = (
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware'
)

TEST_APPS = ('submissions',)
TEST_RUNNER = 'django_nose.NoseTestSuiteRunner'

# Configure nose
NOSE_ARGS = [
    '--with-coverage',
    '--cover-package=' + ",".join(TEST_APPS),
    '--cover-branches',
    '--cover-erase',
]
