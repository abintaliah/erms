# Native language acceptance — 17 November 2026

Both native runs passed at the user's request to automate the language review
before committing and pushing. This replaces the pending manual checkpoint with
explicitly scoped automated evidence; it does not claim a manual device pass.

| Target | Actual logical viewport | Controlled primary locales | Result |
| --- | --- | --- | --- |
| Wathiq Pixel 8 API 36 emulator | 411.43 × 914.29 | English, Arabic, French/unsupported | Passed |
| iPhone 18 Pro iOS 27 simulator | See `ios-results.json` for the measured viewport | English, Arabic, French/unsupported | Passed |

Production widgets, controllers and canonical catalogues run on native phone
targets without viewport resizing. The harness controls Flutter platform-locale
values and injects `AuthApi`. It does not change persistent OS settings, use real
accounts or connect to ERMS/PostgreSQL. This verifies application resolution,
rendering and interactions at that boundary; it is not a live-account backend or
OS Settings propagation test. Existing HTTP/backend contract tests cover their
separate boundaries.

Each run verifies device fallback, live pre-auth locale changes, the mandatory
password gate, localized minimum-length/confirmation errors, saved-preference
override, resistance to later device-language changes, and sign-out/revocation
fallback. Native framework/line-overflow assertions passed. Representative Arabic
sign-in, field-error and saved-language shell screenshots were visually reviewed
without clipping or overflow.

The nine screenshots per platform cover sign-in, password feedback and saved-
language shell for each primary locale. `android-results.json` and
`ios-results.json` list every case/check and screenshot. `manifest.json` retains
the tested base revision, working-tree source hashes and evidence hashes; the
working-tree changes were included in the test, not only the base commit.

The normal development apps must be restored after this test composition. See
the [repeatable procedure](../../language-acceptance.md). Current status and
restoration results are maintained in [Phase 1 status](../../phase-1-progress.md).
