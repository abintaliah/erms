# Automated native language acceptance

This test replaces the requested manual language-selection review with repeatable
native rendering and interaction checks. It runs production `WathiqApp`,
`SessionController`, password/sign-in widgets and canonical packaged catalogues.

The harness injects `AuthApi` and controlled Flutter platform-locale values. It
uses real phone simulator/emulator viewports without synthetic resizing. It does
not change persistent OS language settings, use real credentials, connect to ERMS
or alter any database. It verifies the application locale-resolution boundary and
native UI; it is not an end-to-end real-account or OS Settings test.

## Coverage

Each platform runs these cases:

| Controlled primary locale | Pre-preference language | Saved test-account language |
| --- | --- | --- |
| English | English/LTR | Arabic/RTL |
| Arabic, including initial AE regional locale | Arabic/RTL | English/LTR |
| French (unsupported) | English/LTR fallback | Arabic/RTL |

For each case, assertions cover sign-in copy/direction, live pre-auth locale
changes, mandatory-password access restrictions, minimum-length feedback,
confirmation mismatch, successful saved-preference override, immunity to later
device-locale changes, sign-out fallback and revocation fallback. Screenshots
capture sign-in, password feedback and the opposite-language authenticated shell.
Framework exceptions and paragraphs exceeding configured line limits fail the run.

## Run

Select a running phone target with `flutter devices`. From `frontend/MobileApp`:

```sh
flutter drive --driver=test_driver/language_driver.dart \
  --target=integration_test/language_acceptance_test.dart \
  -d <phone-target-id> --no-pub
```

`test_driver/language_driver.dart` saves PNGs and per-platform JSON summaries in
repository-root `.runtime/language-acceptance/`. Review the screenshots before
promoting evidence. The test needs the existing Flutter integration-test SDK
support; no new dependency or production API is introduced.

## Restore the normal app

`flutter drive` installs a test composition using the development app identifier.
After testing, rebuild normal `lib/main.dart` Android/iOS simulator apps using the
[README commands](../README.md#build-and-install-for-local-review), reinstall them
on the same targets and launch them. Do not leave the fixture composition installed
for real-account testing. No account reset is needed merely to restore the app.

## Evidence

The retained dated evidence and its scope are listed in
[the verification directory](verification/language-2026-11-17/README.md).
Current acceptance is tracked in [Phase 1 status](phase-1-progress.md).
