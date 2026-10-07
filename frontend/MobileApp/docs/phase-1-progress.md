# Phase 1 progress record

Status: In progress

Started: 30 September 2026

## Completed

- English/LTR and Arabic/RTL authentication and application-shell mockups were
  approved with the canonical WebUI logo refinement.
- The existing `/api/v1/auth/login`, `/me`, `/change-password`, and `/logout`
  contracts are represented by an injectable mobile authentication boundary.
- Principal, role, privilege, session, and required-password-change response
  fields are parsed through typed models with malformed-response rejection.
- Session tokens and protected principal state remain in memory only.
- Mobile requests identify themselves as `WathiqMobile/0.1` plus the truthful
  platform family without a device fingerprint and use the approved `mobile`
  audit source.
- Sign-in errors are reduced to non-disclosing client categories.
- Explicit sign-out clears local protected state even when the server request
  fails.
- Obsolete sign-in responses cannot restore a cleared or revoked session.
- Background lifecycle handling retains sessions before 15 minutes and clears
  them at or after 15 minutes; the 10-minute warning boundary is exposed through
  a best-effort scheduler interface whose failure cannot extend the session.
- Focused model, HTTP-contract, and session-state tests pass, and Flutter static
  analysis reports no issues.
- The approved canonical WebUI facet logo is reproduced as a dependency-free
  Flutter vector painter from the source SVG geometry and colors.
- English/LTR and Arabic/RTL sign-in screens use canonical catalogue keys for
  brand, field, action, and non-disclosing failure text.
- Required-password-change presentation uses existing canonical password keys,
  keeps protected destinations unavailable, validates confirmation locally,
  and delegates the actual change to the existing API contract.
- Application composition now switches from signed out to password change or
  authenticated state exclusively from the in-memory session controller.
- Anonymous startup is explicitly English and does not follow the device
  locale. After authentication, the existing localization bootstrap contract
  makes the user's effective language authoritative immediately; protected
  locale state resets to English at logout or session expiry.
- Live iOS authentication against the local API reached the authenticated
  Dashboard and persisted `AUTHENTICATION_SUCCEEDED` with source `mobile` and
  user agent `WathiqMobile/0.1 (ios)`.

## MobileFlutterV0.2 — session and capability continuation, 4 October 2026

- The user confirmed successful v0.1 authentication testing; this continuation
  keeps that boundary and remains on `MobileFlutterV0.2`.
- The user approved the read-only `/api/v1/auth/me/mobile-capabilities` response.
  It returns server-owned destination availability, respects the existing
  credential-change gate, and hides Global Search when disabled. It grants no
  resource access. The mobile client does not reconstruct authorization from
  role names or privilege combinations.
- Implemented destinations (Dashboard, User/Profile, Preferences, Sign out)
  disclose navigation from that response. The tablet separator uses directional
  borders, and the profile displays only authenticated response data.
- Flutter lifecycle observation starts one continuous background interval;
  repeated hidden/paused callbacks cannot restart the 15-minute clock.
- Returning before the limit revalidates the principal and capabilities; server
  revocation clears the session immediately. Offline/error revalidation uses a
  nondismissible centered gate retaining rendered content underneath, with
  explicit safe-read Retry and Sign out. A single foreground-only 30-second
  probe revalidates connectivity without mutation retries or overlapping reads. Sign-out also gates interaction.
- Native iOS/Android adapters schedule one best-effort local warning at ten
  background minutes using generic localized text only. Android uses inexact
  scheduling without exact-alarm permissions and suppresses warnings delivered
  after the fifteen-minute boundary. Resume, sign-out, and process startup
  cancel stale warnings; permission denial cannot change the timeout.
- Session generations prevent delayed preference/bootstrap/capability responses
  from restoring cleared identity, language, destination, or preference state.
  Revocation replaces the Navigator, removing pushed protected routes.
- Added five `mobile.*` contextual keys to the authoritative English catalogue
  and merged only their missing Arabic drafts into the canonical artifact.
  Existing translation text and per-item provenance are unchanged. Both mobile
  language assets are synchronized to 2,899 active keys. No administrator export
  was promoted; the five new Arabic drafts require administrator review.
- Corrected a catalogue-validator false positive: MSG-007 explicitly requires
  the conventional `Re:` reply prefix in every language. Its existing artifact
  text/provenance are preserved and the exception is exact-key/exact-value.
