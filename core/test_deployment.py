"""
Tests for the Render deployment configuration.

The failure this guards against was real: a build command got typed into the
Render dashboard as well as being set in render.yaml, and the two were
concatenated into

    pip install -r requirements.txtpip install -r requirements.txt && ...

and the log reported Python 3.14 because the blueprint was never read. Both
are invisible to `manage.py check`, so they are pinned here instead.

A duplicate mapping key is the other thing this catches: Render rejects
`Duplicate key "hospital" is not allowed` before the build even starts, and
PyYAML silently keeps the last value for a repeated key by default, so a
plain safe_load would not notice it.
"""

import re
import unittest
from pathlib import Path

from django.test import SimpleTestCase

import hms_project

try:
    import yaml
except ImportError:  # pragma: no cover - PyYAML is a dev-only dependency
    yaml = None

BASE_DIR = Path(hms_project.__file__).resolve().parent.parent
RENDER_YAML = BASE_DIR / "render.yaml"
PYTHON_VERSION_FILE = BASE_DIR / ".python-version"
RUNTIME_TXT = BASE_DIR / "runtime.txt"
PROCFILE = BASE_DIR / "Procfile"

# Kept in step with .python-version and runtime.txt by test_python_version_is_pinned_everywhere.
EXPECTED_PYTHON = "3.12.10"


def _no_duplicate_keys(loader, node, deep=False):
    """PyYAML loader hook that refuses a repeated mapping key."""
    mapping = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise AssertionError("duplicate YAML key: %r" % (key,))
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


if yaml is not None:
    yaml.SafeLoader.add_constructor(
        yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _no_duplicate_keys
    )


def _flatten(command):
    return " ".join(str(command).split())


