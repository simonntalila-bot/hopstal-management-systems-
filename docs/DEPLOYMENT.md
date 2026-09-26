# Deployment Plan — `makongatiarg.co.tz`

Architecture:

```
Internet
   │
   ▼
makongatiarg.co.tz  (DNS A / AAAA → VPS)
   │
   ▼
Nginx  :80 ──► /.well-known/acme-challenge/  (Let's Encrypt renewal)
   │       :443 ─┬─► /static/  → staticfiles/   (nginx, cached)
   │             ├─► /media/   → media/         (nginx, or S3 via Django)
   │             └─► /         → Gunicorn unix socket
   ▼
Gunicorn (systemd, unprivileged user, /srv/cdms/venv)
   │
   ▼
Django (hms_project.settings, env-driven)
   │
   ▼
MySQL 127.0.0.1:3306
```

Nothing in this document has been executed. No DNS change, no deployment.

---

## 1. DNS records to create

You create these at your domain registrar or DNS host. I do not have access
and did not change anything.

| Type | Name | Value | TTL | Purpose |
|---|---|---|---|---|
| `A` | `@` (apex = `makongatiarg.co.tz`) | `<VPS public IPv4>` | 300 | the site |
| `CNAME` | `www` | `makongatiarg.co.tz` | 300 | www → apex |

**Once you give me the VPS public IP, the exact records are:**

```
Type    Name    Value
A       @       YOUR_VPS_IPV4
CNAME   www     makongatiarg.co.tz
```

Notes:

- **`A` vs `AAAA`:** add an `AAAA` record *only* if the VPS has a working IPv6
  address and IPv6 is confirmed reachable. A wrong `AAAA` record breaks
  loading for IPv6 users. Tell me whether the VPS has IPv6 and I will say
  whether to add it.
- **No `A` record for `www` pointing at the IP.** Use `CNAME`, so the IP is
  defined in exactly one place.
- Both names must resolve **before** the Let's Encrypt HTTP challenge can
  succeed. Verify with `nslookup makongatiarg.co.tz` and
  `nslookup www.makongatiarg.co.tz` from another machine.
- Keep TTL at 300 while setting up; lower it to 3600 once the site is live.
- The current **502** means a DNS record already points somewhere that
  answers, or nothing is listening on port 80/443 at the target. If DNS
  already resolves to the intended VPS, do not add duplicates.

---

## 2. ALLOWED_HOSTS

Environment variable, comma-separated:

```
DJANGO_ALLOWED_HOSTS=makongatiarg.co.tz,www.makongatiarg.co.tz
```

Read by `hms_project/settings.py`. Default stays `localhost,127.0.0.1`, so a
missing variable can never accidentally expose the site publicly.

Do **not** use `*`. If you need a temporary health check from an external
host, add that single IP rather than opening the site to any Host header.

---

## 3. CSRF trusted origins

```
DJANGO_CSRF_TRUSTED_ORIGINS=https://makongatiarg.co.tz,https://www.makongatiarg.co.tz
```

Added as `CSRF_TRUSTED_ORIGINS` in settings, read from the environment. Django
requires a scheme on every entry, so a bare hostname is automatically upgraded
to `https://` (fails closed rather than silently disabling the check).

POSTs are accepted only when **all** of these hold:

1. `CSRF_TRUSTED_ORIGINS` contains the exact `Origin` of the request
2. the request reached Django as HTTPS — `SECURE_PROXY_SSL_HEADER` is
   already set to `("HTTP_X_FORWARDED_PROTO", "https")`, and
   `deploy/nginx/makongatiarg.co.tz.conf` sets `X-Forwarded-Proto` on every
   proxied request
3. `DJANGO_CSRF_COOKIE_SECURE=1`, so the CSRF cookie is only sent over HTTPS

Both hosts are listed, so a form submitted from the apex after landing on
`www` (or the reverse) is not rejected.

---

## 4. Environment variables

Copy `.env.example` to a file outside the repository and fill in the values:

```bash
sudo install -m 600 /dev/null /etc/cdms/cdms.env
sudo nano /etc/cdms/cdms.env          # paste from .env.example, then edit
```

Required names:

