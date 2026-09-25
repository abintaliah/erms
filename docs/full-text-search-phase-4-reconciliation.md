# Full-text search Phase 4 reconciliation

## Outcome

Phase 4 is implemented and reconciled against the approved specification. The
authenticated Wathiq shell now provides explicit global search, governed result
cards, cursor continuation, query URL restoration, freshness/error/empty/loading
states, privileged diagnostics, and service-account API-key administration.

### Matched-component presentation contract

Record result cards are attribution views, not component inventories. They
render only digital components returned by the search service as matches for
the submitted full-text query. Each rendered component retains its escaped,
highlighted snippet and exposes the governed preview action. The client may
look up authorized metadata for an attributed component to determine whether
preview is currently available, but it must not use that lookup to append the
record's unmatched components. Preview rechecks current authorization through
the established viewer.

## Forward trace

- Sections 11–11.2 are implemented by the responsive header and the dedicated
  record/aggregation result renderer in `frontend/webui/app.py`.
- Section 11.3 is implemented by the service-only credential endpoints and the
  existing User details surface. Issuance returns a 256-bit opaque secret once;
  subsequent reads expose only safe metadata. Rotation supports immediate
  revocation or a maximum seven-day overlap.
- Section 11.4 is implemented as a privileged secondary action. It is off by
  default, affects only later explicit requests, displays exact sent and API
  accepted JSON, and retains sent JSON when the API is unavailable.
- FTS-08/09/15/30–32/36/42–46 have implementation and verification evidence in
  the traceability matrix.

## Reverse trace

Every Phase 4 addition maps to an approved requirement:

- the header input, URL query, cards, type filters and state treatments map to
  sections 11–11.2;
- credential schemas/endpoints/client methods/details UI map to section 11.3;
- diagnostics state, request flag, disclosure and copy controls map to section
  11.4; and
- responsive wrapping and safe snippet elements implement the explicit mobile,
  keyboard, and XSS constraints rather than introducing new product behavior.

No new resource type, access bypass, query language, result source, or durable
diagnostic preference was introduced.

## Verification evidence

- Frontend regression suite: 154 passed.
- Complete API and PostgreSQL integration suite: 261 passed on a uniquely named
  PostgreSQL 18 database initialized from `database/schema.sql`; cleanup
  completed. The focused Phase 3/4 subset also passed 8 tests during iteration.
- Live desktop search showed record attribution, containing aggregation,
  metadata-match state, matched component file name, highlighted snippet, and
  governed preview action without displaying unmatched components.
- A bookmark-style load with `?q=annual%20financial` restored the input and
  rendered the aggregation result.
- Privileged diagnostics were absent until enabled and an explicit rerun was
  submitted. The accepted panel showed the API request ID, query fingerprint,
  received body, and canonical query.
- With the API intentionally stopped, the UI retained **Sent to API**, marked
  **Accepted by API** unavailable, and rendered the connection error.
- At a 390-by-844 viewport the header used two rows and the final document
  `scrollWidth` equalled `innerWidth` (390 px). An initial JSON-panel overflow
  was found during this check, corrected, and reverified.
- The live service-account page displayed **Service account**,
  **Non-interactive**, the fixed internal-route label, governed Generate action,
  and deliberate empty state. Lifecycle API tests verified generate, list,
  rotate, revoke, one-time-secret non-retrievability, and person-account denial.

## Remaining scope

Phase 5 rollout remains intentionally unperformed. It covers deployment with
workers initially disabled, migration, controlled automatic indexing/backfill,
load and quality observation, and final header-search enablement. There are no
Phase 4 deferrals.
