# Project instructions

## Database-backed tests

- Never run a test suite against the development, staging, production, or any
  other persistent ERMS database.
- Before a database-backed test run, create a new uniquely named disposable
  PostgreSQL database dedicated to that run.
- Initialize the disposable database from the repository's canonical schema or
  the migration path required by the test.
- Point the complete test process, including fixtures, at that disposable
  database only.
- After the run finishes, whether it passes or fails, terminate remaining
  connections if necessary and drop the disposable database cleanly.
- Report database creation and cleanup failures; do not silently leave test
  databases behind.

## Canonical database SQL

- SQL files must contain portable PostgreSQL SQL only. Never put `psql`
  meta-commands such as `\\i`, `\\ir`, `\\set`, or `\\copy` in any `.sql` file.
- `database/schema.sql` is the complete, self-contained latest schema for a new
  empty database. It must never include, invoke, or otherwise depend on a
  migration file.
- A new empty database is initialized from `database/schema.sql` alone.
- Migration scripts exist only to upgrade an existing database containing
  data. Repeat required DDL in `schema.sql`; do not make the canonical schema
  execute migrations.
- Seed scripts are separate from schema creation and migrations. They must
  target the latest canonical schema, must not be invoked by `schema.sql`, and
  must not be disguised as migrations even when SQL must be repeated.
- Event-history rows created by seed scripts or seed utilities must use source
  `seeding`; source `migration` is reserved for actual database upgrades.
