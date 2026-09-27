# Render deployment (DEMO / TEST only)

This is the path for putting a public demo of the CDMS on
<https://render.com> without buying a VPS. It produces an `onrender.com`
hostname.

**It does not touch `makongatiarg.co.tz`.** DNS for that domain stays exactly
where it is. Production (MySQL on a real host) is a separate deployment, see
[DEPLOYMENT.md](DEPLOYMENT.md).

## What this demo is, and is not

| | Render demo | Production |
|---|---|---|
| Database | SQLite, one local file | MySQL |
| Data | invented, reseeded on every deploy | real records |
| Survives a redeploy | no | yes |
| Survives a restart | no | yes |
| Sleeps when idle | yes, after 15 min | no |
| Hostname | `*.onrender.com` | `makongatiarg.co.tz` |

Render's filesystem is ephemeral. Every deploy and every restart throws the
SQLite file away, and `releaseCommand` rebuilds it from scratch. That is
fine for invented demo data, but **anything typed into the demo by hand is
lost**, and demo logins stop working after a restart until you log in again.

**Never enter a real patient into the Render demo.**

## Before you start

- Access to <https://github.com/simonntalila-bot/hopstal-management-systems->, branch `main`
- A Render account, and the repository added to it

`render.yaml` in this repository does most of the configuration for you. The
two `sync: false` values are the only things you have to supply by hand.

## Steps

### 1. Push the render.yaml commit

Render reads the blueprint from the repository, so `render.yaml` has to be on
GitHub before you create the service. Commit and push it locally first.

### 2. New Web Service from the repository

1. Render dashboard -> **New** -> **Web Service**
2. **Connect a repository** -> pick
   `simonntalila-bot/hopstal-management-systems-`
3. If asked how to deploy, choose **Blueprint**. Render reads `render.yaml`
   and fills in the build, start and release commands for you.
4. If you chose *Web Service* instead of *Blueprint*, use these by hand:
   - Runtime: Python
   - Build command:
     `pip install --no-cache-dir -r requirements.txt && python manage.py collectstatic --no-input`
   - Start command:
     `gunicorn hms_project.wsgi:application --workers 2 --threads 4 --timeout 120 --bind 0.0.0.0:$PORT --access-logfile - --error-logfile -`

### 3. Fill in the two values Render asks for

Render prompts for the environment variables marked `sync: false`. It shows
the service name as a suggestion; use the hostname it gives you, with no
scheme and no trailing slash:

| Variable | Value |
|---|---|
| `DJANGO_ALLOWED_HOSTS` | `cdms-demo` (your exact hostname) |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | `https://cdms-demo` (scheme included) |

If you skip this the site loads and then every request fails with
`DisallowedHost`. That is the check working, not a broken build.

Before you deploy, check the Environment tab has no leftover rows:

- delete any row with an **empty key** (Render reports `Key Required`)
- delete any row called **`hospital`**, and any second copy of a name above
  (Render reports `Duplicate key "hospital" is not allowed`)

Every key must appear exactly once.

### 4. Deploy

Render builds, runs the release command (`migrate` then `seed_demo`), then
starts gunicorn. Watch the log; you should see all three of these:

```
Using Python version 3.12.10        <- not "3.14.3 (default)"
Demo data ready.                   <- seed_demo, from the release step
Booting worker                     <- gunicorn
```

