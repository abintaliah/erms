# Application Configuration — Draft Specification

**Status:** Discussion draft — not approved; no implementation authorized  
**Project:** ERMS  
**Prepared:** 2 October 2026  
**Revision:** 0.1

## 1. Purpose

This specification separates ERMS configuration into two non-overlapping
categories:

1. **deployment configuration**, which remains in process environment variables
   or a local `.env` file; and
2. **application configuration**, which is stored only in PostgreSQL and may be
   changed through an authorized system-administration interface.

The separation makes PostgreSQL the single source of truth for shared
application behavior. It deliberately excludes copying settings between the
database and `.env`, exporting database settings to `.env`, PostgreSQL
notifications, a message broker, and distributed cache invalidation.

This document is a proposal only. It must not be implemented until it is
reviewed and explicitly approved.

## 2. Governing rules

1. Every production setting listed in this specification belongs to exactly one
   category.
2. A database-managed setting must not also be read from the process environment
   or `.env`, including as a fallback.
3. A deployment setting must not be copied into the application-settings table
   or exposed for editing in the administration UI.
4. Database-managed defaults are defined by the canonical schema and application
   setting registry. They do not come from `.env` at startup.
5. Creating or migrating a database inserts any missing application-setting rows
   without changing existing rows. Concurrent API startup performs no setting
   seeding.
6. All API instances connected to one logical database use the settings stored
   in that database.
7. Database-managed settings are never written back to `.env`.
8. Test-only variables, command-line-tool variables, standard operating-system
   variables, and virtual-environment bootstrap variables are outside this
   specification.

## 3. Configuration categories

### 3.1 Deployment configuration

Deployment configuration describes how a particular process starts, connects,
binds, stores process-local state, or consumes machine resources. It is known
before the API can read PostgreSQL and normally changes through deployment
operations rather than the ERMS administration UI.

Deployment settings are read once at process startup. Changing one requires the
affected process to restart unless the owning runtime already documents
different behavior.

### 3.2 Database-managed application configuration

Application configuration describes shared product behavior for one logical
ERMS database. PostgreSQL is its only source of truth. Authorized changes take
effect without restarting API or WebUI instances, subject to the short cache
expiry in section 6.

The API owns reads, validation, updates, and audit. The WebUI must obtain these
values through the API; it must not retain equivalent environment settings.
The separately deployed text indexer has no database connection and therefore
keeps all of its process and extraction settings as deployment configuration.

## 4. Exact deployment-setting inventory

The following settings remain environment/`.env` settings.

### 4.1 FastAPI and PostgreSQL connectivity

| Setting | Current default or requirement | Reason |
| --- | --- | --- |
| `DATABASE_URL` | Required | Required before application configuration can be read; contains database location and credentials |
| `API_HOST` | `0.0.0.0` | Per-process network binding |
| `API_PORT` | `8000` | Per-process network binding |
| `API_WORKERS` | `1` | Per-instance process capacity |
| `API_RELOAD` | `false` | Development/process-launch behavior |
| `DB_POOL_MIN_SIZE` | `1` | Per-process database capacity |
| `DB_POOL_MAX_SIZE` | `10` | Per-process database capacity |
| `DB_POOL_TIMEOUT` | `10` seconds | Per-process connection-pool behavior |
| `WATHIQ_APPLICATION_REVISION` | Packaged Git revision when required | Build/deployment identity |

### 4.2 WebUI process and session infrastructure

| Setting | Current default or requirement | Reason |
| --- | --- | --- |
| `DATABASE_DISPLAY_NAME` | Required | Default-language deployment identity displayed by the WebUI |
| `DATABASE_DISPLAY_NAME_<LANGUAGE>` | Optional; falls back to `DATABASE_DISPLAY_NAME` | Localized deployment identity using the uppercase base language tag, for example `DATABASE_DISPLAY_NAME_AR` |
| `WEBUI_API_URL` | `http://127.0.0.1:8000` | Address used to reach the API or its load balancer |
| `WEBUI_HOST` | `0.0.0.0` | Per-process network binding |
| `WEBUI_PORT` | `8080` | Per-process network binding |
| `WEBUI_RELOAD` | `false` | Development/process-launch behavior |
| `WEBUI_STORAGE_SECRET` | Must be supplied securely outside local development | Secret used for UI user-storage protection |
| `NICEGUI_REDIS_URL` | Unset | Optional external session-storage infrastructure |
| `NICEGUI_REDIS_KEY_PREFIX` | Runtime default when Redis is used | Deployment/environment isolation |

