# Organizational ownership — Phase 2 completion

Phase 2 implements deterministic ownership assignment for holdings that exist
when migration `045_assign_existing_organizational_ownership` is applied.

## Implemented behavior

- Only active roles in active, non-system organizational units are eligible.
- Each root aggregation is scored using stable tokens from its title and
  description against the role and organizational-unit code, name, and
  description.
- A unique highest score selects that role directly.
- Equal best scores are distributed reproducibly using root order and stable
  eligible-role order.
- Roots with no textual match are distributed by the same stable rule.
- The selected organizational unit is propagated to every descendant
  aggregation and contained record.
- The migration aborts transactionally for missing eligible roles, hierarchy
  cycles, unreachable aggregations, orphan records, incomplete propagation, or
  count reconciliation failures.

## Retained evidence

`organizational_ownership_assignment_runs` retains migration totals and
before/after counts by organizational unit.

`organizational_ownership_root_assignments` retains each root's selected role,
derived organizational unit, match score, selection method, and identity
snapshots. Root, role, and organizational-unit IDs are deliberately historical
values rather than foreign keys so this migration report does not introduce
new lifecycle or deletion restrictions.

## Scope boundary

This phase changes existing ownership metadata only. It does not make ownership
mandatory, enforce parent equality for future writes, modify ACLs, expose owner
fields to clients, or change resource placement. Those behaviors remain in
later phases.

## Verification

The disposable-database suite verifies the upgrade path, canonical-schema
parity, scored selection, descendant and record propagation, retained identity
snapshots, before/after reconciliation, and absence of ownership diagnostics.
All 195 behavior tests unrelated to the repository's pre-existing stale UI
policy inventory pass. The remaining inventory test reports line-number drift
between `frontend/erms_nicegui/webui/app.py` and the committed generated
registry; Phase 2 changes neither file.
