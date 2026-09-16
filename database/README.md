# ERMS database setup

## New database

Execute exactly one file:

```bash
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f database/schema.sql
```

`schema.sql` is the canonical bootstrap entry point and physically contains the
complete current schema. It uses standard SQL and does not depend on `psql`
include commands or separate migration files. Do not execute individual
migration files when initializing a new database.

The schema deliberately contains no shared default password. Once the empty
schema has been loaded, create its one-time bootstrap administrator with:

```bash
backend/services/api/.venv/bin/python -m backend.services.api.manage_auth \
  bootstrap \
  --name "Bootstrap Administrator" \
  --email bootstrap@erms.local
```

The command generates and displays a unique 24-hour temporary password and
forces it to be changed at first login. It refuses to run in a database that
already contains users. See [`../docs/authentication.md`](../docs/authentication.md)
for the complete security model, reserved objects, audit behavior, recovery
procedure, and post-bootstrap checklist.

## Existing database

Apply only migrations not already recorded in `schema_migrations`, in filename
order. To add event history and then user management to a database containing
the core records schema:

```bash
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -1 \
  -f database/migrations/001_add_event_history.sql

psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -1 \
  -f database/migrations/002_add_user_management.sql

psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -1 \
  -f database/migrations/003_add_content_storage_and_entity_versions.sql

psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -1 \
  -f database/migrations/004_add_record_drafts.sql

psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -1 \
  -f database/migrations/005_add_authentication.sql

psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -1 \
  -f database/migrations/006_enforce_closed_aggregations.sql

psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -1 \
  -f database/migrations/007_freeze_closed_aggregation_metadata.sql

psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -1 \
  -f database/migrations/008_cascade_record_digital_components.sql

psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -1 \
  -f database/migrations/009_user_management_lifecycle.sql

psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -1 \
  -f database/migrations/010_rename_org_unit_deactivation_date.sql

psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -1 \
  -f database/migrations/011_normalize_org_unit_event_history.sql

psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -1 \
  -f database/migrations/012_backfill_anonymous_event_actor.sql

psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -1 \
  -f database/migrations/013_snapshot_event_actor_identity.sql

psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -1 \
  -f database/migrations/014_backfill_webui_event_source.sql

psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -1 \
  -f database/migrations/015_reclassify_lifecycle_normalization_events.sql

psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -1 \
  -f database/migrations/016_snapshot_role_assignment_parties.sql

psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -1 \
  -f database/migrations/017_rename_system_accounts_to_service.sql

psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -1 \
  -f database/migrations/018_rename_system_actor_to_automated_process.sql
```

The `-1` option wraps the migration in one transaction. Migration 001 is safe
to apply to the current development database where the event-history objects
were initially installed before migration tracking was introduced; it preserves
existing events and records the migration version. Migration 002 adds users,
organizational units, roles, temporal role assignments, hierarchy safeguards,
searchable indexes, and event-history triggers.
Migration 003 adds PostgreSQL-backed digital-component content storage and
database-managed optimistic-concurrency versions for all mutable entities.
Migration 004 adds transactional record drafts. Migration 005 adds local
credentials, database-backed login sessions, and the original human/system
account types.
Migration 006 enforces direct and inherited aggregation closure throughout the
hierarchy, record, component, and blob layers. The complete business rules are
documented in [`../docs/aggregation-closure.md`](../docs/aggregation-closure.md).
Migration 007 freezes the aggregation metadata itself and permits only clearing
a directly closed aggregation's closure date.
Migration 008 makes digital components lifecycle-dependent on their record:
deleting a record atomically cascades to its component metadata and stored
content.
Migration 009 enforces user, role, and organizational-unit lifecycle state,
inherited organizational effectiveness, assignment eligibility, and the
status/timestamp invariants described in the user-management documentation.
Migration 010 renames the organizational-unit lifecycle timestamp from
`date_closed` to the consistent `date_deactivated` without changing its data.
Migration 011 performs the corresponding one-time terminology normalization in
existing `org_unit` audit payloads and restores the audit immutability trigger
within the same transaction.
Migration 012 retrospectively attributes legacy anonymous events to the agreed
administrator account. It records the basis and migration identifier in each
affected event's metadata and restores the audit immutability trigger within
the same transaction.
Migration 013 stores an immutable name and email snapshot alongside every
application-user actor and backfills those snapshots on existing events.
Migration 014 corrects legacy `api` source values to `web_ui` for the known
NiceGUI-only development period, records that basis in event metadata, and
leaves direct database events unchanged.
Migration 015 reclassifies the no-op lifecycle-normalization events generated
by migration 009 from `database` to `migration`, without changing genuine
direct-database provisioning events.
Migration 016 stores durable user and role identity snapshots on role-assignment
events and backfills existing events, so the audit trail does not depend on
opaque IDs or mutable current rows.
Migration 017 renames the non-interactive user account type from `system` to
`service`.
Migration 018 separately renames audit actor type `system` to the clearer
`automated_process`, backfills existing events with migration provenance, and
constrains future event actor types to `user`, `anonymous`, or
`automated_process`.

## Tests

```bash
database/tests/run.sh
```

The test runner always creates a fresh disposable PostgreSQL container, builds
and tests its databases, and removes the container on success, failure, or
interruption. It never points tests at the standalone development database.
