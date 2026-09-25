# Linux deployment

ERMS has four independently managed components: the FastAPI backend, the
NiceGUI web UI, the REST-only text indexer, and PostgreSQL. Use separate systemd units for the API, UI, and indexer
for an ongoing Linux deployment. They can run on the same server or on separate
servers; PostgreSQL can also be hosted independently.

## Deployment options

| Arrangement | Frontend API address | Load balancing |
| --- | --- | --- |
| One API and one UI on one server | `http://127.0.0.1:8000` | A reverse proxy can serve the UI over HTTPS; affinity is unnecessary with one UI instance. |
| One API and one UI on separate servers | Reachable private API address | No affinity is needed with one instance of each service. |
| Multiple API instances | API load balancer address | API requests can go to any instance sharing the same PostgreSQL database. |
| Multiple UI instances | API address or API load balancer address | The UI load balancer needs session affinity and WebSocket support; shared user storage is optional for preserving login data across instances. |

The request path is browser → UI proxy/load balancer → NiceGUI → API address or
load balancer → FastAPI → PostgreSQL. `WEBUI_API_URL` is used by the NiceGUI
server, so it must be reachable from the UI servers. Browsers do not need
direct access to the API for the current UI.

## Sessions and load balancing

### API instances

API authentication uses an opaque token whose hash is stored in PostgreSQL's
`login_sessions` table. Cookies carry tokens for cookie-authenticated clients;
NiceGUI forwards its token as a Bearer credential. A cookie does not imply
server affinity: any API instance can validate the token against the shared
database. See [authentication](authentication.md).

Uploaded digital-component content is also stored in PostgreSQL, rather than
on an API server's local disk. See [content storage](content-storage.md).
Keep all API instances on the same application version and compatible
configuration, pointing to the same logical PostgreSQL database. They need
neither the same physical application server nor sticky sessions.

`API_WORKERS` can increase the number of API worker processes on one server.
Each worker has its own database connection pool. Budget database connections
across all instances: the application pool maximum is approximately
`instance count × API_WORKERS × DB_POOL_MAX_SIZE`, plus connections for
administration and other clients. Increasing API capacity does not increase
database capacity automatically.

### NiceGUI instances

NiceGUI maintains live page state and connections within an instance. When
running multiple UI instances, configure the frontend load balancer to keep
each browser's HTTP requests, Socket.IO traffic, and WebSocket connection or
reconnections on the same UI instance. A load-balancer affinity cookie is
separate from the API's authentication cookie. Enable WebSocket upgrades and
timeouts suitable for long-lived connections.

