"""
Django settings for Hospital Management System (HMS)
====================================================
Configured for:
- MySQL Workbench (local development)
- Multi-hospital isolated instances
- Tanzania timezone
- Role-based authentication
"""

from pathlib import Path
from django.contrib.messages import constants as message_constants
import os

# ---------------------------------------------------------------------------
# BASE DIRECTORY
# ---------------------------------------------------------------------------
# Absolute path to the project root (where manage.py lives)
BASE_DIR = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# SECURITY SETTINGS
# ---------------------------------------------------------------------------
# WARNING: Change this secret key in production!
# Generate a new one with: python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY",
    "django-insecure-change-me-in-production-hms-2026-tanzania"
)

# DEBUG = True only during development. Set to False in production.
DEBUG = os.environ.get("DJANGO_DEBUG", "True").lower() in ("1", "true", "yes")

# Allowed hosts - add your domain when deploying
ALLOWED_HOSTS = os.environ.get(
    "DJANGO_ALLOWED_HOSTS",
    "localhost,127.0.0.1"
).split(",")


# ---------------------------------------------------------------------------
# APPLICATION DEFINITION
# ---------------------------------------------------------------------------
INSTALLED_APPS = [
    # Django built-in apps
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",

    # Local HMS apps (order matters for model dependencies)
    "core",                 # BaseModel + AuditLog
    "accounts",             # Custom User + StaffProfile (roles)
    "patients",             # Patient registration + EMR + QR codes
    "encounters",           # Encounter (visit) + status machine + Vitals
    "appointments",         # Appointment booking
    "queue_management",     # Live queues (derived from Encounter status)
    "consultations",        # Doctor consultation + e-Prescription
    "pharmacy",             # Drug catalog, batches, FIFO dispensing
    "laboratory",           # Lab tests, orders, results
    "billing",              # Payments, Insurance Claims, Invoices
    "bed_management",       # Wards, Beds, Admissions
    "dashboard",            # Role-based home after login
    "ultrasound",          # Ultrasound department
    "injection",            # Injection room
    "rch",                  # Reproductive and Child Health (RCH)
    "labour",               # Labour ward
]



# ---------------------------------------------------------------------------
# MIDDLEWARE
# ---------------------------------------------------------------------------
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
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
        # Project-level templates folder (for login page, base templates, etc.)
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,  # Also look inside each app's templates/ folder
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
# DATABASE - MySQL Workbench Configuration
# ---------------------------------------------------------------------------
# We use PyMySQL as a pure-Python MySQL client (no need to compile mysqlclient)
import pymysql
pymysql.install_as_MySQLdb()

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.mysql",
        "NAME": "hms_db",                    # Database name created in Workbench
        "USER": "hms_user",                  # MySQL user you created
        "PASSWORD": "REMOVED-ROTATE-THIS-PASSWORD",  # ← CHANGE THIS to your real password
        "HOST": "127.0.0.1",                 # Localhost
        "PORT": "3306",                      # Default MySQL port
        "OPTIONS": {
            "charset": "utf8mb4",            # Full Unicode support (including emojis)
            "init_command": "SET sql_mode='STRICT_TRANS_TABLES'",  # Strict mode
        },
    }
}


# ---------------------------------------------------------------------------
# CUSTOM USER MODEL
# ---------------------------------------------------------------------------
# We use a custom User model so we can extend it later if needed
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
LOGIN_URL = "login"                     # Where to redirect if user is not logged in
LOGIN_REDIRECT_URL = "dashboard:home"   # Where to go after successful login
LOGOUT_REDIRECT_URL = "login"           # Where to go after logout


# ---------------------------------------------------------------------------
# PASSWORD VALIDATION
# ---------------------------------------------------------------------------
AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]


# ---------------------------------------------------------------------------
# SESSION SETTINGS (important for hospital shared computers)
# ---------------------------------------------------------------------------
SESSION_COOKIE_AGE = 60 * 60 * 1          # Session lasts 1 hours
SESSION_SAVE_EVERY_REQUEST = True         # Extend session on every request
SESSION_EXPIRE_AT_BROWSER_CLOSE = True    # Logout when browser is closed


# ---------------------------------------------------------------------------
# INTERNATIONALIZATION
# ---------------------------------------------------------------------------
LANGUAGE_CODE = "en-us"
TIME_ZONE = "Africa/Dar_es_Salaam"        # Tanzania timezone
USE_I18N = True
USE_TZ = True


# ---------------------------------------------------------------------------
# STATIC FILES (CSS, JavaScript, Images)
# ---------------------------------------------------------------------------
STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]


# ---------------------------------------------------------------------------
# MEDIA FILES (Uploaded files - QR codes, reports, etc.)
# ---------------------------------------------------------------------------
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"           # Where patient QR codes will be stored


# ---------------------------------------------------------------------------
# DEFAULT PRIMARY KEY FIELD TYPE
# ---------------------------------------------------------------------------
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# ---------------------------------------------------------------------------
# LOGGING CONFIGURATION
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