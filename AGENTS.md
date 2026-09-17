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