### 4.3 Security and storage infrastructure

| Setting | Current default or requirement | Reason |
| --- | --- | --- |
| `AUTH_COOKIE_SECURE` | `false` locally; `true` in the production example | Depends on the deployment's HTTPS boundary and must not be weakened from the application UI |
| `CONTENT_STORAGE_BACKEND` | `postgresql` | Storage-provider/infrastructure selection |
| `LIBREOFFICE_BINARY` | Auto-discovered when unset | Host executable path |

### 4.4 Service orchestration controls

| Setting | Current default | Reason |
| --- | ---: | --- |
| `TEXT_INDEXER_ENABLED` | `false` | Controls whether local orchestration launches the separate service |
| `CONTENT_INDEXING_MAINTENANCE_ENABLED` | `true` | Controls whether local orchestration launches the maintenance process |

These variables control processes, not shared runtime product behavior. An
external supervisor may provide equivalent orchestration without using them.

### 4.5 Text-indexer deployment

All text-indexer settings remain deployment settings because the indexer is a
separately deployed REST client with no direct PostgreSQL access.

| Setting | Current default or requirement |
| --- | --- |
| `TEXT_INDEXER_API_URL` | Required |
| `TEXT_INDEXER_API_KEY` | Required issued `wti_` credential |
| `TEXT_INDEXER_API_KEY_FILE` | `.secrets/text-indexer-api-key` for local provisioning |
| `TEXT_INDEXER_TIKA_HOME` | Required Tika installation path |
| `TEXT_INDEXER_WORKER_ID` | Required unique deployment identity in production |
| `TEXT_INDEXER_PROCESS_COUNT` | `2` |
| `TEXT_INDEXER_CLAIM_BATCH_SIZE` | `1` |
| `TEXT_INDEXER_POLL_SECONDS` | `5` |
| `TEXT_INDEXER_HEARTBEAT_SECONDS` | `60` |
| `TEXT_INDEXER_EXTRACTION_TIMEOUT_SECONDS` | `120` |
| `TEXT_INDEXER_MAX_INPUT_BYTES` | `52428800` |
| `TEXT_INDEXER_MAX_EXTRACTED_CHARACTERS` | `5000000` |
| `TEXT_INDEXER_CHUNK_TARGET_CHARACTERS` | `16000` |
| `TEXT_INDEXER_CHUNK_MAX_CHARACTERS` | `20000` |
| `TEXT_INDEXER_MAX_PAGES` | `1000` |
| `TEXT_INDEXER_MAX_TEMP_BYTES` | `1073741824` |
| `TEXT_INDEXER_TEMP_DIR` | Operating-system temporary directory plus `wathiq-text-indexer` |
| `TEXT_INDEXER_STALE_TEMP_HOURS` | `24` |
| `TEXT_INDEXER_TEMP_SWEEP_LIMIT` | `100` |

## 5. Exact database-managed setting inventory

The following settings move out of `.env` and become rows in the database. The
table records the initial canonical default. Approval of this specification
also approves removal of the corresponding environment lookup; it does not by
itself approve a particular API or UI layout.

### 5.1 General application behavior

| Setting key | Type | Initial default | Validation |
| --- | --- | ---: | --- |
| `DEFAULT_WORKING_TIMEZONE` | string | `Asia/Dubai` | Canonical IANA timezone identifier |
| `DEFAULT_ROOT_AGGREGATION_MEDIUM` | string | `mixed` | One of `digital`, `physical`, `mixed` |
| `REVIEW_WARNING_WINDOW_DAYS` | integer | `30` | At least `0` |

### 5.2 Content storage and document viewing policy

