"""
hms_project/test_settings.py
============================
Settings used only for running the automated test suite.

The project normally talks to MySQL. A MySQL server is not always available
on a developer machine or in CI, so this module keeps every production
setting and swaps only the database for a temporary SQLite file. That lets
`manage.py test` run anywhere without touching real patient data.

Usage:
    python manage.py test --settings=hms_project.test_settings

Never use this module to serve the application.
"""

import os
import tempfile

# Must be set BEFORE importing settings: settings.py refuses to initialise with
# the public placeholder key, and the assignment below would happen too late.
# Not a secret, and never used outside the test suite.
os.environ.setdefault(
    "DJANGO_SECRET_KEY", "test-only-secret-key-not-used-outside-the-test-suite-0123456789"
)

from .settings import *  # noqa: E402,F401,F403

# `from .settings import *` also executes the tail of settings.py, which
# imports the developer's gitignored local_settings.py. That file is written
# for local development (DEBUG=True, localhost hosts) and would otherwise
# silently shape the test run, so the production value is restored here.
# Result: the suite exercises the same DEBUG state as the live site.
DEBUG = False

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

# Password hasher fast enough for a throwaway in-memory database.
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

# Emails go to the console, never to a real mailbox.
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

# Keep the production storage/media configuration out of the way.
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}

# MEDIA_ROOT must be a real path. Django 5's InMemoryStorage resolves
# MEDIA_ROOT on first access, so the None that used to be set here made any
# test touching a FileField fail with
# "TypeError: _path_normpath: path should be string, bytes or os.PathLike,
# not NoneType" before it reached a single assertion. A throwaway directory
# keeps those tests working and still writes nothing into the project.
MEDIA_ROOT = os.path.join(tempfile.gettempdir(), "cdms-test-media")
os.makedirs(MEDIA_ROOT, exist_ok=True)
