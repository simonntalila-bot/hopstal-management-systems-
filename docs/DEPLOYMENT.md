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

Preparation — one time, after the VPS exists:

```bash
sudo apt update && sudo apt install -y nginx mysql-server python3-venv python3-pip certbot python3-certbot-nginx
sudo adduser --system --group --home /srv/cdms cdms
sudo mkdir -p /srv/cdms/media /srv/cdms/staticfiles
sudo chown -R cdms:cdms /srv/cdms
sudo install -m 600 /dev/null /etc/cdms/cdms.env && sudo nano /etc/cdms/cdms.env
```

Release on each deployment:

```bash
cd /srv/cdms
git pull
./venv/bin/pip install -r requirements.txt
sudo install -m 600 /dev/null /etc/cdms/cdms.env   # only on first release
set -a; . /etc/cdms/cdms.env; set +a
./venv/bin/python manage.py migrate --noinput
./venv/bin/python manage.py collectstatic --noinput
sudo chown -R cdms:cdms /srv/cdms/media /srv/cdms/staticfiles
sudo nginx -t && sudo systemctl reload nginx
sudo systemctl restart cdms
```

Smoke test after each release:

```bash
curl -I http://127.0.0.1/health/            # expect 200 or 302
sudo journalctl -u cdms -n 50 --no-pager
```

Order that matters:

1. DNS `A` + `CNAME` → wait until it resolves
2. VPS, MySQL, app, nginx, env file
3. `migrate` **before** nginx goes live
4. `collectstatic` **before** enabling the `/static/` block
5. `certbot` (needs DNS working, needs `DJANGO_SECURE_SSL_REDIRECT=0`)
6. enable the `DJANGO_SECURE_*` flags, restart
7. verify https, then log in and upload a test patient document and QR code

Before step 7, confirm the two security items still outstanding: the rotated
MySQL password and the revoked Gmail app password.

---

## 9. Files in this repository

| File | Purpose |
|---|---|
| `.env.example` | all variable NAMES with the domain, values as placeholders |
| `deploy/nginx/makongatiarg.co.tz.conf` | nginx site config |
| `deploy/gunicorn_config.py` | gunicorn config |
| `deploy/systemd/cdms.service` | systemd unit |
| `docs/DEPLOYMENT.md` | this document |
| `docs/MEDIA_STORAGE.md` | S3 storage variables |
| `docs/DATABASE_BACKUP.md` | backup strategy and scripts |

## Open items

- [ ] VPS public IP → then the exact DNS records above
- [ ] Does the VPS have IPv6? (decides `AAAA`)
- [ ] MySQL password rotation
- [ ] Gmail app-password revocation
- [ ] `User.is_reception()` role mismatch (fails for Reception users)
- [ ] Run `migrate` against the real database
- [ ] Decide: S3 bucket or persistent disk for patient media
