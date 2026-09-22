# Project instructions

## Specification fidelity

- An approved specification is the authoritative product contract. Implement
  exactly what it requires; do not invent privileges, entities, workflows,
  states, API contracts, UI behavior, or other product requirements that are
  not stated in the specification or separately requested and approved by the
  user.
- If implementation appears to require a product-level addition or departure
  from an approved specification, stop and obtain the user's explicit approval
  before making that change. Do not treat a technical shortcut, convention, or
  inferred preference as approval.
- Maintain requirement-to-implementation-to-test traceability for specified
  features. Do not declare a phase or feature complete while an approved
  requirement lacks implementation or verification evidence.

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

## Frontend table design

- Never introduce a raw or default-styled NiceGUI `ui.table`.
- Before adding or changing a table, inspect a comparable Wathiq table and
  reuse its established presentation and interaction pattern.
- User-facing tables must use Wathiq's standard light-blue headers, borders,
  spacing, typography, action treatment, filtering where relevant, sortable
  columns, pagination controls, and deliberate empty/loading/error states.
- UI table work is incomplete until its rendered appearance has been compared
  with existing Wathiq tables in a live browser.