| Setting key | Type | Initial default | Validation |
| --- | --- | ---: | --- |
| `MAX_UPLOAD_SIZE_BYTES` | integer | `52428800` | At least `1` |
| `CONTENT_SEGMENT_SIZE_BYTES` | integer | `16777216` | At least `1` and within the safe range required by the segmented-storage specification |
| `CONTENT_SEGMENT_CHECKSUMS_ENABLED` | boolean | `true` | Boolean |
| `CONTENT_UPLOAD_SESSION_TTL_SECONDS` | integer | `86400` | At least `1` |
| `CONTENT_CLEANUP_INTERVAL_SECONDS` | integer | `3600` | At least `1` |
| `DOCUMENT_CONVERSION_TIMEOUT_SECONDS` | integer | `60` | At least `1` |
| `MAX_RENDITION_SIZE_BYTES` | integer | `104857600` | At least `1` |

### 5.3 Authentication and session policy

| Setting key | Type | Initial default | Validation |
| --- | --- | ---: | --- |
| `AUTH_SESSION_IDLE_MINUTES` | integer | `30` | At least `1` |
| `AUTH_SESSION_ABSOLUTE_HOURS` | integer | `12` | At least `1` |
| `AUTH_LOCKOUT_ATTEMPTS` | integer | `5` | At least `1` |
| `AUTH_LOCKOUT_MINUTES` | integer | `15` | At least `1` |
| `AUTH_PASSWORD_MIN_LENGTH` | integer | `12` | At least `8` |
| `AUTH_SESSION_RETENTION_DAYS` | integer | `90` | At least `0` |
| `AUTH_SESSION_CLEANUP_INTERVAL_SECONDS` | integer | `3600` | At least `1` |
| `AUTH_SESSION_CLEANUP_BATCH_SIZE` | integer | `500` | At least `1` |

Changing `AUTH_PASSWORD_MIN_LENGTH` affects validation of newly set or changed
passwords. It does not invalidate existing password hashes. Changes to session
lifetimes apply when a session is next evaluated; they do not recreate or
extend an already expired session.

### 5.4 Dashboard, selector, and administration-page limits

| Setting key | Type | Initial default | Validation |
| --- | --- | ---: | --- |
| `DASHBOARD_FAVOURITE_ITEM_LIMIT` | integer | `5` | At least `1` |
| `DASHBOARD_RECENT_ITEM_LIMIT` | integer | `4` | At least `1` |
| `DASHBOARD_RECENT_DAYS` | integer | `30` | At least `1` |
| `DASHBOARD_REVIEW_PREVIEW_LIMIT` | integer | `5` | At least `1` |
| `CLASSIFICATION_RECENT_SELECTION_LIMIT` | integer | `4` | At least `1` |
| `USER_DETAILS_SESSION_LIMIT` | integer | `5` | At least `1` |

### 5.5 Search and indexing policy owned by the API

| Setting key | Type | Initial default | Validation |
| --- | --- | ---: | --- |
| `FULL_TEXT_SEARCH_ENABLED` | boolean | `false` | Boolean |
| `CONTENT_INDEXING_SCHEDULING_ENABLED` | boolean | `false` | Boolean |
| `CONTENT_INDEXING_HISTORY_RETENTION_DAYS` | integer | `365` | At least `0` |
| `CONTENT_INDEXING_CLEANUP_INTERVAL_SECONDS` | integer | `3600` | At least `1` |
| `CONTENT_INDEXING_CLEANUP_BATCH_SIZE` | integer | `500` | At least `1` |
| `TEXT_INDEXER_CREDENTIAL_HISTORY_RETENTION_DAYS` | integer | `365` | At least `0` |
| `TEXT_INDEXER_RATE_LIMIT_PER_MINUTE` | integer | `600` | At least `1` |
| `SEARCH_RATE_LIMIT_PER_MINUTE` | integer | `600` | At least `1` |
| `MANUAL_REINDEX_RATE_LIMIT_PER_MINUTE` | integer | `60` | At least `1` |

`WEBUI_FULL_TEXT_SEARCH_ENABLED` is removed rather than migrated. The WebUI
uses the API's effective `FULL_TEXT_SEARCH_ENABLED` value so the two layers
cannot disagree.

## 6. Runtime reads and short-expiry cache

