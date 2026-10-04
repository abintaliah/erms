# Notifications and messaging — Phase 3 report

Specification: `specs/notifications-and-messaging.md`, approved revision 1.20.
Scope: §16.3, Real-time and multi-instance distribution. Verification date: 3 October 2026.

**Status: implementation and functional validation complete.** Arabic additions
await the normal administrator review, as described below.

## Implementation

Delivery inserts now emit a PostgreSQL notification that becomes visible only
when the transaction commits. Each API worker maintains one dedicated,
autocommit PostgreSQL listener outside the request pool. Listener interruption
triggers bounded reconnection and asks every connected consumer to reconcile.
Shutdown closes the listener socket and explicitly prevents reconnection.

Authenticated WebSocket and SSE endpoints carry the same versioned, frontend-
neutral event contract. Connections are bound to the authenticated recipient;
clients cannot choose another user or subscribe to an arbitrary mailbox.
Session expiry/revocation and current delivery visibility are checked before
sending hints and at heartbeat intervals. Heartbeats do not renew idle sessions.
Cookie-authenticated WebSocket upgrades require a matching Origin. Bearer
tokens are accepted in headers; query-string credentials are rejected.

The NiceGUI adapter subscribes before reading durable catch-up pages. It uses
WebSocket first and SSE after transport failure, retrieves authoritative unread
counts, and shows one summary for recovered messages. Fresh messages produce
one actionable toast in every connected page. Opening it uses the normal,
authorized message view. Duplicate/out-of-order hints do not repeat presentation.
Unknown event types or versions trigger reconciliation. PostgreSQL remains the
source of message content, visibility, read state, and delivery sequence.

Every page has its own adapter and HTTP client. Ordinary navigation cannot cancel
its catch-up requests. Disconnect/sign-out cancels the adapter, closes its HTTP
client, and dismisses notifications. Identity guards discard late responses.
There is no shared message-content cache. The only browser checkpoint is an
integer cursor in tab-local sessionStorage, keyed by user ID and a hash of the
login session token. It advances only from the REST catch-up response. Reloads
reuse it; another identity/session gets a separate key. Storage failure falls
back to durable reconciliation; the in-memory cursor prevents repeated toasts
within the existing page. Language is resolved in the current page's localization
context, and message content is fetched under current authorization.

## Requirement traceability

Backend test names below refer to `backend/services/api/tests/test_messaging_phase3.py`.
Frontend tests are in `frontend/webui/tests/test_messaging_live.py`.

| Requirement | Implementation | Verification |
| --- | --- | --- |
| Commit-only notification; rollback silence (§9, §16.3) | Migration 035 and equivalent canonical trigger | `test_cross_instance_all_connections_postcommit_rollback_and_listener_recovery` |
| Dedicated listener outside request pool; recoverable failure (AC-MSG-014, 014A) | `messaging/realtime.py`, API lifespan, direct connection, autocommit, bounded backoff | Listener termination with live sockets and subsequent reconciliation; `test_idle_listener_shutdown_is_bounded`; normal preview shutdown |
| Authenticated recipient isolation and transport equivalence (AC-MSG-019, 020) | `/api/v1/messages/stream/ws`, `/stream/sse`; common authentication, visibility and event construction | `test_websocket_sse_equivalence_authentication_and_session_revocation`; outsider denied delivery in cross-instance test |
| Every connected tab/device across independent instances (AC-MSG-011, 017) | Per-process subscriber registry; PostgreSQL fan-out; one adapter per page | Three recipient sockets across two API processes; two independent frontend consumer processes; live two-NiceGUI-instance test with two recipient tabs |
| Catch-up across startup/listener/API/frontend gaps (AC-MSG-012–014, 018) | Initial/reconnected reconciliation handshake; bounded REST pages and safe cursors | `test_gateway_startup_during_commits_reconciles_every_delivery`; cross-instance listener recovery; `test_two_frontend_processes_duplicate_hints_and_api_frontend_restart`; frontend persisted-cursor and fallback tests; live reload |
| Duplicate idempotence and accurate counts (AC-MSG-015) | Durable cursor comparison; unread-count endpoint | Repeated explicit NOTIFY hints; frontend duplicate/out-of-order and storage-failure tests; live count increments and read decrement |
| Bounded slow-client handling (AC-MSG-023) | Per-process/per-user connection limits, bounded queue, send deadline, overflow disconnect, cleanup | `test_bounded_queues_slow_client_isolation_and_unknown_payloads` |
| LTR/RTL toast and opening behavior (AC-MSG-024) | Native NiceGUI notification, localized actions, standard message workspace | Live English/Arabic cross-instance delivery, Open, unread count and reload; screenshots in `docs/verification/messaging-phase-3/` |
| Translation fidelity (AC-MSG-025) | Four contextual live-message keys; sorted EN/AR artifacts, preserved existing provenance | Catalogue checker and messaging translation artifact regression |
| UI performance and abandonment | Separate live HTTP client; bounded 50-row catch-up pages; no repeated mailbox polling while stream is healthy; active identity guard | Frontend reconciliation/abandonment tests; existing relationship/capability/interaction suites; live navigation and reload |

## Transport and operations

The WebSocket URL is `/api/v1/messages/stream/ws`. SSE uses
`GET /api/v1/messages/stream/sse`, with JSON in `data:` frames. Both initially send
`{"schema_version":1,"event_type":"reconciliation_required"}`. Heartbeats use
`event_type: "heartbeat"`. A message hint contains exactly:

```json
{"schema_version":1,"event_type":"message_available","delivery_id":"<uuid>","mailbox_cursor":1}
```

Hints contain no subject, body, recipient list, or user ID. Consumers use existing
`/catch-up?after=<cursor>&limit=50` and `/unread-count` endpoints. SSE does not treat
Last-Event-ID as a durable delivery guarantee. Clients must reconcile on every
connection gap and on unknown contract versions/types.

