# Security and authorization implementation — Phase 6

Status: implemented and verified

This phase makes governed information non-disclosing on every general read and discovery path. Aggregations, records, and digital-component metadata are visible only after the caller passes the approved effective-role, global-privilege, maximum-clearance, and live ACL gates. An effective information-governance role bypasses only the ACL gate and must itself satisfy the resource clearance.

## Set-based database policy

Migration 035 installs stable PostgreSQL predicates for global privilege, aggregation ACL resolution, record ACL resolution, resource visibility, component-metadata visibility, and audit visibility. The predicates use the authenticated user ID stored in the transaction-local database context.

Aggregation ACL resolution follows the live Phase 5 model. It walks an inheriting aggregation chain until it reaches a custom child template or a local effective resource ACL; it never copies or merges dormant overrides. Record access resolves either the local record override or the containing aggregation's live default child-record ACL.

The normal authorization path requires:

1. an active user with at least one effective role assignment;
2. the relevant global view privilege from any effective role;
3. maximum effective clearance at or above the resource level; and
4. the required permission through Everyone or any effective role in the effective ACL.

Contributions may come from different effective roles. A lower-clearance role does not veto a higher-clearance role. Governance bypass is accepted only from an effective information-governance role whose own clearance covers the resource; it does not bypass the global privilege or clearance gates.

## Non-disclosing read surfaces

Visibility predicates are composed into SQL before counting, sorting, cursor evaluation, offset, or limit. This applies to:

- direct aggregation, record, and digital-component metadata retrieval;
- ordinary lists and advanced searches;
- classification and aggregation browse trees, node summaries, child counts, and record counts;
- favourite aggregation and record lists and attempts to create a favourite;
- ACL administration resource lookup;
- entity histories and global audit history; and
- record component listings and component searches.

A known but inaccessible resource returns the same public `404` body as an absent resource. Lists, trees, favourites, counts, and searches silently omit inaccessible entries. Filtering by a protected parent returns no results when that parent is unavailable.

Relationship fields are also protected. When a record or child aggregation is visible but its containing aggregation is not, the protected parent identifier and parent label are returned as null. Advanced-search projections apply the same rule before evaluating relationship filters, so a guessed parent ID cannot be confirmed through totals or pagination.

The generic relationship redactor resolves all referenced parents in one bounded set query regardless of page size. List and search authorization is likewise embedded in the set query rather than evaluated with one database call per result.

## Digital-component metadata

Component metadata requires all record-view gates plus the global `record.component.view` privilege and effective `record.component.list` ACL permission. Governance officers may bypass the component ACL only under the same clearance rule. Component lists, direct metadata reads, and searches therefore cannot reveal file names, types, checksums, sizes, or counts for unavailable records.

## Audit history

Global audit viewers retain the immutable event envelope, but governed snapshots, changed fields, reasons, and metadata are redacted when the resource is outside their effective access. The safe metadata identifies the row as redacted without explaining ACL structure.

For a deleted resource, no live ACL remains. A caller with `audit.view` may see its historical snapshots only when the caller's current maximum clearance covers the security level captured in the immutable event snapshot. Otherwise only the redacted envelope is returned. Entity-history routes retain audited deletion history under the same rule while an unrelated or unknown identifier remains `404`.

## Capability endpoints

Current-user capability endpoints are available for aggregation and record details. They use the same non-disclosing resource lookup and therefore return `404` for hidden resources. Aggregations expose current view capability; records additionally expose whether component metadata may be listed. Phase 7 extends these responses while enforcing mutation operations.

## Verification

The complete database and API gate ran against a newly created disposable PostgreSQL database, which the harness removed cleanly afterward. The cross-user matrix verifies:

- identical `404` behavior for hidden and absent IDs;
- omission from lists, searches, totals, browse summaries, favourites, and component metadata;
- redaction of protected audit snapshots;
- maximum-clearance union semantics without a lower-role veto;
- protected relationship projection; and
- a database-query count that remains constant as relationship result size grows, rejecting an N+1 implementation.

The disposable database/API suite passed 158 tests. The Web UI suite passed 65 tests. Canonical/upgrade schema parity, policy-inventory regeneration, Python compilation, and diff validation also passed.

## Deliberately deferred

Phase 6 governs reads and discovery. Phase 7 applies operation-specific global privileges, security checks, resource permissions, source/destination checks, closed-aggregation rules, governance exceptions, and complete mutation capability responses.
