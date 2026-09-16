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
credentials, database-backed login sessions, and human/system account types.
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

## Tests

```bash
database/tests/run.sh
```

The test runner always creates a fresh disposable PostgreSQL container, builds
and tests its databases, and removes the container on success, failure, or
interruption. It never points tests at the standalone development database.
