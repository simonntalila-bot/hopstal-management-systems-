"""
deploy/cpanel/passenger_wsgi.py
===============================
WSGI entry point for Passenger, which is what cPanel's "Setup Python App"
runs. The VPS deployment does not use this file; it uses
hms_project.wsgi:application via systemd and Gunicorn.

Why a separate file:
  Passenger looks for `passenger_wsgi.py` in the application root and imports
  it directly. Pointing cPanel at `hms_project.wsgi:application` also works on
  most hosts, but having the conventional filename removes a class of
  "it boots but 500s" configuration differences between hosts.

This file must stay tiny. Passenger imports it on every request in
development mode and on every application restart in production, so nothing
expensive or side-effecting belongs here.
"""

import os
import sys

# cPanel places the application in something like
# /home/<user>/<appname>/ and runs Passenger with the application root as the
# working directory. Make sure both the app root and the project directory are
# importable, because the settings module lives one level down.
APP_ROOT = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.abspath(os.path.join(APP_ROOT, ".."))

for path in (PROJECT_DIR, APP_ROOT):
    if path not in sys.path:
        sys.path.insert(0, path)

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "hms_project.settings")

from django.core.wsgi import get_wsgi_application  # noqa: E402

application = get_wsgi_application()
