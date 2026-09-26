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

from .settings import *  # noqa: F401,F403

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

MEDIA_ROOT = None
