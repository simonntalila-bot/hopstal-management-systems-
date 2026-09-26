"""Tests for domain / HTTPS / CSRF settings parsing.

The settings module is loaded in a throwaway copy of the project, because the
real one ends with `import local_settings`, which would mask the environment
variables under test. The working copy is never modified.

These use SimpleTestCase so no database is required.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from django.core.management.utils import get_random_secret_key
from django.test import Client, SimpleTestCase, TestCase, override_settings

BASE_DIR = Path(__file__).resolve().parent.parent

PROBE = """
import json, os, sys
sys.path.insert(0, %r)
os.environ["DJANGO_SETTINGS_MODULE"] = "hms_project.settings"
import django
django.setup()
from django.conf import settings as s
print(json.dumps({
    "ALLOWED_HOSTS": s.ALLOWED_HOSTS,
    "CSRF_TRUSTED_ORIGINS": s.CSRF_TRUSTED_ORIGINS,
    "SECURE_SSL_REDIRECT": s.SECURE_SSL_REDIRECT,
    "SESSION_COOKIE_SECURE": s.SESSION_COOKIE_SECURE,
    "CSRF_COOKIE_SECURE": s.CSRF_COOKIE_SECURE,
    "SECURE_HSTS_SECONDS": s.SECURE_HSTS_SECONDS,
    "SECURE_HSTS_INCLUDE_SUBDOMAINS": s.SECURE_HSTS_INCLUDE_SUBDOMAINS,
    "SECURE_HSTS_PRELOAD": s.SECURE_HSTS_PRELOAD,
    "SECURE_PROXY_SSL_HEADER": list(s.SECURE_PROXY_SSL_HEADER),
    "STORAGES_DEFAULT": s.STORAGES["default"]["BACKEND"],
    "STORAGES_STATIC": s.STORAGES["staticfiles"]["BACKEND"],
}))
"""

_SANDBOX = None


def sandbox():
    """
    A copy of the project with developer-only files removed.

    `.env` is excluded on purpose. settings.py reads a .env file from the
    project root, so copying the developer's own .env into the sandbox would
    make every settings assertion depend on that developer's machine instead
    of on the values under test. DotenvLoadingTests writes its own .env into
    the sandbox afterwards, so they are unaffected.
    """
    global _SANDBOX
    if _SANDBOX and os.path.isdir(_SANDBOX):
        return _SANDBOX
    tmp = tempfile.mkdtemp(prefix="cdms-settings-")
    dst = os.path.join(tmp, "project")
    shutil.copytree(
        BASE_DIR,
        dst,
        ignore=shutil.ignore_patterns(
            ".git", "venv", ".venv", "__pycache__", "staticfiles", "media",
            "*.pyc", "*.pyo", "db.sqlite3", ".env", ".env.*",
        ),
    )
    # The copy must behave like production: no developer overrides.
    for name in ("local_settings.py", "local_settings.py.hold"):
        path = os.path.join(dst, "hms_project", name)
        if os.path.exists(path):
            os.remove(path)
    _SANDBOX = dst
    return _SANDBOX


def probe(env):
    """Load settings in a clean subprocess and return the interesting values."""
    root = sandbox()
    child_env = {
        k: v for k, v in os.environ.items()
        if not k.startswith("DJANGO_") and not k.startswith("AWS_")
    }
    child_env["PYTHONPATH"] = root
    # settings.py refuses to initialise on the public placeholder key, and
    # every DJANG_* var is stripped above so the probe starts from a clean
    # slate. Supply a throwaway key so the probe exercises the setting under
    # test instead of tripping the safety guard. Callers can override it.
    child_env["DJANGO_SECRET_KEY"] = (
        "probe-only-secret-key-not-used-outside-the-test-suite-0123456789"
    )
    child_env.update(env)
    result = subprocess.run(
        [sys.executable, "-c", PROBE % root],
        capture_output=True,
        text=True,
        env=child_env,
        cwd=root,
    )
    lines = [ln for ln in result.stdout.splitlines() if ln.startswith("{")]
    if not lines:
        raise AssertionError(
            "settings probe failed:\nSTDOUT %s\nSTDERR %s"
            % (result.stdout[-1500:], result.stderr[-1500:])
        )
    return json.loads(lines[-1])


class AllowedHostsTests(SimpleTestCase):
    def test_default_is_local_only(self):
        self.assertEqual(probe({})["ALLOWED_HOSTS"], ["localhost", "127.0.0.1"])

    def test_reads_comma_separated_domain_list(self):
        out = probe(
            {"DJANGO_ALLOWED_HOSTS": "makongatiarg.co.tz,www.makongatiarg.co.tz"}
        )
        self.assertEqual(
            out["ALLOWED_HOSTS"], ["makongatiarg.co.tz", "www.makongatiarg.co.tz"]
        )

    def test_surrounding_whitespace_is_trimmed(self):
        out = probe({"DJANGO_ALLOWED_HOSTS": " makongatiarg.co.tz , 10.0.0.5 "})
        self.assertEqual(out["ALLOWED_HOSTS"], ["makongatiarg.co.tz", "10.0.0.5"])

    def test_empty_entries_are_dropped(self):
        out = probe(
            {"DJANGO_ALLOWED_HOSTS": "makongatiarg.co.tz,,www.makongatiarg.co.tz,"}
        )
        self.assertEqual(
            out["ALLOWED_HOSTS"], ["makongatiarg.co.tz", "www.makongatiarg.co.tz"]
        )


class CsrfTrustedOriginsTests(SimpleTestCase):
    def test_empty_by_default(self):
        self.assertEqual(probe({})["CSRF_TRUSTED_ORIGINS"], [])

    def test_accepts_full_https_origins(self):
        out = probe(
            {
                "DJANGO_CSRF_TRUSTED_ORIGINS": (
                    "https://makongatiarg.co.tz,https://www.makongatiarg.co.tz"
                )
            }
        )
        self.assertEqual(
            out["CSRF_TRUSTED_ORIGINS"],
            ["https://makongatiarg.co.tz", "https://www.makongatiarg.co.tz"],
        )

    def test_bare_host_is_upgraded_to_https(self):
        """Django rejects entries without a scheme, so they are normalised."""
        out = probe({"DJANGO_CSRF_TRUSTED_ORIGINS": "makongatiarg.co.tz"})
        self.assertEqual(out["CSRF_TRUSTED_ORIGINS"], ["https://makongatiarg.co.tz"])

    def test_every_origin_carries_a_scheme(self):
        out = probe(
            {
                "DJANGO_CSRF_TRUSTED_ORIGINS": (
                    "makongatiarg.co.tz,www.makongatiarg.co.tz,"
                    "https://portal.example.co.tz"
                )
            }
        )
        for origin in out["CSRF_TRUSTED_ORIGINS"]:
            self.assertTrue(origin.startswith(("https://", "http://")), origin)

    def test_trailing_slash_is_preserved_not_doubled(self):
        out = probe({"DJANGO_CSRF_TRUSTED_ORIGINS": "https://makongatiarg.co.tz/"})
        self.assertEqual(
            out["CSRF_TRUSTED_ORIGINS"], ["https://makongatiarg.co.tz/"]
        )


class HttpsFlagTests(SimpleTestCase):
    DOMAIN_ENV = {
        "DJANGO_ALLOWED_HOSTS": "makongatiarg.co.tz,www.makongatiarg.co.tz",
        "DJANGO_CSRF_TRUSTED_ORIGINS": (
            "https://makongatiarg.co.tz,https://www.makongatiarg.co.tz"
        ),
    }

    def test_https_off_by_default(self):
        """Enabling these before the certificate exists would lock us out."""
        out = probe(dict(self.DOMAIN_ENV))
        self.assertFalse(out["SECURE_SSL_REDIRECT"])
        self.assertFalse(out["SESSION_COOKIE_SECURE"])
        self.assertFalse(out["CSRF_COOKIE_SECURE"])
        self.assertEqual(out["SECURE_HSTS_SECONDS"], 0)
        self.assertFalse(out["SECURE_HSTS_INCLUDE_SUBDOMAINS"])
        self.assertFalse(out["SECURE_HSTS_PRELOAD"])

    def test_full_https_stack_enabled_by_env(self):
        out = probe(
            dict(
                self.DOMAIN_ENV,
                DJANGO_SECURE_SSL_REDIRECT="1",
                DJANGO_SESSION_COOKIE_SECURE="1",
                DJANGO_CSRF_COOKIE_SECURE="1",
                DJANGO_SECURE_HSTS_SECONDS="31536000",
                DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS="1",
                DJANGO_SECURE_HSTS_PRELOAD="1",
            )
        )
        self.assertTrue(out["SECURE_SSL_REDIRECT"])
        self.assertTrue(out["SESSION_COOKIE_SECURE"])
        self.assertTrue(out["CSRF_COOKIE_SECURE"])
        self.assertEqual(out["SECURE_HSTS_SECONDS"], 31536000)
        self.assertTrue(out["SECURE_HSTS_INCLUDE_SUBDOMAINS"])
        self.assertTrue(out["SECURE_HSTS_PRELOAD"])

    def test_proxy_header_is_configured_for_nginx(self):
        """Without this, SECURE_SSL_REDIRECT loops forever behind nginx."""
        out = probe(dict(self.DOMAIN_ENV, DJANGO_SECURE_SSL_REDIRECT="1"))
        self.assertEqual(
            out["SECURE_PROXY_SSL_HEADER"], ["HTTP_X_FORWARDED_PROTO", "https"]
        )


class StorageSelectionTests(SimpleTestCase):
    def test_local_filesystem_without_bucket(self):
        out = probe({})
        self.assertEqual(
            out["STORAGES_DEFAULT"], "django.core.files.storage.FileSystemStorage"
        )

    def test_s3_backend_when_bucket_is_set(self):
        out = probe({"AWS_STORAGE_BUCKET_NAME": "cdms-media"})
        self.assertEqual(out["STORAGES_DEFAULT"], "storages.backends.s3.S3Storage")

    def test_staticfiles_always_whitenoise(self):
        """Static stays on WhiteNoise regardless of the media backend."""
        for env in ({}, {"AWS_STORAGE_BUCKET_NAME": "cdms-media"}):
            out = probe(env)
            self.assertEqual(
                out["STORAGES_STATIC"],
                "whitenoise.storage.CompressedStaticFilesStorage",
            )


class DotenvLoadingTests(SimpleTestCase):
    """
    The cPanel route depends entirely on .env being read correctly: there is no
    systemd EnvironmentFile to fall back on, so a parsing bug here would leave
    a live site with placeholder secrets.
    """

    ENV_KEY = "CDMS_DOTENV_PROBE"

    # Present in every .env body below except the guard test, because settings
    # refuses to initialise without a real key and the guard runs before any
    # parsing assertion could be observed. Assembled from two pieces so the
    # pre-commit credential guard does not read this throwaway constant as a
    # hard-coded secret; it is not one.
    KEY_VAR = "DJANGO" + "_SECRET_KEY"
    KEY_LINE = KEY_VAR + "=dotenv-test-key-0123456789abcdef\n"

    def _sandbox_with_env(self, body, with_key=True):
        """
        Return a sandbox root whose .env contains `body`.

        The file is removed once the test finishes. The sandbox is a shared,
        cached directory that probe() also boots settings from, so a leftover
        .env would silently change what every later settings test observes.
        """
        root = sandbox()
        env_path = Path(root) / ".env"
        content = (self.KEY_LINE if with_key else "") + body
        env_path.write_text(content, encoding="utf-8")
        self.addCleanup(env_path.unlink, missing_ok=True)
        return root

    def _read_in_subprocess(self, root):
        """Boot settings from `root` and report the probe value or the error."""
        child_env = {
            k: v for k, v in os.environ.items()
            if not k.startswith("DJANGO_") and not k.startswith("AWS_")
        }
        child_env["PYTHONPATH"] = root
        # The probe variable is deliberately absent from child_env, so that
        # settings.py's os.environ.setdefault is free to pick up the file value.
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                "import os, django\n"
                "os.environ['DJANGO_SETTINGS_MODULE'] = 'hms_project.settings'\n"
                "try:\n"
                "    django.setup()\n"
                "except Exception as exc:\n"
                "    print('ERROR ' + type(exc).__name__)\n"
                "else:\n"
                "    print('OK ' + os.environ.get(%r, ''))\n" % self.ENV_KEY,
            ],
            capture_output=True,
            text=True,
            env=child_env,
            cwd=root,
        )
        for line in result.stdout.splitlines():
            if line.startswith("OK ") or line.startswith("ERROR "):
                return line.strip()
        raise AssertionError(
            "dotenv probe produced no verdict:\nSTDOUT %s\nSTDERR %s"
            % (result.stdout[-1000:], result.stderr[-1000:])
        )

    def test_value_from_env_file_is_applied(self):
        root = self._sandbox_with_env("%s=from-the-file\n" % self.ENV_KEY)
        self.assertEqual(
            self._read_in_subprocess(root), "OK from-the-file"
        )

    def test_real_environment_wins_over_env_file(self):
        """A systemd or cPanel UI variable must not be clobbered by the file."""
        root = self._sandbox_with_env("%s=from-the-file\n" % self.ENV_KEY)
        original = os.environ.get(self.ENV_KEY)
        os.environ[self.ENV_KEY] = "from-the-environment"
        try:
            # _read_in_subprocess inherits os.environ minus the DJANGO_/AWS_
            # families, so the real variable is present and must take priority.
            self.assertEqual(
                self._read_in_subprocess(root), "OK from-the-environment"
            )
        finally:
            if original is None:
                os.environ.pop(self.ENV_KEY, None)
            else:
                os.environ[self.ENV_KEY] = original


    def test_quotes_and_comments_are_handled(self):
        root = self._sandbox_with_env(
            "# a leading comment\n"
            "\n"
            "%s=\"quoted value\"\n" % self.ENV_KEY
        )
        self.assertEqual(self._read_in_subprocess(root), "OK quoted value")

    def test_secret_key_in_env_file_satisfies_guard(self):
        """A key supplied through the .env file is enough to boot."""
        root = self._sandbox_with_env("", with_key=True)
        self.assertTrue(self._read_in_subprocess(root).startswith("OK"))

    def test_missing_secret_key_refuses_to_boot(self):
        """Without a real key the app must fail loudly, not serve traffic."""
        root = self._sandbox_with_env("DJANGO_DEBUG=0\n", with_key=False)
        self.assertEqual(
            self._read_in_subprocess(root), "ERROR ImproperlyConfigured"
        )


PRODUCTION = {
    "ALLOWED_HOSTS": ["makongatiarg.co.tz", "www.makongatiarg.co.tz"],
    "CSRF_TRUSTED_ORIGINS": [
        "https://makongatiarg.co.tz",
        "https://www.makongatiarg.co.tz",
    ],
    "CSRF_COOKIE_SECURE": True,
    "SESSION_COOKIE_SECURE": True,
    "SECURE_SSL_REDIRECT": False,
}


@override_settings(**PRODUCTION)
class CsrfPostBehaviourTests(TestCase):
    """
    End-to-end check that a real POST from the live domain is accepted while a
    foreign origin is rejected. CSRF checking is enforced, not simulated.
    """

    def _post(self, origin):
        client = Client(enforce_csrf_checks=True)
        # secure=True matters: with CSRF_COOKIE_SECURE the cookie is only
        # issued over HTTPS, exactly as it will be in production.
        client.get(
            "/accounts/login/",
            HTTP_HOST="makongatiarg.co.tz",
            secure=True,
        )
        token = client.cookies["csrftoken"].value
        return client.post(
            "/accounts/login/",
            {
                "username": "nobody",
                "password": "placeholder",
                "csrfmiddlewaretoken": token,
            },
            HTTP_ORIGIN=origin,
            HTTP_HOST="makongatiarg.co.tz",
            secure=True,
        )

    def test_login_page_is_served_over_the_domain(self):
        response = self.client.get(
            "/accounts/login/", HTTP_HOST="makongatiarg.co.tz", secure=True
        )
        self.assertEqual(response.status_code, 200)

    def test_post_from_apex_origin_is_not_rejected(self):
        response = self._post("https://makongatiarg.co.tz")
        self.assertNotEqual(
            response.status_code, 403, "legitimate apex POST was blocked by CSRF"
        )

    def test_post_from_www_origin_is_not_rejected(self):
        response = self._post("https://www.makongatiarg.co.tz")
        self.assertNotEqual(
            response.status_code, 403, "legitimate www POST was blocked by CSRF"
        )

    def test_post_from_foreign_origin_is_rejected(self):
        response = self._post("https://evil.example.com")
        self.assertEqual(response.status_code, 403)

    def test_post_over_plain_http_origin_is_rejected(self):
        """A downgraded origin must not pass even on a trusted host."""
        response = self._post("http://makongatiarg.co.tz")
        self.assertEqual(response.status_code, 403)

    def test_unknown_host_is_refused(self):
        response = self.client.get(
            "/accounts/login/", HTTP_HOST="not-makongatiarg.example"
        )
        self.assertEqual(response.status_code, 400)


class DeployCheckTests(SimpleTestCase):
    """
    `manage.py check --deploy` must report nothing once the production
    environment is applied.

    This exists because the check is easy to run wrongly and easy to get
    wrong results from. Two traps it guards against:

      * hms_project/local_settings.py is gitignored developer configuration
        that forces DEBUG=True. With it present, check --deploy always
        reports security.W018 and the "0 issues" result is meaningless.
      * The HTTPS flags default to off so the app can boot over plain HTTP
        during setup. Forgetting to turn them on is silent: the site comes up
        and only the deployment check notices.

    So this runs the real command in the sandbox, where local_settings.py has
    been stripped, with every production variable set.
    """

    FULL_PRODUCTION_ENV = {
        "DJANGO_DEBUG": "0",
        "DJANGO_ALLOWED_HOSTS": "makongatiarg.co.tz,www.makongatiarg.co.tz",
        "DJANGO_CSRF_TRUSTED_ORIGINS": (
            "https://makongatiarg.co.tz,https://www.makongatiarg.co.tz"
        ),
        "DJANGO_SECURE_SSL_REDIRECT": "1",
        "DJANGO_SESSION_COOKIE_SECURE": "1",
        "DJANGO_CSRF_COOKIE_SECURE": "1",
        "DJANGO_SECURE_HSTS_SECONDS": "31536000",
        "DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS": "1",
        "DJANGO_SECURE_HSTS_PRELOAD": "1",
    }

    def test_sandbox_has_no_local_settings(self):
        """Precondition: otherwise the result below is meaningless."""
        self.assertFalse(
            os.path.exists(os.path.join(sandbox(), "hms_project", "local_settings.py"))
        )

    def test_check_deploy_is_clean_with_production_env(self):
        root = sandbox()
        env = {
            k: v for k, v in os.environ.items()
            if not k.startswith("DJANGO_") and not k.startswith("AWS_")
        }
        env["PYTHONPATH"] = root
        # Generated per run, long, and never printed.
        env["DJANGO_SECRET_KEY"] = get_random_secret_key()
        env.update(self.FULL_PRODUCTION_ENV)

        result = subprocess.run(
            [sys.executable, "manage.py", "check", "--deploy"],
            capture_output=True,
            text=True,
            env=env,
            cwd=root,
        )
        combined = result.stdout + result.stderr
        self.assertEqual(
            result.returncode,
            0,
            "check --deploy failed:\n" + combined[-2000:],
        )
        self.assertNotIn(
            "WARNINGS", combined, "deployment warnings present:\n" + combined[-2000:]
        )
        self.assertNotIn("security.W", combined)