Each API process maintains an in-memory snapshot of the complete validated
database-managed configuration for one logical database.

1. The cache lifetime is **30 seconds**, measured from completion of a successful
   database load.
2. A request may use the cached snapshot until it expires.
3. The first access after expiry reloads the complete snapshot in one database
   query. A process-local lock prevents duplicate simultaneous reloads.
4. A successful administration update invalidates the updating API process's
   cache immediately. Other API processes observe the change no later than 30
   seconds after their last successful load.
5. There is no cross-process notification, polling loop, message broker, or
   shared cache.
6. The WebUI does not maintain a second authoritative settings cache. Ordinary
   page data returned by the API may include the effective values needed to
   render that page.
7. If a refresh fails, the API records the failure and may use its last fully
   validated snapshot for requests that can otherwise proceed. It must never
   construct a partial snapshot or substitute environment values. Normal
   database-dependent operations continue to follow their existing database
   failure behavior.

Thirty seconds is an upper bound on normal cross-instance propagation, not a
guarantee that all in-flight requests change behavior simultaneously. The
administration UI must state that a saved value can take up to 30 seconds to be
used by every API instance.

## 7. Registry and persistence model

The application owns a closed registry containing, for every key in section 5:

- stable key;
- data type;
- default value;
- validation rule;
- sensitivity classification;
- editable status; and
- administrator-facing label and description keys.

Unknown keys must not be accepted or used. None of the database-managed values
in section 5 is a secret.

The canonical schema contains an `application_settings` table with one row per
registered key. At minimum, each row stores the key, typed JSON value, row
version, last-update timestamp, and last-updating user. The canonical schema
seeds every key with the defaults in section 5. The upgrade migration inserts
missing rows only and never overwrites an existing value.

The database representation and application registry must agree on every key,
type, default, and validation constraint. Schema-level constraints must enforce
the invariants that can be expressed portably in PostgreSQL; the API validates
the complete proposed change before writing it.

## 8. Administration and audit

The administration UI presents only the keys in section 5. It groups settings
by the same functional areas, shows the effective value and validation rules,
and identifies the initial default. Secret deployment configuration is neither
returned by the API nor shown in this UI.

An update:

1. requires an authenticated person with an explicitly approved configuration-
   administration privilege;
2. requires a non-blank change reason;
3. uses the existing optimistic-concurrency pattern so one administrator cannot
   silently overwrite another administrator's edit;
4. validates all submitted values before changing any row;
5. changes the submitted settings and writes their audit evidence in one
   PostgreSQL transaction; and
6. records actor, time, reason, old value, new value, and resulting row version
   in durable event history.

The exact privilege code and its assignment to built-in profiles are an open
approval decision. Implementation must not reuse an unrelated administration
privilege merely to avoid adding the approved privilege.

## 9. Rollout and compatibility

There is no automatic import from `.env`.

For a new database, `database/schema.sql` creates the settings with the defaults
in section 5. For an existing database, the migration inserts those defaults.
Before deploying the code that stops reading the migrated environment variables,
an operator must compare any deployment-specific overrides with the proposed
database values and enter intentional non-default values through the governed
administration path. The deployment must then remove the section 5 variables
and `WEBUI_FULL_TEXT_SEARCH_ENABLED` from its environment files.

The checked-in environment examples must contain only section 4 settings after
the feature is implemented. Documentation for settings moved to PostgreSQL must
refer to the administration UI and database-backed defaults, not `.env`.

## 10. Existing-codebase impact analysis

This section records the expected impact of the proposal on the repository as it
exists on 2 October 2026. It is an implementation inventory, not authorization
to make the changes.

### 10.1 Database schema and migrations

`database/schema.sql` currently has no general application-settings table. An
implementation will need to:

- add the `application_settings` table, constraints, indexes, canonical rows,
  and any configuration-administration privilege to the self-contained latest
  schema;
- add a portable PostgreSQL migration for existing databases, repeating the
  required DDL and inserting missing settings without invoking the migration
  from `schema.sql`;
- extend the immutable event-history vocabulary and validation, if necessary,
  for configuration changes; and
