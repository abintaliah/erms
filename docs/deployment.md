# Linux deployment

ERMS has three independently managed components: the FastAPI backend, the
NiceGUI web UI, and PostgreSQL. Use separate systemd units for the API and UI
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

Install Python 3.11 or newer with virtual-environment support, and place the
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
AUTH_COOKIE_SECURE=true
```

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

Example `/etc/erms/webui.env`:

```ini
WEBUI_API_URL=http://127.0.0.1:8000
WEBUI_HOST=127.0.0.1
WEBUI_PORT=8080
WEBUI_RELOAD=false
WEBUI_STORAGE_SECRET=REPLACE_WITH_A_STRONG_RANDOM_SECRET
```

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
- [`api.env.example`](../backend/services/api/deploy/api.env.example)
- [`webui.env.example`](../frontend/webui/deploy/webui.env.example)

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
sudo install -m 0600 backend/services/api/deploy/api.env.example /etc/erms/api.env
sudo install -m 0600 frontend/webui/deploy/webui.env.example /etc/erms/webui.env
sudoedit /etc/erms/api.env /etc/erms/webui.env
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
```

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