```
DJANGO_SECRET_KEY          DJANGO_DEBUG=0
DJANGO_ALLOWED_HOSTS       DJANGO_CSRF_TRUSTED_ORIGINS
DB_NAME   DB_USER   DB_PASSWORD   DB_HOST   DB_PORT
DJANGO_EMAIL_BACKEND   DJANGO_EMAIL_HOST   DJANGO_EMAIL_PORT
DJANGO_EMAIL_HOST_USER DJANGO_EMAIL_HOST_PASSWORD
DJANGO_EMAIL_USE_TLS   DJANGO_DEFAULT_FROM_EMAIL
DJANGO_SECURE_SSL_REDIRECT=1
DJANGO_SESSION_COOKIE_SECURE=1
DJANGO_CSRF_COOKIE_SECURE=1
DJANGO_SECURE_HSTS_SECONDS=31536000
DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS=1
DJANGO_SECURE_HSTS_PRELOAD=1
WEB_CONCURRENCY   GUNICORN_TIMEOUT
```

Optional for object storage: `AWS_STORAGE_BUCKET_NAME`, `AWS_ACCESS_KEY_ID`,
`AWS_SECRET_ACCESS_KEY`, `AWS_S3_REGION_NAME`, `AWS_S3_ENDPOINT_URL`,
`AWS_S3_CUSTOM_DOMAIN`, `AWS_QUERYSTRING_AUTH`.

**Order matters:** leave the six `DJANGO_SECURE_*` values off until the
certificate is installed, otherwise the site 301-redirects to HTTPS and the
certificate request has nothing to talk to. `.env.example` documents this.

---

## 5. Nginx plan

File: `deploy/nginx/makongatiarg.co.tz.conf`

```bash
sudo cp deploy/nginx/makongatiarg.co.tz.conf /etc/nginx/sites-available/cdms
sudo ln -s /etc/nginx/sites-available/cdms /etc/nginx/sites-enabled/cdms
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
```

Adjust `alias` paths if the app is not at `/srv/cdms`:

| Block | Purpose |
|---|---|
| `:80` | serves `/.well-known/acme-challenge/`, 301s everything else to HTTPS |
| `:443` | TLS, security headers, rate limits, static, media, proxy |
| `/static/` | `alias` to `staticfiles/`, 30-day cache, served by nginx |
| `/media/` | `alias` to `media/`, private cache, only for local disk |
| `/accounts/login/` | strict rate limit (10 r/min, burst 5) |
| `/` | proxy to gunicorn, sets `Host`, `X-Real-IP`, `X-Forwarded-For`, `X-Forwarded-Proto` |
| `client_max_body_size 50M` | matches Django's upload limit; raise in **both** if you hit 413 |

`proxy_params` is included for the login blocks, but the general `/` block sets
its headers explicitly so nothing depends on the distro's version of that file.

**Media:** with `AWS_STORAGE_BUCKET_NAME` set, Django returns bucket URLs and
the `/media/` block is never used. Without it, `/media/` must point at a
**persistent** volume — a normal VPS disk, not a container's ephemeral layer.

---

## 6. Gunicorn plan

Config: `deploy/gunicorn_config.py` · Unit: `deploy/systemd/cdms.service`

```bash
sudo cp deploy/systemd/cdms.service /etc/systemd/system/cdms.service
sudo systemctl daemon-reload
sudo systemctl enable --now cdms
sudo systemctl status cdms
```

| Setting | Value | Why |
|---|---|---|
| `bind` | `unix:/run/cdms/gunicorn.sock` | Unix socket, no port exposed |
| `workers` | `WEB_CONCURRENCY`, default `min(2×CPU+1, 5)` | small VPS friendly |
| `timeout` | 120s | matches nginx `proxy_read_timeout` |
| `max_requests` | 1000 (+100 jitter) | recycles workers, limits memory growth |
| `accesslog` / `errorlog` | `-` | systemd journal, `journalctl -u cdms` |
| user | `cdms` (dedicated, unprivileged) | never root |
| hardening | `NoNewPrivileges`, `PrivateTmp`, `ProtectSystem=full` | reduces blast radius |

The unit sets only `DJANGO_SETTINGS_MODULE`; every value Django needs comes
from `EnvironmentFile=/etc/cdms/cdms.env`.

