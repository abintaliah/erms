# Legal holds implementation traceability

This file is the release gate for `specs/legal-holds.md`. A requirement is
complete only when its implementation and automated verification are both
identified here. “Implemented” without a passing test is not release-ready.

| Spec acceptance criterion | Implementation evidence | Automated evidence | Status |
|---|---|---|---|
| 1. Effective-period boundaries | SQL effective-hold functions | `database/tests/legal_holds.sql` | Covered |
| 2. Overlapping holds | SQL effective-hold functions | `database/tests/legal_holds.sql` | Covered |
| 3. Arbitrary-depth inheritance | recursive SQL functions | `database/tests/legal_holds.sql` | Covered |
| 4. Effective-hold deduplication | grouped SQL functions | `database/tests/legal_holds.sql` | Covered |
| 5. Held movement authority and audit | resource protection triggers/API authorization | Pending expanded test | Open |
| 6. Resource/component mutation blocking | database triggers | `database/tests/legal_holds.sql` | Covered |
| 7. Disposition integration | capability/Access Explainer contract pending disposition subsystem | API tests | Covered as integration gate |
| 8. Enhanced state preservation | database triggers and capabilities | `database/tests/legal_holds.sql`, API tests | Partial |
| 9. Atomic mixed updates | database transaction enforcement | Pending expanded API test | Open |
| 10. Delete non-empty hold | DB FK plus stable API `hold_not_empty` | API test | Covered |
| 11. Remove-all direct only | resource-centric API | API test | Covered |
| 12. Authorization separation | hold visibility, `holds.administer`, owner authority, `holds.held_items.manage_all` | authorization tests | Covered |
| 13. Held-item management authority | active owner/contributor, hold administrator, or global held-item manager; atomic remove-all | SQL/API tests | Covered |
| 14. Non-disclosure | visibility-filtered queries and redacted effective holds | API tests | Partial |
| 15. Optimistic concurrency | hold and contributor `If-Match`; assignments | Pending assignment version test | Open |
| 16. Race safety | advisory locks and row locks | Pending concurrent DB tests | Open |
| 17. Complete event history | hold/domain triggers | Pending event expansion and tests | Open |
| 18. Server filtering/sorting/paging | paged Holds and held-items APIs/UI | API/UI tests | Covered |
| 19. Mandatory mutation reasons | API reason gate/event context | API tests | Covered |
| 20. Direct held-item list and Open action | Holds held-items endpoint/detail UI | UI tests | Covered |
| 21. Complete UI states/actions | Holds and resource detail views | browser E2E | Partial |
| 22. Access Explainer | governance authorization constraints/UI | API/UI tests | Partial |

## Change control

Every future legal-hold change must update this matrix in the same commit. A
review may not declare a phase or release complete while any applicable row is
`Open` or `Partial`. Each new normative requirement must receive a stable ID,
implementation reference, and automated acceptance test before implementation
is considered complete.
