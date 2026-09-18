# ERMS Operational Tools Catalogue

**Audience:** DevOps engineers, system administrators, and release engineers  
**Last reviewed:** 18 September 2026

## 1. Purpose

This document is the single catalogue of ERMS command-line tools and background
workers intended for operational use. It identifies what each tool changes, how
it is invoked, whether it runs once or continuously, required safeguards, and
whether it is currently implemented or planned.

Feature documentation may explain why an operation exists, but deployment and
runbook procedures must link back to this catalogue. A new operational command,
scheduled worker, repair utility, or destructive environment tool must be added
here as part of the same change that introduces it.

## 2. Common operating rules

Operational tools run outside FastAPI and must not be started inside every API
worker. They use the same application environment and `DATABASE_URL` as the API
unless their section says otherwise.

Every cleanup worker must:

- support a one-shot invocation suitable for a scheduler;
- support `--dry-run` without committing changes;
- process bounded batches;
- use a dedicated PostgreSQL advisory lock so overlapping invocations are safe;
- be idempotent when re-run;
- identify itself in audit context as an `automated_process`;
- use `scheduled_job` for scheduled execution and an appropriate CLI or
  administrative source for deliberate manual execution;
- print consistently structured result counts;
- exit nonzero on failure; and
- document all configuration and retention settings here.

Only one continuous instance of a given worker is needed per logical database.
An advisory lock is still required because deployments and schedulers can
overlap during restarts.

There are two supported scheduling models:

1. Invoke the one-shot command from a deployment scheduler, Kubernetes CronJob,
   systemd timer, or equivalent. This is preferred when a scheduler is
   available.
2. Run `--watch` as one dedicated supervised process when an external scheduler
   is not available.

Do not run `--watch` from FastAPI startup or once per FastAPI worker.

## 3. Tool summary

| Tool | Status | Default mode | Purpose |
| --- | --- | --- | --- |
| `backend.services.api.content_cleanup` | Implemented | One shot | Remove abandoned uploads, expired drafts, and unreferenced content sets |
| `backend.services.api.session_cleanup` | Implemented | One shot | Audit and remove expired or long-revoked login sessions |
| `backend.services.api.manage_auth` | Implemented | One shot | Bootstrap authentication and perform deliberate credential recovery |
| Database migration commands | Implemented | One shot | Upgrade the schema exactly once per database |
| Database seed commands | Implemented | One shot | Install optional reference, demonstration, or load-test data |
| Pre-production database reset | Planned | One shot, destructive | Recreate a not-yet-operational environment after setup or smoke testing |

## 4. Segmented-content cleanup

**Status:** Implemented
**Module:** `backend.services.api.content_cleanup`

This worker removes expired or failed upload sessions, expired record drafts and
their staged data, and superseded or failed content sets that are not active.

```bash
python -m backend.services.api.content_cleanup --dry-run --batch-size 100
python -m backend.services.api.content_cleanup --batch-size 100
python -m backend.services.api.content_cleanup \
  --watch --batch-size 100 --interval-seconds 3600
```

| Setting | Default | Meaning |
| --- | --- | --- |
| `CONTENT_CLEANUP_INTERVAL_SECONDS` | `3600` | Delay between continuous worker passes |

The worker uses a PostgreSQL advisory lock and records a `CONTENT_CLEANUP`
domain event when committed work occurs. See
[PostgreSQL segmented content storage](content-storage.md).

## 5. Login-session cleanup

**Status:** Implemented
**Module:** `backend.services.api.session_cleanup`

This worker treats `login_sessions` as transient operational security data
while preserving `event_history` as the durable authentication audit trail.

An eligible revoked session is one whose `revoked_at` is older than the
configured retention period. An eligible unrevoked expired session is one whose
first applicable idle or absolute expiry is older than the configured retention
period. Active sessions are never eligible.

Before deleting an expired session, the worker writes a `SESSION_EXPIRED` event
containing the final security-safe session snapshot. Revoked sessions must
already have the required durable revocation audit information; the worker must
verify or supply the required terminal audit event before deleting the row.
Token and CSRF secrets or hashes must never be copied into event history.