- Verification: 52 Flutter unit/widget checks pass; Flutter analysis reports no
  issues; Android debug APK and iOS simulator native builds passed. Two backend
  capability tests passed using unique disposable fresh/upgrade databases;
  schema parity passed and both databases were dropped. Three database-free
  invariant-prefix validator tests and full catalogue coverage/order/placeholder/
  blank/terminology/stale-key/hash checks passed.

## Pending

- Complete English, Arabic, LTR, RTL, iOS, Android, phone, and tablet runtime
  verification, including actual OS warning permission/delivery and cancellation.
  Compiled native adapters and mocked channel checks do not establish OS delivery.
- Phase 1 remains in progress; its complete exit gate is not yet claimed.

## Phase 1 shell completion work — 4 October 2026

- Added capability-controlled Global Search, Classification Browser, Favourites,
  and Recent Activity entries in the approved drawer order. Global Search also
  has a prominent top-bar action; it disappears when the server omits it.
- Destination routes retain their place through orientation changes and Back;
  they are navigation foundations only. Search execution, classification trees,
  favourites and activity content remain in phases 5, 6 and 3 respectively.
- Navigation scrolls on compact displays. English/LTR and Arabic/RTL widget
  checks cover phone/tablet navigation, ordering, orientation, Back and disabled
  search. Full Flutter verification: 57 tests pass; static analysis is clean.
- Added four contextual `mobile.navigation.*` keys (global_search,
  classification_browser, favourites, recent_activity), merged only missing
  Arabic drafts, and synchronized 2,903 keys in each mobile asset. Existing
  Arabic wording and per-item provenance are unchanged. Coverage, ordering,
  stale-key, placeholder, terminology and catalogue-hash checks pass. No
  administrator export was promoted; the four new drafts require review in
  addition to the five earlier Phase 1 drafts.
- Xcode 27 provides simulator interaction through Device Hub, already installed
  on this workstation; the old standalone Simulator.app path does not apply.
- Interactive iOS checks were requested from the user. OS warning delivery,
  cancellation, timeout and cross-platform runtime evidence remain pending;
  Phase 1 is not declared complete until its exit gate is verified.

## User-reported iOS acceptance — 4 October 2026

The user reports completing all requested interactive checks except the
fifteen-minute tests. The requested matrix covered sign-in, drawer navigation,
Arabic/RTL, sign-out, process-restart sign-in, return before fifteen minutes,
and warning appearance/cancellation. This is user-reported evidence, not an
independently observed device run. Native acceptance of the at-or-after-fifteen-
minute boundary is still pending; automated 14:59/15:00 checks pass. Android
Phase 1 runtime acceptance is also pending until the user finishes iOS testing.

Updated native packaging verification: iOS simulator build and Android debug APK
both pass with the explicit local API address supplied at build time. The iOS
build was installed and launched through Flutter's debug runner; the initial
English sign-in screen was visually inspected without clipping. Android was
built only; its emulator has not been started for this acceptance run.

## Pre-commit drawer correction — 7 October 2026

Destination selection now closes the phone drawer before pushing its route, so
Back returns to the unobscured Dashboard. The retained-Back widget checks now
verify drawer closure before rotation in English/LTR and Arabic/RTL on phone
and tablet. All 57 Flutter tests pass and static analysis is clean.

## Latest-main integration — 7 October 2026

Integrated `origin/main` at `a93c57a`. Catalogue conflicts were resolved by
message key, preserving all incoming Arabic translation items and provenance
exactly and retaining the mobile-only definitions and drafts. The newer
administrator export already promoted on main is retained as the merge base;
no new administrator export was produced. Mobile assets now contain 2,959
keys per language, with exact canonical coverage and an updated catalogue hash.
The four new navigation drafts and five earlier Phase 1 drafts still require
review. The incoming messaging migration verification is retained.

All 57 mobile tests pass after integration. Catalogue coverage, ordering,
stale-key checks and API environment-template consistency pass. The Arabic
draft validator reports eight inherited terminology failures, identical on
`origin/main`: seven Vital record labels and
`webui.hold_reason_dialog.remove_all_confirmation`. These require terminology
review; curated translations were not overwritten to suppress the failures.
No database-backed tests were run for this merge.
