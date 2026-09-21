# Organizational ownership — Phase 3 completion

Phase 3 makes organizational ownership a mandatory, database-enforced
invariant and keeps it consistent during creation and movement.

## Database guarantees

- `aggregations.owning_org_unit_id` and `records.owning_org_unit_id` are not
  nullable.
- A child aggregation derives its owner from its parent, regardless of a
  supplied value.
- A record derives its owner from its containing aggregation.
- Direct owner updates are rejected.
- Moving a record derives the destination aggregation's owner.
- Moving an aggregation across owners updates the entire descendant subtree
  and all contained records in the same transaction.
- Ownership-changing moves require a nonblank reason and an explicit
  transaction confirmation context.
- Parent rows are locked while ownership is derived, preventing a concurrent
  parent move from producing a stale owner.
- Ordinary row-history triggers preserve creation and movement ownership,
  including org-unit identity snapshots and the supplied reason.

## API behavior

Ordinary aggregation and record patch endpoints continue to support moves
within the same organizational unit. They reject cross-owner moves and direct
the caller to the ACL-aware move command.

The ACL-aware move request now accepts `confirm_ownership_change`. It is
required only when the source and destination owners differ; `reason` remains
mandatory for that command. Its domain event records the old and new owner.

The Phase 6 **Create for** selector is intentionally not introduced early.
Until Phase 6, root creation derives ownership when the caller's effective
roles resolve to exactly one organizational unit. If several units are
possible, the API returns `root_owner_selection_required`. Child and record
creation remains unambiguous because ownership comes from the parent.

Ownership remains internal to API responses until the Phase 4 presentation
contract is implemented.

## Verification

The disposable database suite covers mandatory columns, schema parity,
creation derivation, direct-change rejection, failed-move rollback, confirmed
record moves, recursive aggregation-subtree propagation, and immutable history.
The application suite passes 195 of 196 tests. The sole remaining failure is
the pre-existing generated UI policy-inventory line-number drift documented in
the Phase 2 completion report; Phase 3 does not modify that UI source or
registry.
