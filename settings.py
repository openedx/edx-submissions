"""
Settings for the submissions app.
"""

DEBUG = True
TEMPLATE_DEBUG = DEBUG

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'TEST_NAME': 'submissions_test_db',
    },

    'read_replica': {
        'ENGINE': 'django.db.backends.sqlite3',
        'TEST_MIRROR': 'default'
    }
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

# Silence cache key warnings
# https://docs.djangoproject.com/en/1.4/topics/cache/#cache-key-warnings
import warnings
from django.core.cache import CacheKeyWarning
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

    # Third party
    'django_extensions',

    # Test
    'django_nose',

    # Submissions
    'submissions'
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

SECRET_KEY = "1234"