---

## 7. SSL plan (Let's Encrypt)

Not issued — the VPS is not deployed and DNS does not point at it yet.

**1. DNS first.** Both names must resolve to the VPS or validation fails.

**2. Install certbot.**

```bash
sudo apt update && sudo apt install -y certbot python3-certbot-nginx
```

**3. Issue** (before turning on the `DJANGO_SECURE_*` flags):

```bash
sudo certbot --nginx \
  -d makongatiarg.co.tz \
  -d www.makongatiarg.co.tz \
  --redirect --agree-tos -m <your-email> --no-eff-email
```

Both names in one certificate. Keep the `:80` ACME location in the nginx file
or automatic renewal breaks.

**4. Verify auto-renewal:**

```bash
sudo certbot renew --dry-run
sudo systemctl status certbot.timer
```

**5. Only then** set the `DJANGO_SECURE_*` variables in `/etc/cdms/cdms.env`
and restart the service.

**6. Confirm:**

```bash
curl -I https://makongatiarg.co.tz
curl -sI -o /dev/null -w '%{http_code}\n' https://www.makongatiarg.co.tz
openssl s_client -connect makongatiarg.co.tz:443 -servername makongatiarg.co.tz </dev/null
```

Check `https://www.ssllabs.com/ssltest/` later, not before.

### Rollback

If something breaks, set the six `DJANGO_SECURE_*` values to `0` (and
`DJANGO_SECURE_HSTS_SECONDS=0`) in `/etc/cdms/cdms.env`, then
`sudo systemctl restart cdms`. HSTS is the one setting browsers cache: expect
up to 24 hours before a visitor can reach plain HTTP again.

---

## 8. Final deployment sequence

Two prepared scripts do the work, so nothing is ever copied by hand. **Neither
has been executed** — they are prepared for the day the VPS exists.

### 8.1 First time only — `deploy/bootstrap.sh`

```bash
git clone https://github.com/simonntalila-bot/hopstal-management-systems-.git
cd hopstal-management-systems-
sudo bash deploy/bootstrap.sh
```

Installs nginx, MySQL, Python, certbot; creates the `cdms` account; clones the
repository from Git into `/srv/cdms`; builds the virtualenv; installs
requirements; creates `/etc/cdms/cdms.env` from `.env.example` at mode 600;
activates the pre-commit guard; runs `collectstatic`.

It deliberately **does not** run `migrate` — the database and its credentials
must exist first. It prints the remaining manual steps when it finishes.

### 8.2 Every release after that — `deploy/deploy.sh`

```bash
sudo bash /srv/cdms/deploy/deploy.sh
```

`git fetch` + `reset --hard origin/main` → install requirements → `check` →
`check --deploy` → `migrate --noinput` → `collectstatic` → fix ownership →
restart systemd → `nginx -t` → reload → health check. It refuses to run if the
env file still contains `<placeholder>` values, and prints the commit it
deployed so a rollback target is always known.

### 8.3 Manual steps that stay manual

| # | Step | Command |
|---|---|---|
| 1 | Create database + least-privilege user | `sudo mysql` then `CREATE DATABASE` / `CREATE USER` / `GRANT` |
| 2 | Fill in the env file | `sudo nano /etc/cdms/cdms.env` (mode 600) |
| 3 | Rotate the compromised MySQL password | `ALTER USER ... IDENTIFIED BY '<new>'` |
| 4 | Revoke the old Gmail App Password | Google account security page |
| 5 | Install systemd unit | `sudo cp deploy/systemd/cdms.service /etc/systemd/system/` |
| 6 | Install nginx site | `sudo cp deploy/nginx/makongatiarg.co.tz.conf /etc/nginx/sites-available/cdms` |
| 7 | **Validate nginx — VPS only** | `sudo nginx -t` |
| 8 | Migrate | `./venv/bin/python manage.py migrate --noinput` |
| 9 | Start the app | `sudo systemctl enable --now cdms` |
| 10 | DNS `A` + `CNAME` | registrar |
| 11 | Issue the certificate | `sudo certbot --nginx -d makongatiarg.co.tz -d www.makongatiarg.co.tz --redirect ...` |
| 12 | Enable `DJANGO_SECURE_*`, restart | `sudo systemctl restart cdms` |
| 13 | Verify + upload test files | log in over HTTPS |

