# Mobile documentation guide

Start here when taking over Wathiq Mobile. This guide describes where to find the
current contract, implementation, verification and historical decisions.

| Document | Purpose |
| --- | --- |
| [Mobile specification](../../../specs/flutter-mobile-application.md) | Approved product contract; changes here require user approval |
| [Project README](../README.md) | Toolchain, supported platforms, local setup, builds and test commands |
| [Phase 1 status](phase-1-progress.md) | Maintained status, acceptance limits and the remaining handoff work |
| [Architecture](architecture.md) | Current ownership, authentication/language sequence, session and failure boundaries |
| [Validation matrix](validation-matrix.md) | Requirement → implementation → concrete test/evidence mapping |
| [API inventory](existing-api-inventory.md) | Phase 1 calls and API ownership for later work |
| [November integration review](integration-review-2026-11.md) | Fork integration, refactoring effects, local migrations and resolved compatibility findings |
| [Phase 2 API snapshot](phase-2-api-map.md) | Historical preparation; must be refreshed before implementation |
| [Automated language acceptance](language-acceptance.md) | Repeatable native phone tests, fixture scope, screenshots and normal-app restoration |
| [Tablet acceptance](tablet-acceptance.md) | Native test procedure and its deliberately limited evidence scope |
| [History](history/README.md) | Retained chronological records and superseded decisions |

## Reading status correctly

The specification is the product authority. Architecture documents explain the
current implementation; dated status/evidence reports do not introduce new
requirements. A historical test pass does not establish that a later build was
manually reviewed. An automated test, successful build/install, user-reported
acceptance and waived test are different evidence types.

Phase 0 and Phase 1 were approved complete. The November follow-up corrections
are documented in the maintained status and validation matrix. Historical
"Phase 1 open" statements belong to earlier revisions and must not be treated as
a new backlog. Phase 2 feature implementation has not started.

## Maintaining these records

Update the status document and affected validation rows when a behavior, test or
acceptance outcome changes. Keep one current row per implemented requirement;
add historical evidence to the history record instead of prepending another
contradictory status narrative. Record test dates/counts as observations rather
than permanent release guarantees. Do not copy credentials, private environment
values, session tokens or captured operational logs into these documents.

For translations, publication in a local database and promotion into the
source-controlled artifact are separate steps. Follow the procedure in the
[Phase 1 handoff](phase-1-progress.md#remaining-handoff-work). Never replace a
newer administrator export with regenerated wording.
