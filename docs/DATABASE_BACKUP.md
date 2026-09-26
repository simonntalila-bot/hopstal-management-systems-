# Database Backup & Restore — Argentina Dispensary CDMS

The database holds **patient records**. Losing it is worse than any other
failure this system can have, so backups are part of going live, not an
afterthought.

Nothing in this folder or in `scripts/` contains a password. Every credential
is read from the environment or from a config file that lives **outside** the
Git repository.

---

## 1. Daily backup

`scripts/backup_mysql.sh` produces a single encrypted dump named
`cdms-<database>-<UTC timestamp>.sql.gz`.

Run it once a day from cron:

```cron
15 2 * * * . /etc/cdms/backup.env && /opt/cdms/scripts/backup_mysql.sh >> /var/log/cdms-backup.log 2>&1
```

What the script guarantees:

| Property | How |
|---|---|
| Consistent snapshot, no downtime | `mysqldump --single-transaction` |
| Includes stored procedures / triggers | `--routines --triggers --events` |
| Encrypted at rest | `openssl enc -aes-256-cbc -pbkdf2 -iter 600000` |
| No readable plaintext left behind | raw dump is deleted after encryption |
| Password never on the command line | `--defaults-extra-file` |
| Permissions locked down | `chmod 600` on dumps, `700` on the directory |
| Old dumps cleaned up | `BACKUP_RETENTION_DAYS` (default 30) |

A remote host additionally needs a managed database with point-in-time
recovery; a cron dump alone is not a substitute.

---

## 2. Offsite storage

A backup on the same disk as the database is not a backup. Every dump must be
copied off the host, to a different provider, within the same day.

Recommended: an S3-compatible bucket with versioning and object lock.

```bash
# example upload, run from the host or a CI job
aws s3 cp "$BACKUP_DIR" "s3://YOUR-BACKUP-BUCKET/cdms/" \
  --storage-class STANDARD_IA \
  --exclude "*" --include "cdms-*.sql.gz" \
  --sse AES256
```

Set up a lifecycle rule on the bucket for long-term retention (e.g. keep 30
daily, 12 monthly, then glacier storage class). The bucket holding patient
data should have public access blocked and MFA-delete enabled.

If the hospital later moves to a managed MySQL service, keep the offsite copy
in addition to the provider's own backups.

---

## 3. Retention

**Agreed baseline policy:**

| Tier | Keep | Enforced by | Approx. size |
|---|---|---|---|
| Daily | 30 days | bucket lifecycle | 30 dumps |
| Weekly | 12 weeks | bucket lifecycle | 12 dumps |
| Monthly | 12 months | bucket lifecycle | 12 dumps |

This is a production baseline and can be changed to match storage cost and the
hospital's requirements. It is a **technical** recovery policy, not a legal one:
some clinical-record regimes require longer than 12 months. Confirm the legal
figure with the hospital before the first production backup — that is a
separate decision from this baseline.

### Where each tier is enforced

`scripts/backup_mysql.sh` prunes only the **local** window
(`BACKUP_RETENTION_DAYS`, default 30 days). It deliberately does not keep 12
months on the VPS: that disk cannot hold it, and a replaced or lost VPS must not
mean lost history. The weekly and monthly tiers are the offsite bucket's job.

Preview the local prune before letting cron apply it:

```bash
BACKUP_DRY_RUN=1 scripts/backup_mysql.sh     # lists, deletes nothing
```

The script refuses to prune at all if no file matches its own naming pattern, so
a mistyped `BACKUP_DIR` cannot delete unrelated files.

### Bucket lifecycle rule for the 30 / 12 / 12 tiers

The daily backup uploads one object per run. The bucket lifecycle rotates the
tiers automatically: objects are deleted at 30 days, moved to infrequent access
at 30 days and kept until 365, giving the daily, weekly-equivalent and
monthly-equivalent history without a second cron job.

```json
{
  "Rules": [
    {
      "ID": "cdms-30-12-12",
      "Status": "Enabled",
      "Filter": { "Prefix": "" },
      "Transitions": [
        { "Days": 30, "StorageClass": "STANDARD_IA" }
      ],
      "Expiration": { "Days": 365 }
    }
  ]
}
```

Tune `Days` on the transition and expiration to change the policy in one place.
Check the provider's naming for the infrequent-access class; non-AWS
S3-compatible providers use different storage-class strings.

---

## 4. Restore testing

An untested backup is a guess. Test the restore **monthly**, into a scratch
database, never into production.

```bash
export RESTORE_DATABASE=restore_test_2026_09
export RESTORE_FROM=/path/to/cdms-hms_db-20260901T020000Z.sql.gz
scripts/restore_mysql.sh
```

`restore_mysql.sh` refuses to run against a name containing `hms_db`, `cdms`
or `prod`, and it reports the restored table count so you can see it worked.

To be fully confident, also boot the app against the restored copy and walk
through one patient record end to end:

```bash
DB_NAME=restore_test_2026_09 python manage.py migrate
DB_NAME=restore_test_2026_09 python manage.py check
```

Record the date, the dump filename, the table count and the tester in a
written log. A backup with no recorded successful restore has not been proven.

---

## 5. Protecting the backup credentials

The backup user should be **read-only and separate from the application user**:

```sql
CREATE USER 'cdms_backup'@'YOUR_HOST';
GRANT SELECT, SHOW VIEW, TRIGGER, EVENT, LOCK TABLES
  ON hms_db.* TO 'cdms_backup'@'YOUR_HOST';
-- no INSERT, UPDATE, DELETE, DROP or ALTER
```

Keep three secrets outside Git, each in its own `chmod 600` file:

| Secret | File | Purpose |
|---|---|---|
| Backup user password | e.g. `/root/.my.cnf.backup` | Referenced by `MYSQL_CNF` |
| Dump encryption passphrase | e.g. `/root/.backup-passphrase` | Referenced by `BACKUP_ENCRYPT_PASSPHRASE_FILE` |
| Offsite bucket credentials | host secret store or IAM role | Used by the upload step |

`/etc/cdms/backup.env` holds the variable **names** and non-secret values only,
and is `chmod 600`. All of these paths are covered by `.gitignore`.

Rotate the dump encryption passphrase if anyone with access to the host leaves
the organisation. Rotate the backup password on the same schedule as the
database password.

---

## Before go-live checklist

- [ ] Automated daily backup running and a first dump verified
- [ ] `BACKUP_DRY_RUN=1` reviewed before cron prune is enabled
- [ ] Dump opens and restores into a scratch database
- [ ] Offsite bucket receiving copies
- [ ] Bucket lifecycle rule applied (30 days / 365 days) per section 3
- [ ] Public access blocked on the bucket
- [ ] Backup user is read-only, not the app user
- [ ] Secrets stored outside the repo, `chmod 600`
- [ ] Restore test scheduled monthly with a written log
- [x] Technical baseline agreed: daily 30 / weekly 12 / monthly 12
- [ ] Hospital sign-off: is 12 months enough, or does the clinical regime
      require longer? (section 3)
