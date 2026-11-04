# Post-upgrade mobile compatibility review — 4 November 2026

Reviewed mobile revision `5ee545f` against main revision `0cfd587` after the
authorized local `erms` database upgrade. This records findings only; no main
integration or compatibility fixes are included. Phase 1 remains in progress.

## Saved database upgrade

- Applied all 42 missing migrations, 053 through 094, in order.
- All 55 current application settings validate; previous values, versions and
  provenance are unchanged.
- Required feature seeds were reconciled separately. Canonical comparison found
  no missing privileges, permissions, profiles, languages, security levels,
  application-setting keys, profile grants, or privilege/permission dependencies.
- Resource counts are unchanged: 11 users, 12 roles, 404 aggregations,
  1,603 records and 3,202 digital components.
- English definitions and missing-only Arabic drafts were synchronized:
  3,974 active keys, 1,617 drafts stored, 2,357 existing translations protected,
  zero corrections, failures or entries awaiting generation. Drafts remain
  subject to human review; no translation export was promoted.
- Notification readiness passes without issues. Four packaged default document
  templates are available. Disposition destinations retain their intentionally
  unset defaults and require administrator selection before operational use.
- Private backup, companion environment/key backup, receipts and comparison
  reports are retained under `.runtime/db-upgrades/20261104T051212Z/`.
  These files must remain outside source control. A local Git exclude protects
  them on this older branch until main's ignore rule is integrated.
- The disposable canonical-reference database was dropped successfully. The
  initial reference creation attempt using the application role was denied;
  verification succeeded using the local maintenance role instead.
- No test suite targeted the persistent database. Settings diagnostics and
  readiness inspections were read-only; the documented migration and seed
  operations were the authorized writes. Services remain stopped.

## Findings requiring integration or correction

1. **Startup blocker: old settings registry rejects the upgraded database.**
   `backend/services/api/application_settings.py` requires an exact registry
   match. The branch has 51 keys; migration 088 brings the database to 55.
   A read-only call to `load_snapshot` reproduced
   `SettingsInvalid: application_settings_registry_mismatch`.
   Integrate main's registry and consumers, including
   `DISPOSITION_ORGANIZATION_NAME`, `DISPOSITION_RECORDS_UNIT_EMAIL`,
   `DISPOSITION_RECORDS_UNIT_PHONE`, and `DISPOSITION_REQUEST_LANGUAGE`.
   Do not remove database settings or relax validation to run old code.

2. **Catalogue integration must precede restarting this branch's API.**
   Main has 3,974 English keys; this branch and its bundled mobile assets have
   3,202. Startup synchronization deprecates database definitions absent from
   the checked-in manifest, so running the older manifest after bypassing the
   registry failure would deactivate newer main-only definitions.
   Merge canonical artifacts by message key using main's current Arabic artifact
   as the base, preserving wording and provenance. Retain the ten mobile-only
   definitions (nine `mobile.*` keys and `audit.source.mobile`), while keeping
   the two retired `privilege.user.modify_metadata.*` keys removed. With the
   reviewed inventories this yields 3,984 keys. Synchronize both mobile assets
   and verify coverage, order, placeholders, terminology, stale keys and hash.

3. **User translation authorization still references a removed privilege.**
   `backend/services/api/entity_translations.py` uses `user.modify_metadata`.
   Migration 090 removes that privilege; its absence was verified read-only.
   Integrate main's `identity.users.administer` check and matching WebUI changes.
   Do not recreate the retired privilege or elevate its former holders.

4. **Mobile search availability uses the obsolete environment source.**
   `authentication.mobile_capabilities` calls
   `boolean_environment("FULL_TEXT_SEARCH_ENABLED", True)`. The current API and
   WebUI use the database-backed setting. Update the existing approved endpoint
   to use the validated settings snapshot so mobile navigation follows Settings
   changes. Replace its environment-monkeypatch regression with database-backed
   enabled/disabled checks, exclusively in disposable databases.

## Mobile contracts to retain during integration

- Main does not yet include `/api/v1/auth/me/mobile-capabilities`; the mobile
  client depends on it during authentication and revalidation. Preserve the
  approved route, credential-change gate and destination identifiers. Deploying
  the mobile client against main alone would leave the capability request
  without its route.
- Retain the governed `mobile` audit source and labels, native device-model
  adapters, model-aware HTTP headers and both WebUI session presenters.
- Main adds disposition capability fields to the principal response. The
  existing Flutter parser reads its required fields and tolerates additional
  fields; Phase 1 does not require new disposition destinations.
- New resource/disposition fields affect later content phases. Revisit their
  current contracts when implementing those phases rather than extending
  Phase 1 scope.
- Keep approved 15-minute expiry / 10-minute warning; full-duration device
  acceptance and the previously recorded Phase 1 evidence gaps remain open.

## Review evidence and next step

- All 61 database-free Flutter tests passed on the reviewed branch.
- All 11 database-free WebUI session-presenter tests passed.
- Compared authentication, principal schemas, translation authorization,
  settings registry, canonical manifests and mobile source references across
  both revisions. None of the mobile-used keys shared with main changed its
  English source text.
- During the prior upgrade, API environment-template and configuration-authority
  checks passed. The historical disposition acceptance-ledger audit failed on
  stale source references and missing recorded evidence files; no passing
  release-audit claim is made.

Next: integrate main into this branch, resolve the four findings while
preserving mobile contracts, then run catalogue checks, Flutter analysis/tests,
native builds and focused backend compatibility tests in uniquely named
disposable databases. Verify authenticated English/Arabic behavior against the
integrated code before resuming Phase 1 acceptance. Do not roll back the
database to accommodate this older checkout.