Affinity is still required when user storage is shared. Shared storage makes
the stored API token available across instances; it does not move live page
objects or callback state between them. A failed or restarted UI instance can
require users to reload the page. See
[NiceGUI's multi-instance guidance](https://github.com/zauberzeug/nicegui/discussions/1539).

The current frontend uses `app.storage.user` and defaults to local NiceGUI
storage. You can run multiple UI instances with affinity and local storage,
accepting that users routed to another instance may need to sign in again.
Redis is optional and does not preserve live pages. To enable shared storage:

1. Install NiceGUI's Redis extra into each frontend environment. The current
   `frontend/webui/requirements.txt` declares plain NiceGUI without this extra:

   ```bash
   frontend/webui/.venv/bin/python -m pip install 'nicegui[redis]>=2.24,<3'
   ```

   Include the extra in your deployment dependency installation so rebuilt
   environments retain Redis support.
2. Set `NICEGUI_REDIS_URL` on every UI instance to the same reachable Redis
   service. Configure it before starting the UI process.
3. Set the same strong `WEBUI_STORAGE_SECRET` on every UI instance, and use
   consistent Redis key prefixes. Separate environments must use separate
   Redis databases or `NICEGUI_REDIS_KEY_PREFIX` values.
4. Configure frontend affinity and verify login, navigation, reconnects, and
   behavior when a UI instance restarts.

Redis is additional infrastructure for shared UI storage; PostgreSQL remains
the authority for API authentication and records. See the
[NiceGUI Redis deployment example](https://github.com/zauberzeug/nicegui/tree/main/examples/redis_storage).

## Server preparation and configuration

Install Python 3.11 or newer with virtual-environment support and PostgreSQL 18
or newer, and place the
application at an absolute path such as `/opt/erms`. Create a dedicated Linux
account such as `erms` to run it. The launchers create their virtual environments
and install dependencies on first use, so the service account needs write
access to their environment directories. A UI server also needs write access
to its local NiceGUI storage directory when Redis is not used.

Initialize a new database or migrate an existing one using the
[database instructions](../database/README.md). Apply migrations once per
shared database, rather than from every API instance, and bootstrap the first
administrator as documented there. Prepare dependencies before enabling
services so routine restarts do not depend on package downloads. Pin the
resolved dependency versions in your deployment process for consistent replicas.

Full-text search requires the unmodified built-in `pg_catalog.simple`,
`pg_catalog.english`, and `pg_catalog.arabic` configurations. Schema creation
and migration 010 check these prerequisites atomically; do not create substitute
catalogue objects or change the database-wide default text-search configuration.

The indexer has no `DATABASE_URL`. Install Java 17+, Tesseract with `eng` and
`ara`, Poppler's `pdfinfo` and `pdftoppm`, and the complete official Apache
Tika 4.0.0 app binary distribution.
Verify the distribution archive against
`backend/services/text_indexer/TIKA-DISTRIBUTION.sha512`, extract it to a
root-owned/read-only directory, and set `TEXT_INDEXER_TIKA_HOME` to the
directory containing `tika-app-4.0.0.jar` and the adjacent `lib/` directory.
The startup self-test requires `lib/tika-pipes-fork-parser-4.0.0.jar`; neither
the Homebrew thin CLI package nor a Tika Docker service is supported.

For a developer checkout, run
`backend/services/text_indexer/install-tika.sh`. The installer downloads the
official pinned distribution, verifies the committed archive and application
JAR SHA-512 values, checks for the fork-parser JAR, and installs it under the
Git-ignored `vendor/tika/` directory.

The complete macOS contributor procedure, including installation of Java,
Tesseract with Arabic and English data, Poppler, LibreOffice and PostgreSQL 18,
is in [Full-text search local setup](full-text-search-local-setup.md).

Use `.env.example.api` as the API-host environment template and
`.env.example.text_indexer` as the independently deployable indexer's template.
`TEXT_INDEXER_PROCESS_COUNT` belongs in the full-stack `.env`/`.env.example`
and the text-indexer templates because the supervisor consumes it. It is
intentionally absent from `.env.example.api`: an API-only process neither
starts nor configures text-indexer child processes.
The latter intentionally contains no database credential. Supply
`TEXT_INDEXER_API_KEY` through a protected environment file or deployment
secret store; never commit its value or place it on a command line.

Run `run-text-indexer.sh --self-test` during deployment, then supervise
`run-text-indexer.sh`. Production `TEXT_INDEXER_API_URL` must be HTTPS; plain
HTTP is rejected except on loopback. Deny outbound network access for the
indexer/extractor service at the OS or workload boundary while permitting only
the API destination and Tika's internal loopback Pipes IPC. Apply 2-CPU, 1-GiB
memory, 1-GiB private temporary-storage, and process-count controls in the
service manager in addition to the worker's timeout, JVM heap, file-size, and
Linux address-space limits. Supply the display-once API key through protected
secret storage, never an environment file in source control or command line.

For local development only, `TEXT_INDEXER_ENABLED=true` makes
`run-local-stack.sh` provision a least-privilege service account/key against a
loopback database, store it mode `0600` under `.secrets/`, start and monitor the
worker, and fail the stack if it exits. The default is explicitly disabled and
reported. Readiness is withheld until the worker has registered through a real
claim request. The managed database image is PostgreSQL 18.

Use separate environment files, for example `/etc/erms/api.env` and
`/etc/erms/webui.env`. Restrict access because they contain credentials. These
files use literal `KEY=value` assignments, not shell commands or references
to other variables. Process environment values override the repository's
`.env` defaults.

Example `/etc/erms/api.env`:

```ini
DATABASE_URL=postgresql://erms:REPLACE_PASSWORD@db.internal:5432/erms
API_HOST=127.0.0.1
API_PORT=8000
API_WORKERS=1
API_RELOAD=false
DB_POOL_MIN_SIZE=1
DB_POOL_MAX_SIZE=10
CONTENT_STORAGE_BACKEND=postgresql
CONTENT_SEGMENT_SIZE_BYTES=16777216
CONTENT_SEGMENT_CHECKSUMS_ENABLED=true
CONTENT_UPLOAD_SESSION_TTL_SECONDS=86400
CONTENT_CLEANUP_INTERVAL_SECONDS=3600
AUTH_SESSION_RETENTION_DAYS=90
AUTH_SESSION_CLEANUP_INTERVAL_SECONDS=3600
AUTH_SESSION_CLEANUP_BATCH_SIZE=500
CONTENT_INDEXING_HISTORY_RETENTION_DAYS=365
CONTENT_INDEXING_CLEANUP_INTERVAL_SECONDS=3600
CONTENT_INDEXING_CLEANUP_BATCH_SIZE=500
TEXT_INDEXER_CREDENTIAL_HISTORY_RETENTION_DAYS=365
DASHBOARD_REVIEW_PREVIEW_LIMIT=5
REVIEW_WARNING_WINDOW_DAYS=30
DEFAULT_ROOT_AGGREGATION_MEDIUM=mixed
AUTH_COOKIE_SECURE=true
CONTENT_INDEXING_SCHEDULING_ENABLED=false
FULL_TEXT_SEARCH_ENABLED=false
```

`DEFAULT_ROOT_AGGREGATION_MEDIUM` accepts `digital`, `physical`, or `mixed` and
defaults root-aggregation forms without preventing the creator from choosing a
different value. `REVIEW_WARNING_WINDOW_DAYS` controls how far ahead review
warnings appear and defaults to 30 days. `DASHBOARD_REVIEW_PREVIEW_LIMIT`
defaults to five items per review category; zero keeps complete counts but
omits preview items. Invalid values must prevent application startup.

Run segmented-content cleanup from exactly one dedicated worker or deployment
scheduler, not from every API worker:

```bash
python -m backend.services.api.content_cleanup --watch
```

Administrators can inspect or execute cleanup manually with `--dry-run` and
`--batch-size`. The worker uses a PostgreSQL advisory lock to prevent overlap.
The central [operational tools catalogue](operations.md) lists this worker,
login-session cleanup, authentication administration, database
operations, their scheduling alternatives, and required safeguards. Deployment
runbooks must use that catalogue rather than discovering operational commands
from feature documentation.

Run full-text indexing and retained text-indexer credential cleanup from one
API-owned supervised worker per logical database:

```bash
python -m backend.services.api.text_indexing_maintenance cleanup --watch
```

For the packaged Linux deployment, install
`backend/services/api/deploy/erms-text-indexing-maintenance.service` alongside
the API service. On macOS local development, `run-local-stack.sh` starts and
monitors the same worker automatically. A platform scheduler may instead run
the one-shot `cleanup` command hourly; do not use both scheduling models.

Example `/etc/erms/webui.env`:

```ini
WEBUI_API_URL=http://127.0.0.1:8000
WEBUI_HOST=127.0.0.1
WEBUI_PORT=8080
WEBUI_RELOAD=false
WEBUI_STORAGE_SECRET=REPLACE_WITH_A_STRONG_RANDOM_SECRET
WEBUI_FULL_TEXT_SEARCH_ENABLED=false
```

## Full-text search staged rollout and rollback

Keep the four controls independent: the indexer unit, automatic scheduling
(`CONTENT_INDEXING_SCHEDULING_ENABLED`), API search (`FULL_TEXT_SEARCH_ENABLED`),
and header search (`WEBUI_FULL_TEXT_SEARCH_ENABLED`). A new environment starts
with all four disabled.

1. Apply all migrations through 017 while the indexer and all three flags are
   disabled. Confirm `/health` reports both API flags false.
2. Install and verify
   `backend/services/text_indexer/deploy/erms-text-indexer.service`, then set
   `TEXT_INDEXER_PROCESS_COUNT` to the worker-process capacity of the host.
   Inject its key as `TEXT_INDEXER_API_KEY` through the deployment's protected
   environment file or secret store, and enforce an egress firewall that
   permits only the HTTPS API peer and loopback Pipes IPC. Run
   `run-text-indexer.sh --self-test`, then enable the unit.
3. Set `CONTENT_INDEXING_SCHEDULING_ENABLED=true` on every API instance and
   restart them. Confirm new available content creates a queued job.
4. Run bounded backfill passes from **Administration → Text Indexers → Health**
   with **Queue backfill batch**, or with
   `backend/services/api/.venv/bin/python -m backend.services.api.text_indexing_maintenance reconcile --batch-size 500`.
   Repeat until a pass reports zero examined and zero queued.
   Observe `metrics` between passes; pause when database, API, extractor, or
   storage load approaches the environment's alert limits.
5. Run `quality-gate examples/samples/docs/phase2-worker-benchmark-results.json`
   and `readiness`. Do not expose search until both exit successfully and the
   operational observation window has no sustained queue growth, lease loss,
   cleanup failure, or unexpected extraction error trend.
6. Set `FULL_TEXT_SEARCH_ENABLED=true` on every API instance and smoke-test the
   governed API. Finally set `WEBUI_FULL_TEXT_SEARCH_ENABLED=true` on every UI
   instance and smoke-test the header.

Rollback is non-destructive: first disable the UI flag, then API search, then
automatic scheduling, and stop the indexer. Pending/stale status remains
truthful and source content is untouched. Do not drop index tables; their
removal requires a separately reviewed later migration. Re-enable in the same
staged order after remediation.

These loopback bindings suit a proxy on the same server. For separate servers
or remote load balancers, bind the appropriate service to its private interface
or `0.0.0.0`, and restrict ingress to the required peers. Set `WEBUI_API_URL`
to the private API endpoint or API load balancer. Use HTTPS for public browser
access, protect cross-server traffic appropriately, and keep PostgreSQL and
Redis accessible only to the services that need them. `AUTH_COOKIE_SECURE=true`
is required for HTTPS API cookie clients; HTTP cookie clients cannot send a
Secure cookie. NiceGUI uses Bearer authentication for its API requests.

## Separate systemd services

Ready-to-install Ubuntu unit files and environment templates are provided
within each service’s `deploy` directory:

- [`erms-api.service`](../backend/services/api/deploy/erms-api.service)
- [`erms-session-cleanup.service`](../backend/services/api/deploy/erms-session-cleanup.service)
- [`erms-webui.service`](../frontend/webui/deploy/erms-webui.service)
- [`erms-text-indexer.service`](../backend/services/text_indexer/deploy/erms-text-indexer.service)
- [`api.env.example`](../backend/services/api/deploy/api.env.example)
- [`webui.env.example`](../frontend/webui/deploy/webui.env.example)
- [`text-indexer.env.example`](../backend/services/text_indexer/deploy/text-indexer.env.example)

They assume `/opt/erms`, a service account and group named `erms`, and
`/etc/erms/api.env` and `/etc/erms/webui.env`. Adapt paths and account names
if needed. The repository currently has one backend application service:
FastAPI. Authentication, search, and document conversion run within it and do
not need separate units. PostgreSQL uses its independently managed service.

On Ubuntu with Python 3.11 or newer available, prepare the service account:

```bash
sudo apt update
sudo apt install python3 python3-venv curl
sudo useradd --system --user-group --home-dir /var/lib/erms --create-home --shell /usr/sbin/nologin erms
sudo install -d -m 0750 -o root -g erms /etc/erms
```

Create the account only if it does not already exist. Ubuntu releases whose
system Python is older than 3.11 need a supported newer Python; set
`PYTHON_BOOTSTRAP` in the environment files to its executable. For Office
file previews, install LibreOffice on the API server as described in
[document viewing](document-viewing.md).

Copy the application to `/opt/erms` before proceeding. Create writable runtime
directories while keeping the deployed source owned by the deploying account:

```bash
sudo install -d -m 0750 -o erms -g erms /opt/erms/backend/services/api/.venv
sudo install -d -m 0750 -o erms -g erms /opt/erms/frontend/webui/.venv /opt/erms/.nicegui
```

Ensure `erms` can read the source and execute the launchers. Build virtual
environments on the Ubuntu server; do not copy macOS virtual environments.
From the deployed project root, install the units and initial configuration:

```bash
sudo install -m 0644 backend/services/api/deploy/erms-api.service /etc/systemd/system/erms-api.service
sudo install -m 0644 backend/services/api/deploy/erms-session-cleanup.service /etc/systemd/system/erms-session-cleanup.service
sudo install -m 0644 frontend/webui/deploy/erms-webui.service /etc/systemd/system/erms-webui.service
sudo install -m 0644 backend/services/text_indexer/deploy/erms-text-indexer.service /etc/systemd/system/erms-text-indexer.service
sudo install -m 0600 backend/services/api/deploy/api.env.example /etc/erms/api.env
sudo install -m 0600 frontend/webui/deploy/webui.env.example /etc/erms/webui.env
sudo install -m 0600 backend/services/text_indexer/deploy/text-indexer.env.example /etc/erms/text-indexer.env
sudoedit /etc/erms/api.env /etc/erms/webui.env /etc/erms/text-indexer.env
```

Copy environment templates only during initial setup; copying them again would
replace existing configuration. Replace the database password and UI storage
secret before starting. On separate servers, install only the relevant unit,
environment file, and runtime directories. Set the API binding and
`WEBUI_API_URL` for cross-server connectivity as described above.

The units use the existing launchers, which prepare dependencies on first
startup. They send logs to the journal, restart after failures, stop child
processes as a group, and use a restrictive file-creation mask. You can verify
the installed unit configuration on Ubuntu before enabling it:

```bash
sudo systemd-analyze verify /etc/systemd/system/erms-api.service /etc/systemd/system/erms-session-cleanup.service /etc/systemd/system/erms-webui.service
sudo systemd-analyze verify /etc/systemd/system/erms-text-indexer.service
```

### Text-indexer process-pool examples

The deployment runs one `erms-text-indexer.service`. Its Python supervisor
starts `TEXT_INDEXER_PROCESS_COUNT` child workers. Every child claims exactly
one job at a time; the configured `TEXT_INDEXER_WORKER_ID` is only the base for
unique runtime IDs. A failed child slot is restarted without stopping healthy
siblings. systemd supervises the complete service and restarts it if the
supervisor itself exits.

#### Account and credential boundaries

The complete relationship is:

```text
Text Indexers service account
└── active API key stored by one deployed text-indexer service
    └── supervisor process
        ├── child worker 1 — one claimed job
        └── child worker 2 — one claimed job
```

Create the non-interactive account in **Administration → Text Indexers**. The
dedicated workflow assigns the protected built-in Text Indexer Service role
and displays the initial API key once. Store that key in the deployment's
protected secret store or `/etc/erms/text-indexer.env`; never commit it. Child
workers in the service pool share that account and key, while the supervisor
gives every child a distinct runtime worker ID. Do not create a service account
or API key for every child process.

The recommended production boundary is one Text Indexers account and key per
server or independently operated worker pool. Server A should normally use
account/key A and Server B account/key B. That permits independent audit
attribution, rotation, revocation, suspension, and incident containment. A
trusted identically managed group may share an account only when that shared
security boundary is intentional.

Suspending an account disables every service and child using it. Revoking a
key disables deployments using that key, without affecting a separate account
or another active key. To rotate safely, generate a new key, deploy it to the
intended service, restart and verify its workers in **Text Indexers → Health**,
and only then revoke the old key.

**Small production host — one concurrent extraction:**

```ini
TEXT_INDEXER_WORKER_ID=records-indexer-a
TEXT_INDEXER_PROCESS_COUNT=1
TEXT_INDEXER_CLAIM_BATCH_SIZE=1
```

This produces one runtime worker, for example
`records-indexer-a-1842-1`, and processes one document at a time.

**Normal production host — two concurrent extractions:**

```ini
TEXT_INDEXER_WORKER_ID=records-indexer-a
TEXT_INDEXER_PROCESS_COUNT=2
TEXT_INDEXER_CLAIM_BATCH_SIZE=1
```

This produces two child workers, such as `records-indexer-a-1842-1` and
`records-indexer-a-1842-2`. They share the service account/API key but lease
different jobs and run separate Tika/OCR subprocesses.

**Two production hosts:** configure a distinct base on each host, for example
`records-indexer-a` and `records-indexer-b`. With a process count of `2` on
each host, the deployment can extract four documents concurrently. All four
workers claim through the API; none connects directly to PostgreSQL. Normally,
provision a separate Text Indexers account/API key for each host, while the two
child workers on the same host share that host's credential.

After editing `/etc/erms/text-indexer.env`, start or restart the single service:

```bash
sudo systemctl enable --now erms-text-indexer.service
sudo systemctl restart erms-text-indexer.service
sudo systemctl status erms-text-indexer.service
```

The service unit's CPU, memory and task limits apply to the whole process pool.
Size those aggregate limits for the configured count. Keep
`TEXT_INDEXER_CLAIM_BATCH_SIZE=1`; concurrency comes from child processes, not
claim prefetching or threads.

The UI unit intentionally has no `Requires=erms-api.service`: systemd
dependencies refer to local units and cannot represent a remote API. Network
ordering also does not guarantee that PostgreSQL or the API is ready. Start
and verify PostgreSQL, then the API, then the UI. Manage PostgreSQL through its
own service, container supervisor, or managed database platform.

On a combined server, activate the units with:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now erms-api.service erms-session-cleanup.service erms-webui.service
sudo systemctl status erms-api.service erms-session-cleanup.service erms-webui.service
```

On separate servers, use only the service installed on that server. Logs and
routine lifecycle operations are independent:

```bash
sudo journalctl -u erms-api.service -f
sudo journalctl -u erms-webui.service -f
sudo systemctl restart erms-api.service
sudo systemctl restart erms-webui.service
```

Enabled services start at boot and run independently of SSH. Automatic restart
is subject to systemd start-rate limits; inspect the journal if repeated
failures leave a service stopped. See the
[systemd service reference](https://github.com/systemd/systemd/blob/main/man/systemd.service.xml).

## Verification and upgrades

Check the API's `/health` endpoint and the UI's `/` endpoint using addresses
reachable from the checking host. For a local deployment:

```bash
curl --fail http://127.0.0.1:8000/health
curl --fail http://127.0.0.1:8080/
```

These probes confirm HTTP availability; also verify login and an authenticated
API operation to exercise database-backed authentication. With multiple API
instances, verify that the same token works against each instance. With
multiple UI instances, verify the load balancer retains affinity through page
load and reconnects, and, if enabled, that shared user storage works across instances.

Back up PostgreSQL, including uploaded content, before schema upgrades. Deploy
compatible application versions and apply required migrations once. Drain
instances before planned restarts where possible. API requests in progress
can be interrupted, and UI restarts lose live page state even when Redis
preserves user storage. Database availability and capacity remain shared
dependencies; adding application instances alone does not provide database
high availability. Test restoring backups as part of operations.

## Temporary SSH deployment with tmux

For testing, `tmux` can keep the existing local stack running after SSH logout.
Install it using the Linux server's package manager, then run from the project
root:

```bash
tmux new -s erms
./run-local-stack.sh
```

Once ready, press **Ctrl+B**, release both keys, then press **D** to detach.
You can log out and later return with `tmux attach -t erms`. Reattach and press
**Ctrl+C** to stop services started by the script. The script preserves the
database volume and leaves services it reused running. See
[tmux's documentation](https://github.com/tmux/tmux/wiki/Getting-Started).

The local stack requires Docker, `curl`, and `psql`. Its automatic database
container uses development credentials and is intended for local testing.
`tmux` provides neither automatic boot startup nor restart after a crash. For
an ongoing deployment, use the separate systemd services and independently
managed database described above.
