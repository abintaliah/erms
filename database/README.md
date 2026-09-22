# ERMS database setup

## New database

Initialize a new empty database from the canonical schema alone:

```bash
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f database/schema.sql
```

`database/schema.sql` is complete and self-contained. It does not execute or
depend on migrations or seeds. All SQL files contain portable PostgreSQL SQL;
client meta-commands such as `\\i`, `\\ir`, `\\set`, and `\\copy` are prohibited.

## Existing database

Migrations upgrade an existing database containing data. Inspect
`schema_migrations` and apply only missing files from `database/migrations/` in
filename order:

```bash
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 \
  -f database/migrations/001_fix_vital_descendant_scope.sql
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 \
  -f database/migrations/002_govern_review_dates.sql
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 \
  -f database/migrations/003_location_sources_and_governed_history.sql
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 \
  -f database/migrations/004_normalize_user_management_lifecycle.sql
```

Migration 004 makes lifecycle timestamps authoritative. Organization units and
roles are inactive exactly when `date_deactivated` is populated. Users use
`date_deactivated` for deactivation and the separate `date_suspended` timestamp
for temporary suspension. Their `status` columns become generated, read-only
projections so existing API and search contracts remain stable without storing
contradictory mutable state. Suspended legacy users receive migration-time
`date_suspended` values and corresponding immutable migration-provenance events.

Migration files are not initialization scripts and must never be run against a
new database already created from the latest `schema.sql`.

## Seed data

Schema creation, schema migration, and seeding are separate workflows. Apply
optional utilities or SQL from `database/seeds/` only after the database is on
the latest canonical schema. Seeds do not record migration versions and their
event-history source is `seeding`.

The larger XML example file plan is imported transactionally with:

```bash
backend/services/api/.venv/bin/python database/seeds/import_mutamathilah.py \
  --database-url "$DATABASE_URL"
```

## Bootstrap administrator

The schema contains no shared default password. After initializing a genuinely
empty database, provision the one-time bootstrap administrator with:

```bash
backend/services/api/.venv/bin/python -m backend.services.api.manage_auth \
  bootstrap \
  --name "Bootstrap Administrator" \
  --email bootstrap@erms.local
```

The command emits a unique 24-hour temporary password, requires it to be
changed on first login, and refuses to run after users exist. See
[`../docs/authentication.md`](../docs/authentication.md).

## Tests

```bash
database/tests/run.sh
```

The runner creates uniquely named disposable PostgreSQL databases inside a
temporary PostgreSQL container. It tests the canonical schema and the lifecycle
upgrade path separately, runs the API/database suite and backup/restore check,
then explicitly drops auxiliary databases and removes the container on success,
failure, or interruption. It never targets a persistent ERMS database.
