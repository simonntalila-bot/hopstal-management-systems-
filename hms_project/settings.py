"""
Django settings for Hospital Management System (HMS)
====================================================
Configured for:
- MySQL Workbench (local development)
- Multi-hospital isolated instances
- Tanzania timezone
- Role-based authentication

Local overrides: create hms_project/local_settings.py (gitignored).
Production: set env vars on the server (no .env file required).
"""

from pathlib import Path
from django.contrib.messages import constants as message_constants
import os

# ---------------------------------------------------------------------------
# BASE DIRECTORY
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent


def env_flag(name, default="0"):
    """Read a boolean-ish environment variable."""
    return os.environ.get(name, default).strip().lower() in ("1", "true", "yes", "on")


# ---------------------------------------------------------------------------
# SECURITY SETTINGS
# ---------------------------------------------------------------------------
# Generate production key:
# python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY",
    "django-insecure-change-me-in-production-hms-2026-tanzania",
)

# DEBUG is True ONLY when you explicitly enable it (local_settings or DJANGO_DEBUG=1)
# Default = False (safe for production)
DEBUG = os.environ.get("DJANGO_DEBUG", "0").lower() in ("1", "true", "yes")

ALLOWED_HOSTS = [
    h.strip()
    for h in os.environ.get(
        "DJANGO_ALLOWED_HOSTS",
        "localhost,127.0.0.1",
    ).split(",")
    if h.strip()
]


# ---------------------------------------------------------------------------
# APPLICATION DEFINITION
# ---------------------------------------------------------------------------
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",

    "core",
    "accounts",
    "patients",
    "encounters",
    "appointments",
    "queue_management",
    "consultations",
    "pharmacy",
    "laboratory",
    "billing",
    "bed_management",
    "dashboard",
    "ultrasound",
    "injection",
    "rch",
    "labour",
]


# ---------------------------------------------------------------------------
# MIDDLEWARE
# ---------------------------------------------------------------------------
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    # Serves collected static files when no web server does (temporary
    # hosting, and the VPS before nginx is in front). Safe to keep when
    # nginx is added - WhiteNoise steps aside for files it does not own.
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]


# ---------------------------------------------------------------------------
# URL & TEMPLATE CONFIGURATION
# ---------------------------------------------------------------------------
ROOT_URLCONF = "hms_project.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "hms_project.wsgi.application"


# ---------------------------------------------------------------------------
# DATABASE - MySQL (override password in local_settings.py)
# ---------------------------------------------------------------------------
import pymysql
pymysql.install_as_MySQLdb()

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.mysql",
        "NAME": os.environ.get("DB_NAME", "hms_db"),
        "USER": os.environ.get("DB_USER", "hms_user"),
        "PASSWORD": os.environ.get("DB_PASSWORD", ""),
        "HOST": os.environ.get("DB_HOST", "127.0.0.1"),
        "PORT": os.environ.get("DB_PORT", "3306"),
        "OPTIONS": {
            "charset": "utf8mb4",
            "init_command": "SET sql_mode='STRICT_TRANS_TABLES'",
        },
    }
}


# ---------------------------------------------------------------------------
# EMAIL
# Required in production for password reset links. When DJANGO_EMAIL_BACKEND is
# unset the console backend is used, so nothing is sent to a real mailbox.
# ---------------------------------------------------------------------------
_default_from = os.environ.get(
    "DJANGO_DEFAULT_FROM_EMAIL", "Argentina Dispensary <no-reply@example.com>"
)

EMAIL_BACKEND = os.environ.get(
    "DJANGO_EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend"
)
EMAIL_HOST = os.environ.get("DJANGO_EMAIL_HOST", "")
EMAIL_PORT = int(os.environ.get("DJANGO_EMAIL_PORT", "587"))
EMAIL_HOST_USER = os.environ.get("DJANGO_EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.environ.get("DJANGO_EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = env_flag("DJANGO_EMAIL_USE_TLS", "1")
EMAIL_USE_SSL = env_flag("DJANGO_EMAIL_USE_SSL", "0")
EMAIL_TIMEOUT = int(os.environ.get("DJANGO_EMAIL_TIMEOUT", "10"))
DEFAULT_FROM_EMAIL = _default_from
SERVER_EMAIL = _default_from


# ---------------------------------------------------------------------------
# HTTPS / PROXY
# SECURE_SSL_REDIRECT stays off by default so plain-HTTP container boot and local
# runs are not broken. Turn it on once the domain has a certificate.
# ---------------------------------------------------------------------------
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = env_flag("DJANGO_SECURE_SSL_REDIRECT", "0")
SESSION_COOKIE_SECURE = env_flag("DJANGO_SESSION_COOKIE_SECURE", "0")
CSRF_COOKIE_SECURE = env_flag("DJANGO_CSRF_COOKIE_SECURE", "0")
SECURE_HSTS_SECONDS = int(os.environ.get("DJANGO_SECURE_HSTS_SECONDS", "0"))
SECURE_HSTS_INCLUDE_SUBDOMAINS = env_flag("DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS", "0")
SECURE_HSTS_PRELOAD = env_flag("DJANGO_SECURE_HSTS_PRELOAD", "0")
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
SECURE_REFERRER_POLICY = "same-origin"


# ---------------------------------------------------------------------------
# CUSTOM USER MODEL
# ---------------------------------------------------------------------------
AUTH_USER_MODEL = "accounts.User"

MESSAGE_TAGS = {
    message_constants.DEBUG: "secondary",
    message_constants.INFO: "info",
    message_constants.SUCCESS: "success",
    message_constants.WARNING: "warning",
    message_constants.ERROR: "danger",
}


# ---------------------------------------------------------------------------
# AUTHENTICATION & LOGIN REDIRECTS
# ---------------------------------------------------------------------------
LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "dashboard:home"
LOGOUT_REDIRECT_URL = "login"


# ---------------------------------------------------------------------------
# PASSWORD VALIDATION
# ---------------------------------------------------------------------------
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]


# ---------------------------------------------------------------------------
# SESSION SETTINGS (shared hospital workstations)
# ---------------------------------------------------------------------------
SESSION_COOKIE_AGE = 60 * 60 * 1
SESSION_SAVE_EVERY_REQUEST = True
SESSION_EXPIRE_AT_BROWSER_CLOSE = True


# ---------------------------------------------------------------------------
# INTERNATIONALIZATION
# ---------------------------------------------------------------------------
LANGUAGE_CODE = "en-us"
TIME_ZONE = "Africa/Dar_es_Salaam"
USE_I18N = True
USE_TZ = True


# ---------------------------------------------------------------------------
# STATIC & MEDIA
# ---------------------------------------------------------------------------
STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"  # collectstatic on server

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# WhiteNoise serves STATIC_ROOT in production. CompressedStaticFilesStorage is
# used instead of the manifest variant so a missing asset degrades to a normal
# 404 rather than a template exception.
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedStaticFilesStorage",
    },
}


# ---------------------------------------------------------------------------
# DEFAULT PRIMARY KEY
# ---------------------------------------------------------------------------
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# ---------------------------------------------------------------------------
# LOGGING
# ---------------------------------------------------------------------------
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "[{asctime}] {levelname} {name} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "INFO",
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        "hms": {
            "handlers": ["console"],
            "level": "DEBUG",
            "propagate": False,
        },
    },
}


# ---------------------------------------------------------------------------
# LOCAL OVERRIDES (not in Git) — put DEBUG=True and DB password here
# ---------------------------------------------------------------------------
try:
    from .local_settings import *  # noqa: F401, F403
except ImportError:
    pass