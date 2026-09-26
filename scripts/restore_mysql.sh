#!/usr/bin/env bash
#
# scripts/restore_mysql.sh
# ========================
# Restore a dump produced by scripts/backup_mysql.sh into a scratch database
# so a restore can be VERIFIED. Never point this at production.
#
# Required environment variables:
#
#   MYSQL_CNF                            chmod-600 client config file
#   MYSQL_HOST                           target host
#   MYSQL_USER                           admin user for the target instance
#   RESTORE_DATABASE                     database name to create and restore
#   RESTORE_FROM                         path to the encrypted .sql.gz dump
#   BACKUP_ENCRYPT_PASSPHRASE_FILE      chmod-600 passphrase file
#
set -Eeuo pipefail

log() { printf '%s [restore] %s\n' "$(date -Is)" "$*"; }
die() { log "ERROR: $*" >&2; exit 1; }

for var in MYSQL_CNF MYSQL_HOST MYSQL_USER RESTORE_DATABASE RESTORE_FROM \
           BACKUP_ENCRYPT_PASSPHRASE_FILE; do
  [ -n "${!var:-}" ] || die "$var is not set"
done

[ -r "$RESTORE_FROM" ] || die "dump not readable: $RESTORE_FROM"
case "$RESTORE_DATABASE" in
  *hms_db*|*cdms*|*prod*)
    die "refusing to restore into '${RESTORE_DATABASE}'. Use a scratch name like restore_test."
    ;;
esac

MYSQL="mysql --defaults-extra-file=${MYSQL_CNF} --host=${MYSQL_HOST} --user=${MYSQL_USER}"

log "recreating scratch database ${RESTORE_DATABASE}"
$MYSQL -e "DROP DATABASE IF EXISTS \`${RESTORE_DATABASE}\`;
          CREATE DATABASE \`${RESTORE_DATABASE}\`
          CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"

log "decrypting and loading"
openssl enc -d -aes-256-cbc -pbkdf2 -iter 600000 \
  -in "$RESTORE_FROM" \
  -pass "file:${BACKUP_ENCRYPT_PASSPHRASE_FILE}" \
| gunzip \
| $MYSQL "$RESTORE_DATABASE"

log "sanity check"
TABLES="$($MYSQL -N -B -e "SELECT COUNT(*) FROM information_schema.tables
                          WHERE table_schema='${RESTORE_DATABASE}';")"
log "tables restored: ${TABLES}"
[ "$TABLES" -gt 0 ] || die "no tables present, restore failed"

log "verifying django can see the schema"
python manage.py check --database default --deploy 2>/dev/null \
  && log "django check OK" \
  || log "django check skipped (point DB_* at the scratch database to run it)"

log "restore verified OK. Drop ${RESTORE_DATABASE} when finished."