- preserve source `migration` for actual upgrade events and use the existing
  API/web-UI audit source for administrator changes.

The migration cannot discover process environment values. Existing customized
environment values therefore require the explicit rollout reconciliation in
section 9. Schema and migration parity checks must include the new objects and
seeded rows.

### 10.2 API configuration boundary

`backend/services/api/config.py` currently provides generic environment readers
used for both deployment and application settings. It will need to retain
environment parsing only for section 4 and delegate section 5 keys to a new
database-backed application-configuration component.

The new component will need:

- the closed typed registry described in section 7;
- complete-snapshot loading and validation;
- the 30-second process-local cache and reload lock;
- an explicit test clock or equivalent deterministic cache-expiry seam;
- lookup methods that do not fall back to `os.getenv`; and
- a safe way to load settings through an existing connection without recursively
  invoking the normal request connection dependency.

API startup currently validates `DEFAULT_WORKING_TIMEZONE` before opening the
connection pool. The order in `backend/services/api/main.py` must change so the
pool opens first, the complete database configuration is loaded and validated,
and startup fails clearly if the canonical rows are missing or invalid. A failed
startup load must not fall back to environment values.

`backend/services/api/database.py` currently obtains
`CONTENT_INDEXING_SCHEDULING_ENABLED` from the environment while establishing
each request's PostgreSQL session context. That value must instead come from the
validated cached snapshot. Database URL and pool sizing remain environment
reads and must remain usable before the settings cache exists.

### 10.3 API call sites that must become runtime lookups

Several modules resolve application settings into module-level constants at
import time. Those constants must be removed because they would prevent an
administrator's change from taking effect without restart:

- `backend/services/api/authentication.py`: session idle/absolute lifetimes,
  lockout policy, and minimum password length;
- `backend/services/api/main.py`: default aggregation medium and review warning
  window;
- `backend/services/api/dashboard.py`: review warning window and review preview
  limit; and
- `backend/services/api/database.py`: content-index scheduling session context.

The following existing environment reads must also be routed through the same
component at their point of use:

- `backend/services/api/content_storage.py`: upload limit, segment size,
  per-segment checksums, and upload-session lifetime;
- `backend/services/api/document_conversion.py`: conversion timeout and maximum
  rendition size, while leaving the LibreOffice executable path in the
  environment;
- `backend/services/api/search.py` and API health responses: full-text-search
  availability;
- API middleware in `backend/services/api/main.py`: search, manual-reindex, and
  text-indexer request limits;
- `backend/services/api/localization.py`: working timezone;
- `backend/services/api/session_cleanup.py`: retention, interval, and batch
  settings;
- `backend/services/api/content_cleanup.py`: cleanup interval;
- `backend/services/api/text_indexing_maintenance.py`: indexing retention,
  cleanup interval, cleanup batch size, and credential retention; and
- `backend/services/api/user_management.py`: text-indexer credential-history
  retention.

Functions that already receive a database connection should use a snapshot
associated with that request or operation instead of issuing individual setting
queries. Code that does not currently receive a connection will need an explicit
configuration dependency or a narrowly scoped snapshot argument; hidden global
database calls should not be scattered through domain modules.

The health response currently exposes selected feature flags. It may continue
to expose non-secret effective values, but it must obtain them from the same
snapshot and must not become an unrestricted settings endpoint.

### 10.4 Operational API-owned workers

The session cleanup, content cleanup, and text-indexing maintenance commands run
outside API request handling but connect to the same logical database. Their
database-managed defaults must no longer be argparse defaults sourced from the
environment.

For one-shot execution, each command loads one validated settings snapshot at
the start of the run. For `--watch` execution, it uses the same 30-second cache
and re-evaluates interval, retention, and batch settings before each pass.
Explicit command-line arguments remain per-invocation operator overrides and do
not modify database settings; help output must distinguish an explicit override
from the database-managed default. Existing advisory-lock and single-logical-
database execution requirements are unchanged.

The text-indexer worker itself remains unaffected by the database settings
component. Its existing `backend/services/text_indexer/config.py` environment
model remains intact. Only the API-owned policies around indexing and indexer
credentials move to PostgreSQL.

### 10.5 Administration API and authorization

