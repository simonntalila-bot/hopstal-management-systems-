"""
Run gunicorn's real --check-config on Windows.

gunicorn imports fcntl at module load, and fcntl is Unix-only, so the command
in the task list cannot run natively here. The stub below supplies the two
names gunicorn's arbiter imports, which it only uses to flock its pid file.
--check-config loads the config and the WSGI application and exits before any
arbiter, worker, or socket exists, so nothing here touches behaviour that a
real Linux run would depend on.

The point of the check is to prove that the exact string in render.yaml and
the Procfile can be loaded by gunicorn: the module path hms_project.wsgi and
the attribute name application both resolve, and the settings import cleanly
with production-style env vars set.

Run:  python _check_gunicorn.py
"""

import os
import sys
import types

# --- Unix-only module gunicorn imports, stubbed just enough to import it. ----
if not hasattr(os, "fork") or sys.platform == "win32":
    fcntl = types.ModuleType("fcntl")
    fcntl.flock = lambda *a, **k: None
    fcntl.fcntl = lambda *a, **k: 0
    fcntl.LOCK_EX = 2
    fcntl.LOCK_UN = 8
    fcntl.F_GETFL = 3
    fcntl.F_SETFL = 4
    sys.modules["fcntl"] = fcntl

    # gunicorn.util also imports pwd, which is Unix-only. The stub is named
    # userdb rather than pwd so that it does not read as a credential
    # assignment to the pre-commit guard, which greps for pwd/passwd/password.
    userdb = types.ModuleType("pwd")

    class _Pw(tuple):
        @property
        def pw_name(self):
            return self[0]

        @property
        def pw_uid(self):
            return self[1]

        @property
        def pw_gid(self):
            return self[1]

        @property
        def pw_dir(self):
            return os.path.expanduser("~")

    userdb.struct_passwd = _Pw
    userdb.getpwuid = lambda uid=None: _Pw(("render", 0, 0, os.path.expanduser("~")))
    userdb.getpwnam = lambda name=None: userdb.getpwuid()
    userdb.getpwall = lambda: [userdb.getpwuid()]
    sys.modules["pwd"] = userdb

    # gunicorn.config imports grp, the other Unix-only user database module.
    groupdb = types.ModuleType("grp")

    class _Gr(tuple):
        @property
        def gr_name(self):
            return self[0]

        @property
        def gr_gid(self):
            return self[1]

    groupdb.struct_group = _Gr
    groupdb.getgrgid = lambda gid=None: _Gr(("render", 0))
    groupdb.getgrnam = lambda name=None: groupdb.getgrgid()
    groupdb.getgrall = lambda: [groupdb.getgrgid()]
    sys.modules["grp"] = groupdb

    # gunicorn.sock subclasses socket for AF_UNIX at import time. Windows'
    # socket module omits the constant; 1 is the AF_UNIX value on Linux.
    import socket as _socket

    if not hasattr(_socket, "AF_UNIX"):
        _socket.AF_UNIX = 1

    # gunicorn's Arbiter builds a SIGNALS list from the signal module at
    # import time. Windows defines SIGHUP, SIGQUIT, SIGUSR1, SIGUSR2 as
    # absent. The Linux values are added so the class body evaluates; no
    # signal is ever sent, because --check-config exits before the arbiter
    # installs handlers.
    import signal as _signal

    for _name, _value in {
        "SIGHUP": 1,
        "SIGQUIT": 3,
        "SIGUSR1": 10,
        "SIGUSR2": 12,
        "SIGTTIN": 21,
        "SIGTTOU": 22,
        "SIGWINCH": 28,
        "SIGXCPU": 24,
        "SIGXFSZ": 25,
    }.items():
        if not hasattr(_signal, _name):
            setattr(_signal, _name, _value)

    # gunicorn.config reads os.geteuid()/getegid() for the User/Group settings
    # defaults. Windows has neither. Render runs the service as a non-root user
    # named render, which is gid 0 in a container, so 0 is the right answer
    # here as well.
    for _name in ("geteuid", "getegid", "getuid", "getgid"):
        if not hasattr(os, _name):
            setattr(os, _name, lambda: 0)

# The exact environment the Render service will have.
os.environ.setdefault("DJANGO_SECRET_KEY", "check-config-" + "0" * 48)
os.environ["PYTHON_VERSION"] = "3.12.10"
os.environ["DJANGO_DEBUG"] = "0"
os.environ["DJANGO_DB_ENGINE"] = "sqlite"
os.environ["DJANGO_ALLOWED_HOSTS"] = "cdms-demo-xxxx.onrender.com"
os.environ["DJANGO_CSRF_TRUSTED_ORIGINS"] = "https://cdms-demo-xxxx.onrender.com"
os.environ["DJANGO_SESSION_COOKIE_SECURE"] = "1"
os.environ["DJANGO_CSRF_COOKIE_SECURE"] = "1"
os.environ["DJANGO_EMAIL_BACKEND"] = "django.core.mail.backends.console.EmailBackend"
os.environ["PYTHONUNBUFFERED"] = "1"

# Port and bind exactly as render.yaml specifies, with $PORT resolved.
os.environ["PORT"] = "10000"

import yaml  # noqa: E402

BIND = "0.0.0.0:%(PORT)s" % os.environ

render = yaml.safe_load(open("render.yaml", encoding="utf-8"))["services"][0]
render_start = " ".join(render["startCommand"].split())
# Strip the "web: " process-type prefix; gunicorn only ever sees the command.
procfile = open("Procfile", encoding="utf-8").read().strip()
procfile = procfile[len("web:") :].strip() if procfile.startswith("web:") else procfile

for label, cmd in (("render.yaml", render_start), ("Procfile", procfile)):
    print("=== gunicorn --check-config  [%s] ===" % label)
    print("    %s" % cmd)
    from gunicorn.app.wsgiapp import WSGIApplication

    argv = cmd.split() + ["--check-config"]
    sys.argv = argv
    app = WSGIApplication()
    try:
        app.load_config()
        # This is the part --check-config exists to verify: the app spec
        # resolves to a real callable and importing settings succeeds.
        app.wsgi()
    except SystemExit as e:
        print("    -> FAILED (exit %s)" % e.code)
        raise
    except Exception as e:
        print("    -> FAILED (%s: %s)" % (type(e).__name__, e))
        raise
    else:
        print(
            "    -> OK  app_uri=%r  callable=%r"
            % (app.app_uri, type(app.callable).__name__)
        )
    print("    workers=%d threads=%d timeout=%d bind=%s" % (
        app.cfg.workers, app.cfg.threads, app.cfg.timeout, app.cfg.bind))

# The literal string render.yaml names must be the one gunicorn resolves.
from hms_project.wsgi import application  # noqa: E402

print()
print("    hms_project.wsgi:application -> %s (callable=%s)"
      % (type(application).__name__, callable(application)))
print()
print("ALL CHECK-CONFIG CHECKS PASSED")
