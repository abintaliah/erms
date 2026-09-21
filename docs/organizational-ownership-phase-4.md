# Organizational ownership — Phase 4 completion

Phase 4 exposes organizational ownership as descriptive metadata and a
reporting dimension. It does not use ownership as an authorization boundary.

## API and user interface

- Aggregation and record create, read, update, list, search, and browse
  responses include the owning organizational unit's identifier, code, and
  name.
- Aggregation and record detail views display the owning organizational unit.
- List, structured-search, and classification-browse APIs accept an optional
  `owning_org_unit_id` filter. Authorization is applied independently, so an
  owner filter cannot reveal an otherwise inaccessible resource.
- Move previews identify whether the move changes ownership and return the
  source and destination owner identifiers for confirmation interfaces.
- The dashboard shows separate authorized aggregation and record counts for
  every organizational unit represented by the signed-in user's effective
  roles. Multiple roles in one unit produce one dashboard row. Explanatory text
  beneath the heading states both this effective-role scope and that counts
  include only resources the signed-in user is allowed to view.
- `GET /api/v1/dashboard/summary` consolidates overview counts,
  classification metrics, governance attention, organizational holdings,
  favourites, and hydrated self-only recent activity while holding one API
  database connection. The web UI performs one summary request per refresh,
  suppresses overlapping refreshes on the same page, and no longer performs
  per-card searches or per-activity-item hydration during dashboard loading.

The application has no separate server-side holdings-export operation at this
phase. Consumers exporting list, search, or browse results receive the same
owner fields in those authorized result rows and may filter them by owner.

## Verification

The Phase 4 API tests reconcile response metadata, list and structured-search
filters, classification browse filtering, dashboard counts, and the
consolidated summary against created resources. The full database and
application suite runs only against the test runner's fresh disposable
PostgreSQL container, which is removed on completion.

Phase 5 may now introduce the contextual `org_unit_members` ACL principal. It
must not reinterpret the Phase 4 owner field as a standalone access grant.
