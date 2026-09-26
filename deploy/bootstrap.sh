#!/usr/bin/env bash
#
# deploy/bootstrap.sh
# ===================
# ONE-TIME VPS preparation for the Argentina Dispensary CDMS.
# Installs everything, clones the repository from Git, and stops before
# anything is exposed to the internet.
#
#   sudo bash deploy/bootstrap.sh
#
# This script has NOT been run anywhere. It is prepared for the day the VPS
# is purchased. It contains no secrets: the environment file it creates is
# filled in by hand afterwards.
#
# Safe to re-run: every step is idempotent.
#
set -Eeuo pipefail

REPO_URL="${REPO_URL:-https://github.com/simonntalila-bot/hopstal-management-systems-.git}"
BRANCH="${BRANCH:-main}"
APP_DIR="${APP_DIR:-/srv/cdms}"
APP_USER="${APP_USER:-cdms}"
ENV_FILE="${ENV_FILE:-/etc/cdms/cdms.env}"
PYTHON_BIN="${PYTHON_BIN:-python3}"

log()  { printf '\n\033[1;34m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33mwarn:\033[0m %s\n' "$*"; }
die()  { printf '\033[1;31merror:\033[0m %s\n' "$*" >&2; exit 1; }

[ "$(id -u)" -eq 0 ] || die "run with sudo"
log "1/9  System packages"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq \
  nginx mysql-server python3-venv python3-pip \
  certbot python3-certbot-nginx git rsync curl

log "2/9  Service account and directories"
if ! id -u "$APP_USER" >/dev/null 2>&1; then
  adduser --system --group --home "$APP_DIR" --shell /usr/sbin/nologin "$APP_USER"
fi
mkdir -p "$APP_DIR" "$APP_DIR/media" "$APP_DIR/staticfiles" /etc/cdms
chown -R "$APP_USER:$APP_USER" "$APP_DIR"
chmod 755 "$APP_DIR"

log "3/9  Repository from Git (not manual file copying)"
if [ -d "$APP_DIR/.git" ]; then
  warn "$APP_DIR is already a clone; leaving it alone"
else
  # Clone into a temp dir, then move contents so the target is not a subdir.
  tmp=$(mktemp -d)
  git clone --branch "$BRANCH" --single-branch "$REPO_URL" "$tmp/repo"
  cp -a "$tmp/repo/." "$APP_DIR/"
  rm -rf "$tmp"
fi
chown -R "$APP_USER:$APP_USER" "$APP_DIR"

log "4/9  Python virtual environment"
sudo -u "$APP_USER" python3 -m venv "$APP_DIR/venv"
"$APP_DIR/venv/bin/pip" install --quiet --upgrade pip setuptools wheel
"$APP_DIR/venv/bin/pip" install --quiet -r "$APP_DIR/requirements.txt"

log "5/9  Environment file (secrets stay out of Git)"
if [ ! -f "$ENV_FILE" ]; then
  install -m 600 /dev/null "$ENV_FILE"
  cp "$APP_DIR/.env.example" "$ENV_FILE"
  chmod 600 "$ENV_FILE"
  chown root:"$APP_USER" "$ENV_FILE"
  warn "created $ENV_FILE from .env.example"
  warn "EDIT IT NOW and replace every <placeholder>. Do not commit it."
else
  warn "$ENV_FILE already exists; not overwriting"
fi

log "6/9  Git guard in this clone"
sudo -u "$APP_USER" git -C "$APP_DIR" config core.hooksPath .githooks
sudo -u "$APP_USER" git -C "$APP_DIR" config user.name "cdms-deploy"
sudo -u "$APP_USER" git -C "$APP_DIR" config user.email "deploy@makongatiarg.co.tz"

log "7/9  Static files"
set -a; . "$ENV_FILE"; set +a
sudo -u "$APP_USER" "$APP_DIR/venv/bin/python" "$APP_DIR/manage.py" collectstatic --noinput

log "8/9  MySQL is present but the schema is NOT migrated yet"
warn "Deliberately not running migrate: the database and its credentials"
warn "must be created first. See the manual checklist in the handover notes."

log "9/9  Done - nothing is exposed yet"
cat <<'NEXT'

  Remaining manual steps (in this order):

    1. Create the database and a least-privilege user:
         sudo mysql
         CREATE DATABASE argentina CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
         CREATE USER 'argentina_user'@'localhost' IDENTIFIED BY '<your password>';
         GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, ALTER, INDEX,
               REFERENCES ON argentina.* TO 'argentina_user'@'localhost';
         FLUSH PRIVILEGES;

    2. Fill in $ENV_FILE with real values (chmod 600, never commit):
         sudo nano $ENV_FILE

    3. Rotate the compromised MySQL password and revoke the old Gmail
       App Password before going live.

    4. Install the service and web server configs:
         sudo cp $APP_DIR/deploy/systemd/cdms.service /etc/systemd/system/
         sudo cp $APP_DIR/deploy/nginx/makongatiarg.co.tz.conf \
                 /etc/nginx/sites-available/cdms
         sudo ln -s /etc/nginx/sites-available/cdms /etc/nginx/sites-enabled/cdms
         sudo rm -f /etc/nginx/sites-enabled/default

    5. Verify nginx syntax on THIS server (cannot be checked on Windows):
         sudo nginx -t

    6. Migrate and start:
         cd $APP_DIR
         set -a; . $ENV_FILE; set +a
         ./venv/bin/python manage.py migrate --noinput
         sudo systemctl daemon-reload
         sudo systemctl enable --now cdms
         sudo systemctl reload nginx

    7. Add DNS A + CNAME records, then issue the certificate:
         sudo certbot --nginx -d makongatiarg.co.tz -d www.makongatiarg.co.tz \
              --redirect --agree-tos -m <your email> --no-eff-email

    8. Only then set the DJANGO_SECURE_* values in $ENV_FILE and restart:
         sudo systemctl restart cdms

NEXT