If the first line says `(default)`, the Python pin was not picked up. See
[Troubleshooting a failed build](#troubleshooting-a-failed-build).

If `Demo data ready.` is missing, the release step did not run and there is no
database yet.

### 5. Get the URL

Render shows `https://<your-service>.onrender.com`. Open it. You should land
on the sign-in page:

```
Sign in | CDMS - Argentina Dispensary
```

### 6. Log in with a demo account

Every demo account shares one password: `CDMS-demo-2026`

| Username | Role |
|---|---|
| `demo.admin` | Administrator |
| `demo.reception` | Reception |
| `demo.doctor` | Doctor |
| `demo.nurse` | Nurse |
| `demo.pharmacy` | Pharmacy |
| `demo.lab` | Laboratory |
| `demo.rch` | RCH |
| `demo.labour` | Labour |
| `demo.ultrasound` | Ultrasound |
| `demo.injection` | Injection |

Sign in as `demo.admin` to see the widest set of pages. These are invented
accounts on an invented database.

## If it does not work

| Symptom | Cause | Fix |
|---|---|---|
| `DisallowedHost` on every page | `DJANGO_ALLOWED_HOSTS` wrong or blank | Set it to the exact hostname, no scheme |
| Sign-in fails, log-in page loads | `DJANGO_CSRF_TRUSTED_ORIGINS` wrong | Set it to `https://<hostname>` with the scheme |
| 404 on every page | `collectstatic` or `migrate` did not run | Check the build and release log for errors |
| `ImproperlyConfigured: DJANGO_SECRET_KEY is not set` | `generateValue` did not apply | Re-add `DJANGO_SECRET_KEY` and let Render generate it |
| No CSS, unstyled pages | `collectstatic` failed | Run it locally to see the error |
| 500, blank page | real error | The Render log has the traceback; `PYTHONUNBUFFERED=1` is already set so it appears immediately |
| First request hangs ~1 min | free plan waking from sleep | expected; later requests are fast |
| Logged out unexpectedly | database was wiped by a restart | log in again; see the table at the top |

## Troubleshooting a failed build

### `Using Python version 3.14.3 (default)`

Render is on its own default instead of the pinned 3.12.10. The word
**`(default)`** is the tell: it means the pin was not picked up, not that the
pin is wrong.

Render reads the Python version from different places depending on how the
service was created:

| Source | Read for a Blueprint service | Read for a hand-made service |
|---|---|---|
| `.python-version` | yes | **yes** |
| `runtime.txt` | yes | **yes** |
| `PYTHON_VERSION` env var in `render.yaml` | yes | **no** |

So `.python-version` is the pin that works either way. If you built the
service by hand and the log still says 3.14, set `PYTHON_VERSION=3.12.10` in
the dashboard's environment, or recreate the service as a Blueprint.

### A build command with a fragment glued onto the front

A log line like

```
ERROR: Could not open requirements file: [Errno 2] No such file or
       directory: 'requirements.txtpip'
```

means two build commands were concatenated. This happens when a build
command is typed into the dashboard *and* one is also set in `render.yaml`.
They cannot both apply.

Pick one:

- **Blueprint (recommended).** Clear the Build Command field in the Render
  dashboard and leave it to `render.yaml`.
- **Hand-made service.** Clear nothing, and set the three commands by hand to
  exactly what `render.yaml` has (see the three blocks below).

If you cannot tell which mode the service is in, look at the build log: a
Blueprint echoes the commands from `render.yaml` verbatim, including the
`--no-cache-dir` and the `&&`.

### `Duplicate key "hospital" is not allowed`

Two environment variables share a name. `hospital` was not a typo to fix but a
row to delete: the settings module never reads a variable called `hospital`.
Only these are used, and each must appear exactly once:

```
PYTHON_VERSION
DJANGO_SECRET_KEY
DJANGO_DEBUG
DJANGO_DB_ENGINE
DJANGO_ALLOWED_HOSTS
DJANGO_CSRF_TRUSTED_ORIGINS
DJANGO_SESSION_COOKIE_SECURE
DJANGO_CSRF_COOKIE_SECURE
DJANGO_EMAIL_BACKEND
PYTHONUNBUFFERED
```

### `Key Required`

An environment variable row has an empty key. Delete the row. A key must be a
name like `DJANGO_DEBUG`, with no spaces, and no duplicate.

### `--noinput` is not a flag

Django spells it `--no-input`, with the hyphen. `--noinput` fails the step
instead of suppressing the prompt, and a failed step is what leaves you with
no database.

### Nothing renders but the log has no error

Check which version of Python ran and whether the release step ran at all:

```
Using Python version ...
Demo data ready.        <- seed_demo
Booting worker          <- gunicorn
```

`Demo data ready.` comes from `releaseCommand`. If it is missing, the schema
and the demo data were never created, and every page that touches the database
will fail.

## The three commands

Build, release and start are three separate steps. Do not merge them.

| Step | Command | What it does |
|---|---|---|
| Build | `pip install --no-cache-dir -r requirements.txt && python manage.py collectstatic --no-input` | installs dependencies, collects static files |
| Release | `python manage.py migrate --no-input && python manage.py seed_demo` | creates the schema, fills it with demo data |
| Start | `gunicorn hms_project.wsgi:application --workers 2 --threads 4 --timeout 120 --bind 0.0.0.0:$PORT --access-logfile - --error-logfile -` | serves the site |

Migrations deliberately stay out of the build step: a build can be started and
abandoned, and a half-migrated database is harder to reason about than an
empty one. `--force-in-production` is deliberately absent from the release
command, so that a database accidentally pointed at MySQL fails loudly rather
than being filled with invented patient records.

`core/test_deployment.py` enforces all of this. It fails the suite if the
commands are merged, if a command is duplicated, if a flag is misspelled, if
`PYTHON_VERSION` is not 3.12.10, or if an environment variable key is empty or
duplicated. Run it with:

```
python manage.py test core.test_deployment --settings=hms_project.test_settings
```

## What not to do here

- Do not point `makongatiarg.co.tz` at Render for this demo. DNS changes are
  a separate decision, made on purpose, with a real host behind it.
- Do not add real patient data.
- Do not put production mail, AWS or database credentials in these variables.
- Do not treat this as a staging copy of production. It has no backup, no
  uptime guarantee, and loses its data.

## Moving this to real hosting later

The blueprint is throwaway; the application is not. For a real host the
equivalent is MySQL plus gunicorn plus nginx plus a certificate, and those
files are already written:

```
deploy/bootstrap.sh              install OS packages, Python, database
deploy/deploy.sh                 pull, migrate, collectstatic, restart
deploy/gunicorn_config.py        gunicorn settings
deploy/systemd/cdms.service      keep gunicorn running
deploy/nginx/makongatiarg.co.tz.conf   reverse proxy and certificate
docs/DEPLOYMENT.md               the full runbook
```

The SQLite setting is the only thing that changes: set `DJANGO_DB_ENGINE` to
MySQL's default (unset it) and supply `DB_NAME`, `DB_USER`, `DB_PASSWORD`,
`DB_HOST` and `DB_PORT`.