`/health` includes `messaging_realtime.listener_connected` and
`listener_generation`. Listener failure does not make the durable Inbox unavailable.
The SSE route is recorded as relationship-scoped in the operation policy registry.
WebSocket routes are outside OpenAPI's HTTP-operation inventory and enforce their
session/ownership rules directly in the shared real-time module.

Defaults in `.env.example`: 1,000 connections per API worker, 20 per user per
worker, 64 queued hints per connection, 15-second heartbeat, and 5-second send
timeout. Overflow disconnects only the slow connection; reconnection catches up
from PostgreSQL. Reconnection backoff is bounded at 30 seconds. Deployments must
budget one additional database connection per API worker. When request connections
use a transaction pooler, set `MESSAGING_LISTENER_DATABASE_URL` to a direct or
session-pooled connection to the **same database**. Reverse proxies must allow
WebSocket upgrades, disable SSE response buffering, and permit idle intervals
longer than the configured heartbeat.

Migration `035_messaging_live_signals.sql` upgrades an existing Phase 2 database.
`database/schema.sql` independently contains the same DDL and never invokes a
migration. No persistent database was migrated during implementation.

## Verification results

- **77 passed** in the final combined backend run: Phase 1, Phase 2, Phase 3,
  policy inventory, global privilege enforcement, and translation artifact checks.
- **1 additional test passed** in a separate disposable run for the explicit
  gateway-startup/commit race, added after the combined run had collected tests.
  The Phase 3 integration file now contains six tests.
- **30 frontend unit tests passed**, covering the six live adapter regressions
  plus existing relationship-search and capability tests.
- **11 NiceGUI interaction tests passed**, covering messaging and shared security
  selectors.
- Fresh canonical initialization and populated-predecessor upgrades through
  migrations 033–035 produced identical schema dumps and preserved existing data.
- Catalogue references, EN/AR active-key coverage, ordering, placeholders,
  nonblank values, artifact hash, and preserved curated provenance passed.
  `git diff --check` and Python compilation passed.

Live verification used two API and two NiceGUI processes against one disposable
database. A message sent through instance A produced one toast in each of two
recipient tabs on instance B, including a tab outside the Inbox. The Inbox refreshed
without navigation, unread count increased from 14 to 15, and the toast opened
the exact message and reduced that tab's count to 14. Arabic repeated the send,
toast, Open, content and count checks in RTL. Reload retained the checkpoint and
showed no repeated summary. A fresh Arabic tab produced one summary for 14
existing messages; its localized Open and Close actions rendered correctly and
Close dismissed it. Screenshots include `live-ltr.png`, `opened-ltr.png`,
`opened-rtl.png`, and `summary-rtl.png`.

Browser setup exposed an idle-listener shutdown loop: socket cancellation could
surface as a reconnectable connection error. Explicit shutdown state and socket
closure corrected it, and the bounded-shutdown test plus normal preview shutdown
verified the fix. RTL inspection also exposed the notification component's default
English Close label; the fourth contextual translation key corrects it.

Database-backed tests use `tools/test_messaging.py`, which creates
unique disposable fresh/upgrade databases, compares schema dumps, checks existing-
data preservation, runs the complete test process against the disposable database,
and drops both databases in a finally block. It also overrides the optional
listener DSN so subprocess listeners cannot escape test isolation.

All disposable databases created for these runs were dropped, including the
interrupted preview attempts used to diagnose shutdown. Final combined/preview
databases `erms_messaging_test_69af7f504c1b42dc_fresh` and
`erms_messaging_test_1d00caea3a704589_upgrade` both reported successful removal;
the runner exited with status 0. The startup-race run likewise removed both of
its databases. Browser tabs and preview processes were closed. No database
creation or cleanup failures remain.

Reproduction commands (run frontend unit and interaction suites separately):

```sh
backend/services/api/.venv/bin/python tools/test_messaging.py \
  backend/services/api/tests/test_messaging.py \
  backend/services/api/tests/test_messaging_phase2.py \
  backend/services/api/tests/test_messaging_phase3.py \
  backend/services/api/tests/test_policy_inventory.py \
  backend/services/api/tests/test_global_privilege_enforcement.py
frontend/webui/.venv/bin/python -m pytest -q \
  frontend/webui/tests/test_messaging_live.py \
  frontend/webui/tests/test_relationship_search.py \
  frontend/webui/tests/test_capabilities.py
frontend/webui/.venv/bin/python -m pytest -q --asyncio-mode=auto \
  frontend/webui/interaction/tests/test_messaging_workspace.py \
  frontend/webui/interaction/tests/test_security_level_selector.py
frontend/webui/.venv/bin/python frontend/webui/scripts/check_i18n_catalogue.py
```

Add `--preview-multi` to the backend command for disposable two-instance browser
verification. Use `localhost:18081` and `127.0.0.1:18082` so browser cookies for
the independent frontend secrets remain isolated. Ctrl-C performs cleanup.

## Remaining work and limits

Four new Arabic values (`messaging.live.close`, `.new_message`, `.summary`, `.unread`)
are generated drafts requiring the normal administrator review. All prior Arabic
wording and provenance are preserved. Browser verification publishes fixture copies
only in disposable databases. The two previously reported curated terminology
findings in `classification_transfer.error.checksum_mismatch` and
`classification_transfer.retention_rule` remain unchanged.

The test dependencies still emit the existing Starlette/httpx and AnyIO portal
deprecation warnings. These do not fail the tests.

This phase supplies the live transport for human messaging. System notification
registry/administration, capture, retention/purge execution, and production rollout
remain in their approved later phases. This report does not declare the entire
subsystem production-ready.