No current API router provides general application-setting administration. An
implementation will require endpoints to:

- list the registered editable settings and their effective values, types,
  validation metadata, defaults, versions, and last-update metadata; and
- update one setting or an approved atomic batch with `If-Match`/expected
  versions and a mandatory change reason.

Request and response models must be explicit; the generic CRUD routes must not
be used to bypass registry validation, authorization, optimistic concurrency,
or auditing. Deployment settings must be impossible to retrieve through these
endpoints.

The authorization subsystem currently has no configuration-administration
privilege. Approval must resolve the open decision in section 12 before schema,
profile, API-policy, and authorization tests can be finalized. Role-name checks
must not replace privilege enforcement.

### 10.6 WebUI behavior and configuration module

`frontend/webui/config.py` currently reads the working timezone, root medium,
full-text feature flag, Dashboard limits, recent-classification limit, and user-
session page size from the environment. Those functions must be removed or
changed to consume API-provided effective configuration. Its deployment-only
functions for API URL, host, port, reload, and storage secret remain.

`frontend/webui/app.py` currently uses those helpers in localization fallback,
aggregation creation, Dashboard rendering, favourites previews,
classification selection, and user-session pagination. Those consumers must
use values returned by existing bounded page/bootstrap responses or a single
bounded configuration response. The implementation must not add one settings
request per widget or introduce duplicate page requests, in accordance with
`docs/webui-performance.md`.

The duplicate `WEBUI_FULL_TEXT_SEARCH_ENABLED` path must be deleted. UI feature
visibility and the API's enforcement must derive from the same database value;
API enforcement remains authoritative during the cache propagation window.

A new administration page or section will be required. Before implementation,
its user-visible text must follow sections 7.5 and 7.8.1–7.8.4 of
`specs/internationalization-and-user-preferences.md`. English keys must remain
lexicographically ordered, maintained-language artifacts must preserve curated
translations and follow the identical key order, and live LTR/RTL behavior must
be verified. If a settings table is used, it must follow the established Wathiq
table pattern rather than a raw/default NiceGUI table.

### 10.7 Environment examples, launchers, and documentation

Implementation will remove every section 5 key and
`WEBUI_FULL_TEXT_SEARCH_ENABLED` from:

- `.env.example`;
- `.env.example.api` where present;
- `backend/services/api/deploy/api.env.example`; and
- `frontend/webui/deploy/webui.env.example` where present.

Text-indexer example files retain the complete section 4.5 inventory. Local
stack launch scripts must stop interpreting database-managed keys as process
configuration, while retaining the service-orchestration controls in section
4.4.

At minimum, `docs/deployment.md`, `docs/operations.md`,
`docs/authentication.md`, `docs/dashboard.md`, `docs/document-viewing.md`,
`docs/content-storage.md`, `docs/full-text-search-local-setup.md`, and
`frontend/webui/README.md` require reconciliation wherever they currently
describe a migrated setting as an environment variable or restart-only value.
Existing feature specifications that normatively define one of these defaults
must be cross-referenced or amended without silently changing their approved
product behavior.

### 10.8 Test impact

Tests that currently change environment variables or reload modules to exercise
section 5 settings must instead insert/update rows in a newly created disposable
test database and explicitly expire or replace the test cache. Pure registry and
validation tests may remain database-free.

Required additions include:

- canonical-schema, migration, and schema/migration parity coverage;
- registry-to-database completeness and type/default agreement tests;
- no-environment-fallback tests using deliberately conflicting environment
  values;
- deterministic cache hit, expiry, refresh-failure, local invalidation, and
  multi-instance convergence tests;
- concurrent-administrator optimistic-conflict and atomic rollback tests;
- privilege and deployment-setting non-disclosure tests;
- worker one-shot, watch-mode refresh, and command-line-override tests;
- API/WebUI integration tests proving that feature visibility and enforcement
  share one value; and
- rendered administration-page comparison in LTR and RTL, including validation,
  empty/loading/error states, and narrow viewports.

No database-backed test may reuse a development or other persistent database.
Each such run must create, initialize, target, and finally drop a uniquely named
disposable PostgreSQL database as required by the repository instructions.