@unittest.skipUnless(yaml is not None, "PyYAML is not installed")
class RenderYamlTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Asserts there are no duplicate keys anywhere, including duplicates
        # inside a single service's envVars list, which the dashboard reports
        # as `Duplicate key "..." is not allowed`.
        raw = yaml.safe_load(RENDER_YAML.read_text(encoding="utf-8"))
        cls.services = raw["services"]
        cls.service = cls.services[0]

    def env_map(self):
        return {e["key"]: e for e in self.service["envVars"]}

    def test_file_exists(self):
        self.assertTrue(RENDER_YAML.is_file(), "render.yaml is missing")

    def test_exactly_one_web_service(self):
        self.assertEqual(len(self.services), 1)
        self.assertEqual(self.service["type"], "web")
        self.assertEqual(self.service["runtime"], "python")

    def test_python_version_is_3_12_10(self):
        self.assertEqual(
            self.env_map()["PYTHON_VERSION"]["value"],
            EXPECTED_PYTHON,
            "PYTHON_VERSION must pin %s, not Render's default 3.14" % EXPECTED_PYTHON,
        )

    def test_every_env_var_key_is_non_empty(self):
        for entry in self.service["envVars"]:
            key = entry.get("key", "")
            self.assertTrue(
                key.strip(),
                "an envVars entry has an empty key, which Render rejects "
                "with 'Key Required'",
            )
            self.assertEqual(key, key.strip(), "envVar key %r has stray space" % key)

    def test_env_var_keys_are_unique(self):
        keys = [e["key"] for e in self.service["envVars"]]
        self.assertEqual(
            len(keys),
            len(set(keys)),
            "duplicate envVar keys: %s" % sorted({k for k in keys if keys.count(k) > 1}),
        )

    def test_no_hospital_key(self):
        # "hospital" was entered by hand and Render rejected it. The settings
        # module never reads it, so it can only ever be a typo.
        self.assertNotIn("hospital", self.env_map())

    def test_secret_key_is_generated_not_written_down(self):
        entry = self.env_map()["DJANGO_SECRET_KEY"]
        self.assertTrue(
            entry.get("generateValue"),
            "DJANGO_SECRET_KEY must use generateValue, never a literal value",
        )
        self.assertNotIn("value", entry)

    def test_debug_is_off(self):
        self.assertEqual(self.env_map()["DJANGO_DEBUG"]["value"], "0")

    def test_database_is_sqlite_for_the_demo(self):
        self.assertEqual(self.env_map()["DJANGO_DB_ENGINE"]["value"], "sqlite")

    def test_hostname_variables_wait_for_a_value(self):
        env = self.env_map()
        for key in ("DJANGO_ALLOWED_HOSTS", "DJANGO_CSRF_TRUSTED_ORIGINS"):
            self.assertIn(
                key, env, "%s must be declared" % key
            )
            self.assertIs(
                env[key].get("sync"),
                False,
                "%s must be sync: false; the hostname is not known until the "
                "service exists" % key,
            )

    def test_no_mysql_variables(self):
        # The demo must not carry production database credentials.
        for key in ("DB_NAME", "DB_USER", "DB_PASSWORD", "DB_HOST", "DB_PORT"):
            self.assertNotIn(key, self.env_map(), "%s does not belong here" % key)

    def test_build_command_installs_and_collects_static_only(self):
        build = _flatten(self.service["buildCommand"])
        self.assertIn("pip install", build)
        self.assertIn("-r requirements.txt", build)
        self.assertIn("collectstatic --no-input", build)
        # The bug this guards: a duplicated or appended command. A build
        # command must appear exactly once.
        self.assertEqual(
            build.count("pip install"), 1, "pip install is repeated: %s" % build
        )
        self.assertEqual(
            build.count("requirements.txt"), 1, "requirements.txt is repeated: %s" % build
        )
        # Schema and data belong in releaseCommand.
        for step in ("migrate", "seed_demo"):
            self.assertNotIn(
                step, build, "%s must not run in the build command" % step
            )

    def test_release_command_migrates_and_seeds(self):
        release = _flatten(self.service["releaseCommand"])
        self.assertIn("migrate --no-input", release)
        self.assertIn("seed_demo", release)
        self.assertNotIn("pip install", release)
        self.assertNotIn("collectstatic", release)
        # Deliberately absent: if the database is ever MySQL, seeding must fail
        # loudly instead of writing invented records into it.
        self.assertNotIn("--force-in-production", release)

    def test_commands_use_the_correct_flag_spelling(self):
        # --noinput is not a Django flag. It fails the step.
        for field in ("buildCommand", "releaseCommand"):
            self.assertNotIn("--noinput", _flatten(self.service[field]))

    def test_start_command_serves_the_wsgi_callable(self):
        start = _flatten(self.service["startCommand"])
        self.assertIn("gunicorn hms_project.wsgi:application", start)
        self.assertIn("0.0.0.0:$PORT", start)
        # Without the bind Render cannot reach the app at all.
        self.assertNotIn("127.0.0.1", start)

    def test_health_check_is_a_public_page(self):
        self.assertEqual(self.service["healthCheckPath"], "/accounts/login/")

    def test_commands_are_single_strings(self):
        # A YAML list here becomes a multi-line command, which is how a
        # duplicate fragment ends up glued to the previous one.
        for field in ("buildCommand", "releaseCommand", "startCommand"):
            self.assertIsInstance(self.service[field], str)


class PythonVersionPinTests(SimpleTestCase):
    """
    Render reads .python-version for every Python service, including one
    created by hand rather than from the blueprint, so this is the pin that
    survives a service someone made in the dashboard.
    """

    def test_python_version_file_matches(self):
        self.assertTrue(PYTHON_VERSION_FILE.is_file(), ".python-version is missing")
        self.assertEqual(
            PYTHON_VERSION_FILE.read_text(encoding="utf-8").strip(), EXPECTED_PYTHON
        )

    def test_runtime_txt_matches(self):
        self.assertEqual(
            RUNTIME_TXT.read_text(encoding="utf-8").strip(), "python-%s" % EXPECTED_PYTHON
        )

    def test_procfile_binds_the_render_port(self):
        # If Render ever falls back to the Procfile, a missing $PORT bind
        # leaves gunicorn on 127.0.0.1:8000 and nothing can reach it.
        procfile = PROCFILE.read_text(encoding="utf-8")
        self.assertIn("hms_project.wsgi:application", procfile)
        self.assertIn("${PORT", procfile)
        self.assertIn("0.0.0.0", procfile)


class WsgiImportTests(SimpleTestCase):
    def test_wsgi_application_is_importable(self):
        # The callable named in render.yaml's startCommand must exist, or the
        # container starts and immediately dies.
        from hms_project.wsgi import application

        self.assertTrue(callable(application))
