# ERMS NiceGUI frontend

The frontend is an independently deployable NiceGUI service. It communicates
with the FastAPI service over HTTP and does not access PostgreSQL directly.

## Run locally

Start the API first, then run:

```bash
./run-webui.sh
```

Open `http://localhost:8080`. The launcher creates a dedicated virtual
environment under `frontend/webui/.venv` and installs only the frontend's
dependencies.

To start the complete local stack instead, run:

```bash
./run-local-stack.sh
```

This reuses PostgreSQL, the API, or the UI when they are already running. If
PostgreSQL is unavailable at the default local URL, it creates a Docker
container initialized from `database/schema.sql`. Its data is retained in the
`erms-postgres-local-data` Docker volume between runs. Ctrl-C stops only the
processes and database container started by the script.

Configuration is read from the process environment, with `.env` as local
defaults:

- `WEBUI_API_URL` defaults to `http://127.0.0.1:8000`
- `WEBUI_HOST` defaults to `0.0.0.0`
- `WEBUI_PORT` defaults to `8080`
- `WEBUI_RELOAD` defaults to `false`
- `WEBUI_STORAGE_SECRET` encrypts per-user authentication storage and must be
  changed outside local development
- `DASHBOARD_RECENT_ITEM_LIMIT` defaults to `4` and controls how many items are
  shown in each personal recent-activity category
- `DASHBOARD_RECENT_DAYS` defaults to `30` and excludes activity older than that
  rolling number of days
- `CLASSIFICATION_RECENT_SELECTION_LIMIT` defaults to `4` and controls how many
  of the signed-in user's recently selected classifications are promoted in the
  aggregation classification selector.

Dashboard recent activity is attributed through the immutable audit event's
`actor_user_id`. Created and updated cards display the matching event's
`occurred_at` timestamp, rather than always displaying the entity creation date.
Both settings must be positive integers and take effect when the web UI process
is restarted. See [`../../docs/dashboard.md`](../../docs/dashboard.md) for the
Dashboard's system-wide and user-specific data semantics.

Real environment variables override `.env` values.

## Current scope

The interface provides the shared application shell, local authentication,
login-session administration, role-aware user menu, list views, search-first
aggregation and record views, add/edit dialogs, optimistic concurrency
handling, and record-scoped digital-component upload/listing. Classification
schemes and classifications share a vertically stacked administration workspace
with a fixed-height scrollable scheme browser, lazy-loaded hierarchy,
contextual root/child creation, classification search, and effective-rule
provenance. See [`../../docs/classification-schemes.md`](../../docs/classification-schemes.md)
for its behavior. The selected-classification pane exposes deactivate,
reactivate, and delete actions. Delete is enabled only for an unused leaf in an
active, unpublished scheme; otherwise inline guidance explains the blocking
condition. Direct, ancestor-derived, and scheme-derived inactivity are visibly
distinguished. See
[`../../docs/authentication.md`](../../docs/authentication.md) for authentication
operations and security behavior. Digital components can be downloaded in their
original format or viewed through the bundled, self-hosted PDF.js viewer. See
[`../../docs/document-viewing.md`](../../docs/document-viewing.md). Authorization
remains a later subsystem. Direct and inherited closure behavior is described in
[`../../docs/aggregation-closure.md`](../../docs/aggregation-closure.md).
