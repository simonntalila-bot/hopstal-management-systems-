#!/usr/bin/env bash
#
# deploy/deploy.sh
# ================
# Per-release deployment for the Argentina Dispensary CDMS.
# Pulls the release from Git and applies it. Safe to re-run.
#
#   sudo bash deploy/deploy.sh
#
# This script has NOT been run anywhere. No secrets: the environment file
# lives outside the repository and is only read, never written.
#
set -Eeuo pipefail

APP_DIR="${APP_DIR:-/srv/cdms}"
APP_USER="${APP_USER:-cdms}"
ENV_FILE="${ENV_FILE:-/etc/cdms/cdms.env}"
BRANCH="${BRANCH:-main}"
MEDIA_BACKEND_HINT="set AWS_STORAGE_BUCKET_NAME in $ENV_FILE to use object storage"

log()  { printf '\n\033[1;34m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33mwarn:\033[0m %s\n' "$*"; }
die()  { printf '\033[1;31merror:\033[0m %s\n' "$*" >&2; exit 1; }

[ "$(id -u)" -eq 0 ] || die "run with sudo"
[ -d "$APP_DIR/.git" ] || die "$APP_DIR is not a git clone; run deploy/bootstrap.sh first"
[ -f "$ENV_FILE" ] || die "$ENV_FILE not found; run deploy/bootstrap.sh first"

# Refuse to run against a half-filled environment file: migrations against a
# broken config are worse than not migrating at all.
if grep -q '<[^>]*>' "$ENV_FILE"; then
  die "$ENV_FILE still contains <placeholder> values. Fill it in first."
fi

log "Loading environment (values are not printed)"
set -a; . "$ENV_FILE"; set +a
[ -n "${DJANGO_SECRET_KEY:-}" ] || die "DJANGO_SECRET_KEY is empty"
[ "${DJANGO_DEBUG:-1}" = "0" ] || warn "DJANGO_DEBUG is not 0"
command -v "$APP_DIR/venv/bin/python" >/dev/null || die "virtualenv missing at $APP_DIR/venv"

log "Stopping the app before the code changes underneath it"
systemctl stop cdms || true

log "Pulling $BRANCH from Git"
sudo -u "$APP_USER" git -C "$APP_DIR" fetch --quiet origin "$BRANCH"
sudo -u "$APP_USER" git -C "$APP_DIR" reset --hard "origin/$BRANCH"
git_rev=$(sudo -u "$APP_USER" git -C "$APP_DIR" rev-parse --short HEAD)
log "deployed commit $git_rev"

log "Installing dependencies"
"$APP_DIR/venv/bin/pip" install --quiet --upgrade pip
"$APP_DIR/venv/bin/pip" install --quiet -r "$APP_DIR/requirements.txt"

log "Sanity check before touching the database"
sudo -u "$APP_USER" "$APP_DIR/venv/bin/python" "$APP_DIR/manage.py" check
if ! sudo -u "$APP_USER" "$APP_DIR/venv/bin/python" "$APP_DIR/manage.py" check --deploy; then
  warn "check --deploy reported issues above; continuing is a judgement call"
fi

log "Applying migrations"
sudo -u "$APP_USER" "$APP_DIR/venv/bin/python" "$APP_DIR/manage.py" migrate --noinput

log "Collecting static files"
sudo -u "$APP_USER" "$APP_DIR/venv/bin/python" "$APP_DIR/manage.py" collectstatic --noinput

log "Fixing ownership on writable paths"
chown -R "$APP_USER:$APP_USER" "$APP_DIR/media" "$APP_DIR/staticfiles"
chmod 600 "$ENV_FILE"

log "Starting the app"
systemctl daemon-reload
systemctl enable --now cdms
systemctl restart cdms
sleep 3
systemctl --no-pager --lines=15 status cdms || true

log "Checking nginx configuration on this server"
nginx -t
systemctl reload nginx || warn "nginx reload failed; run 'sudo nginx -t'"

log "Health check"
if curl -fsS -o /dev/null -w '  http://127.0.0.1 -> %{http_code}\n' \
     --resolve makongatiarg.co.tz:80:127.0.0.1 http://makongatiarg.co.tz/; then
  log "responding"
else
  warn "no HTTP response yet; check: journalctl -u cdms -n 50 --no-pager"
fi

cat <<EOF

  Release $git_rev applied.

  Post-release manual checks:
    - log in at https://makongatiarg.co.tz/
    - upload a patient document, a QR code and an ultrasound image
    - confirm the files are reachable (S3: $MEDIA_BACKEND_HINT)
    - confirm today's database backup ran: scripts/backup_mysql.sh

  To roll back to a previous release:
    sudo -u $APP_USER git -C $APP_DIR reset --hard <commit>
    then re-run this script.

EOF