### 10.9 Principal risks and mitigations

| Risk | Required mitigation |
| --- | --- |
| Import-time constants preserve stale values forever | Remove section 5 module-level constants and resolve through the cached snapshot at use time |
| API instances disagree for up to one cache lifetime | Document the 30-second bound; keep enforcement server-side; test controlled-clock convergence |
| A setting change produces internally inconsistent behavior within one request | Capture one immutable snapshot for the request/operation and pass it to all affected logic |
| Startup cannot validate database configuration because pool opening depends on configuration | Keep connectivity/pool settings in the environment and load database settings only after the pool opens |
| Existing customized `.env` values are lost during rollout | Require the section 9 pre-deployment comparison and explicit database entry before removing variables |
| WebUI adds repeated settings requests or a second cache | Include needed effective values in bounded bootstrap/page responses and keep the API authoritative |
| Invalid direct SQL edits break every instance | Enforce database constraints, validate the complete snapshot, fail startup on an invalid initial load, and retain only a previously validated runtime snapshot |
| Cleanup workers silently retain startup values | Re-evaluate settings before each watch pass through the same short-expiry component |
| Administrators expose or mutate infrastructure secrets | Keep section 4 keys outside the table, API models, event metadata, and UI |
| Feature flag changes are visible before all instances enforce them | State the propagation window in the UI and treat the API instance handling each request as authoritative |

### 10.10 Estimated implementation breadth

This is a cross-cutting configuration migration rather than a localized UI
change. It affects the canonical schema and one migration, the API configuration
and connection lifecycle, multiple API domain modules, three API-owned
operational workers, WebUI configuration consumers, authorization and audit,
environment examples, operational documentation, and both unit and browser
test suites. The text-indexer process configuration and deployment-level API/UI
startup settings remain deliberately outside the change.

Implementation should be phased so the database table and read path exist before
environment fallbacks are removed, but no phase may leave two production
authorities for a section 5 key. A compatibility phase may write and verify the
database values while the old code remains deployed; the cutover release must
switch each migrated key to database-only authority and remove its environment
lookup together.

## 11. Acceptance and traceability requirements

| Requirement | Required verification |
| --- | --- |
| ACFG-01 — Every production setting is assigned to exactly one category | Inventory test comparing registered settings, production environment reads, and documented tables |
| ACFG-02 — Database-managed keys have no environment lookup or fallback | Static/source test and runtime tests with conflicting environment values |
| ACFG-03 — Canonical schema and migration create all settings without overwriting existing values | Fresh-schema and upgrade tests using separate disposable databases |
| ACFG-04 — Types, defaults, and validation match section 5 | Registry/schema contract tests and invalid-update API tests |
| ACFG-05 — Multiple API processes converge within the 30-second cache lifetime without notifications | Controlled-clock multi-instance integration test |
| ACFG-06 — A failed refresh never exposes a partial or environment-derived snapshot | Unit and database-failure integration tests |
| ACFG-07 — Administrative updates are authorized, reasoned, optimistic, atomic, and audited | Authorization, conflict, rollback, and event-history tests |
| ACFG-08 — The WebUI has no duplicate feature flag or business-setting authority | UI/API integration and source inventory tests |
| ACFG-09 — Deployment secrets and infrastructure values are absent from the settings API and UI | API negative tests and UI tests |
| ACFG-10 — Environment examples and operational documentation contain only deployment settings | Documentation/inventory check |
| ACFG-11 — LTR and RTL administration UI behavior and all maintained translations are verified | Browser verification and internationalization artifact checks |

Database-backed verification must follow the repository rule requiring a newly
created, uniquely named disposable PostgreSQL database for each run and clean
removal after the run, whether the run passes or fails.

## 12. Decisions required before approval

1. Approve or change the proposed 30-second cache lifetime.
2. Approve the exact configuration-administration privilege code and built-in
   profile assignments.
3. Confirm whether every setting in section 5 is editable, or identify any key
   that should be database-resident but read-only after installation.
4. Confirm the rollout treatment of existing non-default environment values.
5. Confirm whether the administration UI saves one setting at a time or permits
   a validated atomic batch edit.
