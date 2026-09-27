# Known issues

Defects found while building the SQLite demo environment. These are in the
application code, not in the demo tooling.

## FIXED: DISCHARGE_BUG - discharging an admitted patient crashed and left bad data

**Status: fixed.** The inpatient statuses are back on the encounter state
machine and the bed bookkeeping is atomic. Kept in this file because the
reasoning matters for anyone touching the state machine, and because the
regression tests that guard it live in `bed_management/tests.py`.

### What used to happen

1. A patient is admitted to a ward bed.
2. Staff try to discharge them.
3. The request raised `ValidationError: Cannot move from ADMITTED to DISCHARGED.`
4. The error was shown to the user, but the database had already been partly
   written and was left self-contradictory.

### Root cause

`encounters` and `bed_management` disagreed about the encounter status
vocabulary. `Admission.save()` wrote `ADMITTED` and `Admission.discharge()`
asked for `DISCHARGED`, but `Encounter.STATUS_CHOICES` and
`Encounter.VALID_TRANSITIONS` defined neither, so:

- admitting wrote a status value that was not a valid choice, and
- `transition_to("DISCHARGED")` always raised, because `ADMITTED` was not even
  a key in `VALID_TRANSITIONS`.

`encounters/migrations/0001_initial.py` did contain `ADMITTED`, `IN_WARD` and
`DISCHARGED`. They were dropped from the model without updating
`bed_management`, which is where the mismatch came from.

### The dangerous part

The bed was genuinely reusable after a failed discharge. The
`one_open_admission_per_bed` constraint did not prevent it, because
`discharge()` stamped `discharged_at` before crashing, so the first admission
was no longer counted as open. A second patient could be admitted to that bed
with no error at all while the first was still recorded as `ADMITTED`.

### The fix

`encounters/models.py`:

- `ADMITTED`, `IN_WARD` and `DISCHARGED` are back in `STATUS_CHOICES`.
- `VALID_TRANSITIONS` covers them: `ADMITTED`/`IN_WARD` reach each other and
  `DISCHARGED`; every pre-admission status can move to `ADMITTED`.
- `COMPLETED` is no longer terminal, because a visit that finished outpatient
  care can still be admitted to a bed. `CANCELLED` stays terminal.
- `closed_at` is set for `DISCHARGED` and cleared for `ADMITTED`/`IN_WARD`, so
  an inpatient stay is never recorded as closed while it is still running.
- `EncounterManager.open()` excludes `DISCHARGED`.
- New `is_inpatient()`, `admit_to_ward()` and `discharge_from_ward()` keep the
  ward transitions in the state machine, so `bed_management` no longer writes
  `status` directly.

`bed_management/models.py`:

- `Admission.save()` and `Admission.discharge()` both run inside
  `transaction.atomic()`. The encounter transition is consulted first, so a
  refused discharge cannot leave the bed marked `AVAILABLE` with
  `discharged_at` stamped.

`encounters/migrations/0007_alter_encounter_status.py` alters `status` for the
restored choices. No data is rewritten: the column is a `CharField` and the
values were already being written.

### Verified

`bed_management/tests.py` covers admit, discharge, bed reuse after discharge,
refused discharge rolling back completely, double discharge, `IN_WARD`, and a
check that no status is stranded unreachable from `REGISTERED`. The demo seeder
now calls the real `Admission.discharge()` instead of writing those fields by
hand, so the path is exercised on every seed.

## Open: no HTTPS hardening in settings

`manage.py check --deploy` reports four warnings that are still unaddressed:

- `security.W004` `SECURE_HSTS_SECONDS` not set
- `security.W008` `SECURE_SSL_REDIRECT` not `True`
- `security.W012` `SESSION_COOKIE_SECURE` not `True`
- `security.W016` `CSRF_COOKIE_SECURE` not `True`

On the cPanel/Passenger path these are expected to be handled at the web
server, but the application cookies are not marked secure on their own. They
are left alone here because turning them on before HTTPS is actually working
would lock staff out of the system. Fix them once the domain serves real
HTTPS, not before.

## Open: four apps have no user interface

`appointments`, `bed_management`, `billing` and `queue_management` have models
and admin pages but no `urls.py`, so nothing in the application links to them.
Their data is real and seeded, but it is only visible in Django admin. This is
pre-existing and out of scope for the demo work, but it means the bed board and
invoices are not reachable through the UI yet.
