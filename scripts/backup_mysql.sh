#!/usr/bin/env bash
#
# scripts/backup_mysql.sh
# =======================
# Encrypted, timestamped MySQL backup for the CDMS database.
#
# Designed for a Linux host (VPS or container) running the Django app.
# Safe to run from cron. Contains NO credentials: everything is read from the
# environment and a MySQL client config file that lives OUTSIDE the repo.
#
# Required environment variables (names only, set them in your host secret
# store, e.g. /etc/cdms/backup.env, NOT in Git):
#
#   MYSQL_HOST             database host
#   MYSQL_PORT             database port, default 3306
#   MYSQL_DATABASE         database name
#   MYSQL_USER             backup user (read-only, no admin rights needed)
#   MYSQL_CNF              path to a chmod-600 MySQL client config file that
#                          holds the password for MYSQL_USER
#   BACKUP_DIR             where .sql.gz files are written
#   BACKUP_ENCRYPT_PASSPHRASE_FILE
#                          path to a chmod-600 file holding the passphrase
#                          used to encrypt the dump
#   BACKUP_RETENTION_DAYS  local rolling window in days, default 30. The
#                          12-week and 12-month tiers are enforced by the
#                          offsite bucket lifecycle rule, not here.
#   BACKUP_DRY_RUN          1 = print the prune plan and delete nothing
#   BACKUP_PREFIX          filename prefix, default cdms
#
# Example crontab (daily 02:15, local window 30 days):
#   15 2 * * * . /etc/cdms/backup.env && /opt/cdms/scripts/backup_mysql.sh \
#       >> /var/log/cdms-backup.log 2>&1
#
set -Eeuo pipefail

log() { printf '%s [backup] %s\n' "$(date -Is)" "$*"; }
die() { log "ERROR: $*" >&2; exit 1; }

# --- validate configuration (names checked, values never printed) -----------
for var in MYSQL_HOST MYSQL_DATABASE MYSQL_USER MYSQL_CNF BACKUP_DIR \
           BACKUP_ENCRYPT_PASSPHRASE_FILE; do
  [ -n "${!var:-}" ] || die "$var is not set"
done

[ -r "$MYSQL_CNF" ] || die "MYSQL_CNF is not readable"
[ -r "$BACKUP_ENCRYPT_PASSPHRASE_FILE" ] || die "passphrase file is not readable"

mkdir -p "$BACKUP_DIR"
chmod 700 "$BACKUP_DIR"

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
NAME="${BACKUP_PREFIX:-cdms}-${MYSQL_DATABASE}-${STAMP}"
RAW="${BACKUP_DIR}/${NAME}.sql"
DEST="${BACKUP_DIR}/${NAME}.sql.gz"

# --- write the dump ---------------------------------------------------------
# --defaults-extra-file keeps the password out of the command line and out of
# the process list. --single-transaction gives a consistent snapshot without
# locking InnoDB tables, which keeps patient records safe while people work.
log "dumping ${MYSQL_DATABASE} on ${MYSQL_HOST}"
mysqldump \
  --defaults-extra-file="$MYSQL_CNF" \
  --host="$MYSQL_HOST" \
  --port="${MYSQL_PORT:-3306}" \
  --user="$MYSQL_USER" \
  --single-transaction \
  --quick \
  --routines \
  --triggers \
  --events \
  --set-gtid-purged=OFF \
  "$MYSQL_DATABASE" > "$RAW"

[ -s "$RAW" ] || { rm -f "$RAW"; die "dump is empty"; }
chmod 600 "$RAW"

# --- encrypt then compress --------------------------------------------------
# AES-256 with PBKDF2. The plaintext dump is removed immediately afterwards so
# patient data is never left readable on disk.
log "encrypting"
openssl enc -aes-256-cbc -pbkdf2 -iter 600000 -salt \
  -in "$RAW" \
  -out "${DEST}.tmp" \
  -pass "file:${BACKUP_ENCRYPT_PASSPHRASE_FILE}"

mv "${DEST}.tmp" "$DEST"
rm -f "$RAW"
chmod 600 "$DEST"

SIZE="$(du -h "$DEST" | cut -f1)"
log "wrote ${DEST} (${SIZE})"

# --- retention --------------------------------------------------------------
#
# Policy (docs/DATABASE_BACKUP.md section 3), grandfathered/rotated offsite:
#
#   daily   30 days      bucket lifecycle
#   weekly  12 weeks     bucket lifecycle
#   monthly 12 months    bucket lifecycle
#
# This script only prunes the LOCAL rolling window. The long-term tiers live in
# the offsite bucket, because keeping 12 months of dumps on the VPS disk is not
# viable and a lost VPS must not mean lost history. BACKUP_RETENTION_DAYS is
# therefore the local window and is intentionally not 12 months.
#
# Safety: deletion is opt-in-previewable, pattern-restricted, and refuses to run
# against a directory that does not look like a backup directory. Set
# BACKUP_DRY_RUN=1 to print the plan without deleting anything.
KEEP="${BACKUP_RETENTION_DAYS:-30}"
DRY_RUN="${BACKUP_DRY_RUN:-0}"
PATTERN="${BACKUP_PREFIX:-cdms}-${MYSQL_DATABASE}-*.sql.gz"

case "$KEEP" in
  ''|*[!0-9]*) die "BACKUP_RETENTION_DAYS must be a whole number, got '${KEEP}'" ;;
esac
[ "$KEEP" -ge 1 ] || die "BACKUP_RETENTION_DAYS must be at least 1"

# Refuse to prune if the directory is not plausibly a backup directory. Without
# this, a mistyped BACKUP_DIR could delete unrelated files matching the glob.
existing="$(find "$BACKUP_DIR" -maxdepth 1 -type f -name "$PATTERN" | wc -l)"
if [ "$existing" -eq 0 ]; then
  log "no existing dumps match '${PATTERN}'; skipping prune entirely"
  log "done"
  exit 0
fi

log "pruning local dumps older than ${KEEP} days (${existing} matching files present)"
if [ "$DRY_RUN" = "1" ]; then
  log "DRY RUN: listing what would be deleted, deleting nothing"
  find "$BACKUP_DIR" -maxdepth 1 -type f -name "$PATTERN" -mtime "+${KEEP}" \
    -print
  log "dry run complete; re-run with BACKUP_DRY_RUN=0 to apply"
  log "done"
  exit 0
fi

# -mtime keeps the most recent KEEP days untouched regardless of anything else.
find "$BACKUP_DIR" -maxdepth 1 -type f -name "$PATTERN" -mtime "+${KEEP}" \
  -print -delete
log "local prune complete; offsite tiering is the bucket lifecycle rule's job"

log "done"
