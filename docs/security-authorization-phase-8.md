# Security and authorization implementation — Phase 8

Status: implemented and verified

Phase 8 protects the complete record-draft and digital-component lifecycle and implements the approved, narrowly scoped information-governance correction for placing a record into an effectively closed aggregation.

Practical profile and ACL combinations for creation-time and post-commit access
are collected in [Authorization configuration scenarios](security-authorization-scenarios.md).

## Database policy

Migration 037 installs reusable PostgreSQL predicates for destination child-record permissions, component operations, and active draft ownership. It also replaces the closed-record trigger with a fail-closed implementation that recognizes a transaction-local correction context only for record creation or a pure change of containing aggregation. Ordinary inserts, moves, metadata changes, deletion, and component/content changes in a closed branch remain blocked.

The canonical schema, incremental migration runner, clean-reset fixture, schema-parity check, and disposable test harness include migration 037.

## Record drafts

- A draft belongs to one active person and is concealed from every other user, including administrators.
- Only its owner may view, edit, stage/reorder/remove components, commit, or discard it.
- Every draft operation requires the owner's current `record.create` privilege. Draft metadata and staged files are one record-creation package.
- Commit re-evaluates the current profile, role assignment, clearance, destination `aggregation.add_record` permission, and closure state. Authorization captured when the draft was opened is never trusted.
- Staging and committing files with a new record does not require `record.component.add`. That privilege, and the other `record.component.*` privileges, govern changes only after the record has been committed.
- A draft without an explicitly selected security level receives the lowest configured level at commit, consistent with ordinary record creation.
- A failed commit leaves the draft and its staged components intact and creates no record or promoted content.

## Digital components

Component metadata enumeration requires record visibility plus `record.component.list`. The API independently enforces the matching global privilege and effective record permission for preview, download, add, replace, remove, and reorder.

Replacement is an atomic operation governed solely by `record.component.replace`; add and remove rights cannot be combined to simulate it. Authorization and optimistic-version checks occur before upload bytes are staged. PostgreSQL storage and metadata updates remain in one transaction, so denial, stale versions, validation failures, or storage errors cannot leave committed orphan rows or blobs.

Component metadata edits use replacement authorization. Changing a component's owning record through the metadata endpoint is rejected; no implicit component-move operation exists. Share and print remain explicitly unavailable in capability responses because no governed implementation exists yet.

## Closed-aggregation correction

`POST /api/v1/records/{id}/correct-placement` is separate from the ordinary move operation and requires:

- ordinary `record.move` privilege and source-record permission;
- `closure.correct_record_placement`;
- an effective information-governance role whose own clearance covers the record and destination;
- a destination that is effectively closed;
- the normal security hierarchy invariant and optimistic version;
- a nonblank `X-Change-Reason`.

The correction changes only the record's containing aggregation. It does not reopen the destination or alter any closure date. The event `CLOSED_AGGREGATION_RECORD_CORRECTED` records source and destination, the effective closure source and date, confirmation that the date was unchanged, the reason, and the qualifying governance-role snapshot.

The same policy is available when committing a completed draft through the explicit `commit-placement-correction` endpoint. The ordinary commit and ordinary move endpoints continue to reject closed destinations.

## Capabilities and policy inventory

Record capabilities now expose component list, preview, download, add, replace, remove, and reorder decisions. Share and print return `false`. The generated operation-policy registry is advanced to Phase 8 and records enforcement for draft, component, correction, and record-capability routes.

## Verification

The complete database/API suite ran against a newly created disposable PostgreSQL database and passed all **169 tests**. The harness disposed of the database cleanly afterward. Phase 8 regression tests verify:

- owner-only drafts and commit-time policy re-evaluation;
- component concealment from metadata-only record viewers;
- replacement cannot be obtained through add/remove permissions;
- denied replacement leaves the original bytes unchanged;
- governance correction preserves the closure date and produces its dedicated audit event; and
- schema parity between canonical installation and incremental migrations.

The Web UI regression suite also passed all **65 tests**. Python compilation and diff validation passed.

## Deliberately deferred

Phase 9 implements authorization explanations and the administrative diagnostics needed to answer why a user is allowed or denied. Full end-user authorization management and correction-flow presentation remain part of the later UI phase; the Phase 8 API and capability contract are authoritative and ready for those interfaces.
