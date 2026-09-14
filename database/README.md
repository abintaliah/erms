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
```

The `-1` option wraps the migration in one transaction. Migration 001 is safe
to apply to the current development database where the event-history objects
were initially installed before migration tracking was introduced; it preserves
existing events and records the migration version. Migration 002 adds users,
organizational units, roles, temporal role assignments, hierarchy safeguards,
searchable indexes, and event-history triggers.

## Tests

```bash
database/tests/run.sh
```

The test runner always creates a fresh disposable PostgreSQL container, builds
and tests its databases, and removes the container on success, failure, or
interruption. It never points tests at the standalone development database.