Interface:

```bash
python -m backend.services.api.session_cleanup --dry-run --batch-size 500
python -m backend.services.api.session_cleanup --batch-size 500
python -m backend.services.api.session_cleanup \
  --watch --batch-size 500 --interval-seconds 3600
```

| Setting | Initial default | Meaning |
| --- | --- | --- |
| `AUTH_SESSION_RETENTION_DAYS` | `90` | Retention after revocation or effective expiry |
| `AUTH_SESSION_CLEANUP_INTERVAL_SECONDS` | `3600` | Delay between continuous worker passes |
| `AUTH_SESSION_CLEANUP_BATCH_SIZE` | `500` | Default maximum rows processed per pass |

The implementation must use a session-cleanup-specific advisory-lock key. It
must not share the segmented-content cleanup lock because the jobs operate on
independent data and may run concurrently.

The preferred production deployment is an external scheduler running the
one-shot command. `--watch` exists for simple deployments and must run as its
own supervised service, never inside FastAPI.

The normative lifecycle, audit, retention, and cleanup requirements are in
[Authentication and Login-Session Lifecycle](../specs/authentication-and-login-session-lifecycle.md).

## 6. Authentication bootstrap and credential recovery

**Status:** Implemented  
**Module:** `backend.services.api.manage_auth`

Bootstrap is permitted only for a genuinely empty user database:

```bash
python -m backend.services.api.manage_auth bootstrap \
  --name "Bootstrap Administrator" \
  --email bootstrap@erms.local
```

Reset a person account's password:

```bash
python -m backend.services.api.manage_auth reset-password user@example.org
```

Deliberate recovery can assign the reserved administrator role when an existing
organizational unit is explicitly identified:

```bash
python -m backend.services.api.manage_auth reset-password user@example.org \
  --make-system-administrator \
  --org-unit-code ROOT
```

These commands print temporary credentials once. Their output must be handled as
a secret and must not be stored in routine command logs. See
[Authentication](authentication.md).

## 7. Database migrations

**Status:** Implemented

Migrations are release operations, not background jobs. Apply them once per
logical database before application instances using the new schema are started.
Use `ON_ERROR_STOP` and the transaction instructions documented for each
migration.

See [Database setup and migrations](../database/README.md) for the authoritative
commands and ordering. Do not apply migrations automatically from every API
instance.

## 8. Optional database seeds

**Status:** Implemented

Seed scripts install optional reference, demonstration, or load-test data. They
are not migrations and do not run during application startup.

See [ERMS seed data](../database/seeds/README.md). Confirm the target database
and the seed's duplicate-data behavior before execution. Load-test seeds must
not be applied to an operational production repository.

## 9. Pre-production database reset

**Status:** Planned

This deliberately destructive procedure is for an environment that has been
provisioned and smoke-tested but has not entered operational production use. It
will drop and recreate the database from the canonical schema and required
production seeds.

It is not ordinary entity deletion and must not be available through the web
application. Its implementation must:

- require an explicit pre-production environment designation;
- display and require confirmation of the exact database host, port, and name;
- refuse known production environment designations;
- require a separate destructive confirmation flag for non-interactive use;
- recreate required schema and production seeds;
- verify the resulting schema version and bootstrap readiness; and
- produce a clear completion or failure report.

Until the tool is implemented, DevOps must use the database platform's approved
reprovisioning process rather than an ad hoc application command.

## 10. Deployment checklist for scheduled operations

For each deployed logical database:

- choose external one-shot scheduling or one dedicated `--watch` process for
  every required cleanup tool;
- configure the same `DATABASE_URL` and compatible application version used by
  the API;
- prevent secrets and temporary passwords from entering logs;
- monitor nonzero exits and repeated advisory-lock skips;
- retain worker logs according to the operational logging policy;
- test dry-run and one committed batch after deployment;
- verify that cleanup metrics advance and active rows are not selected; and
- update this catalogue whenever a tool, setting, schedule, or runbook changes.