### 8.4 Ordering that matters

1. DNS must resolve before certbot can validate
2. `migrate` **before** nginx serves traffic
3. `collectstatic` **before** the `/static/` location is used
4. certbot **while** `DJANGO_SECURE_SSL_REDIRECT=0`, otherwise the redirect
   points at an endpoint with no certificate
5. `DJANGO_SECURE_*` only after the certificate is live

---

## 9. Files in this repository

| File | Purpose |
|---|---|
| `.env.example` | all variable NAMES with the domain, values as placeholders |
| `deploy/nginx/makongatiarg.co.tz.conf` | nginx site config |
| `deploy/gunicorn_config.py` | gunicorn config |
| `deploy/systemd/cdms.service` | systemd unit |
| `deploy/bootstrap.sh` | one-time VPS preparation (idempotent, no secrets) |
| `deploy/deploy.sh` | per-release deploy from Git (refuses placeholder env) |
| `docs/DEPLOYMENT.md` | this document |
| `docs/MEDIA_STORAGE.md` | S3 storage variables |
| `docs/DATABASE_BACKUP.md` | backup strategy and scripts |
| `scripts/backup_mysql.sh` | encrypted scheduled backup |
| `scripts/restore_mysql.sh` | restore drill into a scratch database |
| `hms_project/tests.py` | automated checks for host, CSRF and storage settings |

## Open items

- [ ] VPS public IP → then the exact DNS records above
- [ ] Does the VPS have IPv6? (decides `AAAA`)
- [ ] MySQL password rotation
- [ ] Gmail app-password revocation
- [ ] Run `migrate` against the real database
- [x] ~~Decide S3 bucket or persistent disk~~ — **S3-compatible object storage
      chosen**; see `docs/MEDIA_STORAGE.md`
- [x] ~~Confirm the backup retention period~~ — baseline agreed: daily 30 /
      weekly 12 / monthly 12; see `docs/DATABASE_BACKUP.md` §3
- [x] ~~`User.is_reception()` role mismatch~~ — fixed; the helper checked
      `RECEPTION_PHARMACY`, retired by migration `0003`
- [x] ~~`dashboard/home.html` checks the retired `RECEPTIONIST`~~ — fixed
- [ ] Decide what the stale `NURSE` / `PHARMACIST` branches in
      `dashboard/home.html` should map to (see below)
- [ ] Hospital sign-off: is 12 months of backup history enough, or does the
      clinical regime require longer?

## Role-mapping decisions still open

**1. `User.is_reception()` returns `True` for `ADMIN`, not `False`.**
Every other `is_*()` helper, `reception_required()`,
`dashboard/views.py:1277` and `patients/views.py:137` all treat `ADMIN` as
passing. Returning `False` for `ADMIN` would make this one helper disagree
with the decorators that actually guard the views — the same class of bug the
`RECEPTION_PHARMACY` fix removed. `accounts/tests.py::ReceptionRoleTests`
enforces the agreement in both directions. Changing this needs a decision, not
a one-line edit, because it would also mean revisiting the decorators.

**2. `dashboard/home.html` has two more dead branches: `NURSE` and
`PHARMACIST`.** Both were removed from `ROLE_CHOICES` in migration `0002`
(`PHARMACIST` → `PHARMACY`; there is no Nurse role at all, vitals are handled
by Reception). They are recorded in
`accounts.tests.DashboardTemplateRoleTests.KNOWN_LEGACY_ROLES` rather than
renamed, because the mapping is a product decision: `PHARMACIST` → `PHARMACY`
is mechanical, but `NURSE` has no obvious successor among the current roles.

Context worth knowing before deciding: `dashboard.views.home()` already
redirects every role in its `ROLE_HOME` map to a dedicated `*-home` template,
so `home.html` only renders for a user whose role is unset or unmapped. The
live dashboards are `dashboard/reception_home.html` and friends. These stale
branches in `home.html` are therefore invisible in production regardless —
fixing them changes nothing a user sees. `DashboardTemplateRoleTests` will
fail if a *new* unknown role ever appears, so the drift cannot spread.
