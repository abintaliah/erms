# Phase 1 progress record

Status: In progress

Current policy (approved 4 November 2026): session expiry belongs exclusively to
API application settings. The mobile 15-minute timeout and ten-minute reminder
are removed. Historical entries below describing those rules are superseded;
see the latest amendment at the end for current verification and exit checks.

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

## User-reported accelerated iOS acceptance — 7 October 2026

On the iPhone simulator, the user reports that warning delivery and expiry on
resume worked with a temporary three-minute background timeout and a warning
after one minute (two minutes remaining). Early-return warning cancellation
also passed. Arabic notification text was delivered; the user accepts the
observed left-aligned notification presentation. Its cause was not independently
verified. These are user-reported results, not independently observed runs.

The temporary timing and warning text were restored to the approved fifteen-
minute timeout and ten-minute warning. Accelerated checks validate the device
lifecycle path but do not establish a real fifteen-minute device boundary run.
That full-duration check and Android runtime acceptance remain pending.

## Mobile audit/session identification correction — 20 October 2026

- The user reported Browser / Unknown platform for a native mobile session.
  Both WebUI session summaries only recognized browser-style user agents,
  despite the client already sending the correct `WathiqMobile/0.1 (ios)` or
  `(android)` header.
- Section 8.5 now explicitly requires Wathiq Mobile with iOS or Android in
  audit/session presentation in both languages. A shared presenter recognizes
  the existing native format in both global and user-detail session views.
  Raw session/audit evidence and event source remain unchanged; there is no
  schema, API, environment, or translation-artifact change.
- Verification: 153 WebUI presenter/entity checks and six Flutter HTTP contract
  checks passed; catalogue completeness/stale-reference validation passed.
  Existing product/platform names are interpolation values in the unchanged
  bilingual message. No catalogue keys changed or administrator export promoted.
- Live English/Arabic review of authenticated session cards remains pending;
  this correction does not close the outstanding Phase 1 device acceptance gate.

## Device-model session identification — 20 October 2026

- At the user's request, §8.5 now requires the device model beside the OS family
  so sessions can be distinguished before revocation. New native user agents
  append `; model=<model>`; existing sessions/audit events are not rewritten.
- Android reports manufacturer/model using `Build.MANUFACTURER`/`Build.MODEL`.
  iOS reports the hardware model identifier using `uname`, or the simulator's
  model identifier with an explicit Simulator suffix. No marketing-name lookup
  is guessed. No serial, IMEI, vendor/advertising ID or user-assigned name is read.
- One bounded native model read precedes composition; unavailable/failed reads
  fall back to OS-only identification. Header model text is sanitized and capped
  at 100 ASCII characters. Both WebUI session views show the model plus OS.
- Verification: all 61 Flutter tests pass, analysis is clean, Android debug APK
  and iOS simulator builds pass, and all 11 shared presenter cases pass. Catalogue
  completeness/stale-reference checks pass. No environment/schema/translation
  artifacts or keys changed and no administrator export was promoted.
- Updated Android build installed on the Pixel 8 emulator. Sign in again to
  record the model in a new session. Authenticated English/Arabic visual review
  remains pending because browser automation is unavailable in this session.
  A hardware model identifies a product family, not an individual device;
  existing session timestamps/current-session state remain relevant.

## User-reported iOS model-entry acceptance — 20 October 2026

The user verified the iOS session entry after launching the updated app on the
iPhone 18 Pro simulator and signing in. This is user-reported acceptance of the
iOS client/model/platform presentation, not an independently observed browser
run. The exact displayed model value and language were not supplied. Earlier
Android feedback confirmed `Google sdk_gphone64_arm64 (Android)`, the emulator's
reported model. These checks do not establish the full bilingual session-card
matrix or the remaining Android lifecycle/notification acceptance.

## Temporary Android accelerated acceptance — 20 October 2026

At the user's request, Android debug builds temporarily expire after three
background minutes and schedule the warning after one minute. The native warning
suppression boundary and temporary English/Arabic warning wording match that
three-minute interval. iOS and release builds retain approved 15/10-minute timing.
These temporary edits in `session_controller.dart`, `main.dart`, and Android
`MainActivity.kt` must be restored after the device run, before release or phase
completion. This is an acceptance build, not a new product timing requirement.
All 61 Flutter tests and analysis pass; host tests retain normal timing and do
not establish native accelerated delivery/expiry. User/device results are pending.
Canonical translation assets are untouched by this temporary test wording.

## User-reported Android accelerated acceptance — 20 October 2026

The user confirms that the temporary Android warning arrived in the notification
panel and that automatic logout occurred with the three-minute test timeout.
No heads-up banner appeared. The receiver creates the channel with
`IMPORTANCE_DEFAULT`, which explains panel delivery without a heads-up banner;
no notification-priority change was requested or made. This is user-reported
warning/expiry evidence, not an independently observed OS run. Early-return
cancellation and a full-duration native run were not reported by this result.
The temporary Android timing, native stale-warning boundary, and test wording
are restored to the approved 15-minute expiry / 10-minute warning and canonical
bilingual wording. The earlier accelerated acceptance build is superseded.

## Android return-to-app acceptance setup — 29 October 2026

At the user's request, an explicit debug-only compile-time switch
`--dart-define=WATHIQ_ANDROID_ACCEPTANCE=true` enables a three-minute
background expiry and a warning after two minutes on Android only. It defaults
to false; iOS, release builds and ordinary host tests retain 15/10-minute timing.
This is a build argument, not a service environment setting. Temporary bilingual
notification wording describes the three-minute limit; canonical catalogues are
unchanged. The Android debug warning cutoff is one minute after the two-minute
warning. Remove this acceptance setup after the device test.

Return before three minutes should retain the session after server revalidation
and cancel the pending/displayed warning. A subsequent background interval must
start a new clock. Returning at or after three minutes must require sign-in.
Device acceptance results are pending; this setup does not close Phase 1.

### Missing two-minute Android warning — 29 October 2026

The user reports no warning in the 3/2-minute acceptance run. ADB inspection
confirms notification permission granted and the session-warning channel enabled
at DEFAULT importance. AlarmManager retains a Wathiq SessionWarningReceiver alarm
cancellation at app return, with a requested trigger approximately 70 seconds
before cancellation, and no Wathiq delivery in the retained alarm statistics.
This is consistent with inexact OS delivery being delayed until the app returned
and cancelled it; exact scheduling is not promised by setAndAllowWhileIdle.
Battery Saver is currently off. No notification-policy or permission change was
made. Warning acceptance is not passed; early-return session retention and
cancellation results remain pending.

### User-reported Android early-return acceptance — 29 October 2026

The user confirms they could continue the session after returning during the
accelerated early-return test. Record early-return session retention as passed
on user-reported evidence; the exact elapsed duration was not supplied. The
user also confirms the alarm worked previously, consistent with the retained
20 October successful accelerated warning-delivery result. The current 3/2-minute
run produced no visible warning; it does not invalidate the earlier delivery
evidence. ADB observed cancellation of a still-pending alarm on return, but
cancellation of an already displayed warning was not established in this run.
Full-duration native acceptance remains pending. Temporary acceptance timing
is still enabled in the installed debug build.

### Android notification diagnosis — 29 October 2026

AlarmManager snapshot retained at `/tmp/erms-alarm-diagnosis.txt` shows the
two-minute warning has a 90-second inexact delivery window, overlapping the
three-minute expiry cutoff. A later snapshot confirms a receiver alarm delivery,
but no active notification at inspection. This supports OS delay; it does not
prove whether the receiver suppressed expiry or a posted notification was later
cleared. Added debug-only timing/event logs (`WathiqSessionWarning`) for schedule,
cancel, receive, expiry/permission suppression and posting. No identity, token,
notification text or device model is logged. Diagnostic native build verification
and a fresh user-run reproduction are required; no scheduling policy changed.

### Revised Android diagnostic timing — 29 October 2026

At the user's request, the explicit Android debug acceptance build now uses
five-minute background expiry and the unchanged two-minute warning. The native
stale-warning cutoff and temporary bilingual wording match five minutes. This
supersedes the earlier three-minute diagnostic setup; ordinary builds and iOS
retain approved 15/10-minute timing. Runtime diagnosis remains pending.

### Successful Android diagnostic run — 29 October 2026

The user reports receiving the notification and continuing the preserved session
on return with five-minute expiry / two-minute requested warning. Native debug
logs confirm schedule at elapsedMs=999441, receiver delivery at 1209457,
notification posting at 1209461, and cancellation on return at 1215899. Delivery
was 210.016 seconds after scheduling (3m30s), 90.016 seconds after the requested
two-minute trigger. Return/cancellation occurred at 216.458 seconds (3m36s),
before the five-minute cutoff (1299441). This establishes delayed OS alarm
delivery and successful notification posting/cancellation in this run, alongside
user-reported session retention. A comparable delay with the earlier three-minute
cutoff would suppress a stale warning; earlier runs lack receiver logs, so that
specific suppression remains an inference. No scheduling policy was changed.
The installed diagnostic build still uses temporary 5/2-minute timing; normal
15/10-minute timing restoration and full-duration acceptance remain outstanding.

### Normal timing restored — 2 November 2026

At the user's request, removed the Android debug acceptance switch and restored
the unconditional 15-minute background expiry and 10-minute warning in
`SessionController`. Notification bodies again use the existing canonical
English/Arabic catalogue key. Android stale-warning suppression is restored to
five minutes after the requested warning, matching the fifteen-minute expiry.
Device-model support and debug diagnostic logging are retained.

All 61 Flutter tests pass and `flutter analyze` reports no issues. No catalogue
keys, translation artifacts, or environment settings changed. No native build
was installed by this restoration; the previously installed diagnostic build
requires rebuilding/reinstalling to receive normal timing. Full-duration device
acceptance and the remaining Phase 1 exit checks are still pending.

## Main integration after database upgrade — 4 November 2026

Integrated main revision `0cfd587` after the local database upgrade through
migration 094. The merged settings registry validates all 55 database settings;
user translations use `identity.users.administer` following migration 090.
The approved mobile capability route, `mobile` audit source, device-model
adapters and session presenters are retained. Mobile search availability now
reads the validated database snapshot; environment changes cannot override it.

Merged English definitions and canonical Arabic items by message key, retaining
every main Arabic item and its provenance unchanged, ten mobile-only keys, and
the retirement of the two obsolete user-metadata privilege keys. Both mobile
assets now contain 3,984 keys. The user approved correcting the specification's
Vital record spelling to `الوثائق الحيوية`; runtime terminology and the legacy
validator agree. Diacritics are normalized only during validation. These fixes
resolve ten inherited validator failures without rewriting curated translations.
Artifact catalogue/specification/terminology hashes are refreshed. No new
administrator export was promoted; existing mobile drafts still need review.

Verification: all 61 Flutter tests pass, analysis is clean, and Android debug
APK and iOS simulator builds pass. All 42 focused backend compatibility tests
pass in a new disposable database, which was dropped. All 28 database-free
validator/presenter checks pass. Coverage, order, blank, placeholder, stale-key,
Arabic-quality, contextual terminology, artifact-hash and provenance checks pass;
environment-template and configuration-authority checks also pass.

All 90 focused WebUI audit/history/localization regressions pass in English
and Arabic, including the merged disposition event labels and mobile audit
source. AST-isolated dialog fixtures now supply the retained source presenter.

The local database received only ten missing mobile drafts, protecting 3,974
existing translations, with zero corrections/failures. Notification readiness
passes. No services or emulators were started, and the new native builds were
not installed. Authenticated bilingual runtime review and full-duration timeout
acceptance remain pending; this integration does not close Phase 1.

## Server-owned expiry amendment — 4 November 2026

The user approved removing the mobile-specific background timeout and reminder.
Specification §§8.3, 26 Phase 1 and 27.3 now require the API's configured idle and
absolute lifetime policy to be authoritative. A server-valid session resumes
regardless of background duration; server expiry/revocation clears protected
state. Offline validation retains the noninteractive gate with Retry/Sign out.
Process-restart credentials, explicit logout and user isolation remain required.

Removed the local clock/cutoff, Dart warning scheduler, notification bridge,
Android receiver and permission, and all iOS/Android reminder scheduling and
permission requests. Native startup retains cancellation of old notification
identifiers so an upgrade does not leave an obsolete reminder pending/displayed.
Device-model support is retained. The historical warning panels in the approved
mockup boards are explicitly superseded, without changing other approved layouts.

Removed two unused catalogue definitions (`mobile.session.warning_title` and
`mobile.session.warning_body`) and their artifact/mobile-asset items. All 3,982
remaining entries retain their original wording and provenance. No administrator
export was promoted and no new translation review is introduced. Catalogue
coverage/order, placeholders, blank values, stale keys, terminology, Arabic
quality and artifact-hash/provenance checks pass.

The local database catalogue was synchronized: the two reminder definitions
are deprecated, their translation/history rows remain intact, and 3,982 active
definitions remain.

All 61 Flutter checks pass, including English/Arabic one-day-background widget
cases that resume only according to the server result. Android debug APK and
iOS simulator builds pass. All 11 focused server-policy/capability tests pass
in a fresh disposable database, which was dropped. The existing API settings,
values and schema are unchanged; no environment variable/template changes are
needed. Builds are not installed and services remain stopped.

Retired acceptance: fixed 15-minute background expiry, ten-minute warning,
permission/delivery matrix and continuous local expiry-clock tests. Current
remaining runtime acceptance: server-configured idle/absolute expiry and
revocation on background return, retention of server-valid sessions, safe offline
retry, no reminder prompts/delivery, and cancellation of legacy reminders on
upgrade, on iOS/Android and in both languages. Other Phase 1 device/tablet and
session-card review gaps remain open. This amendment does not close Phase 1.

## User-reported server idle-timeout acceptance — 4 November 2026

The user confirms that the server-owned idle timeout worked successfully on
both Android and iOS after the rebuilt apps were installed and launched against
the local API. Record idle-timeout behavior as passed on both platforms on
user-reported evidence. The configured timeout, elapsed duration, language, and
detailed sign-in/Back-navigation observations were not specified; those coverage
dimensions remain unclaimed. This is not an independently observed device run.

This result supports the amended §8.3 server-owned expiry requirement. Absolute
lifetime, explicit revocation, offline recovery, server-valid session retention,
legacy reminder cleanup and remaining bilingual/device coverage are not
established by this report. Phase 1 remains in progress.

## Foreground revocation correction — 4 November 2026

The user reported that revoking an open mobile session did not clear the shell
until background return. Phase 1 destinations were local foundations with no
server read, and the existing periodic reconnect probe ran only in an offline
gate. The user explicitly approved a passive session-status endpoint, a
15-second foreground check and validation before protected navigation.

Added `GET /api/v1/auth/me/session-status`, returning existing `PrincipalRead`.
Successful status authentication never updates activity or stored deadlines;
server policy still persists terminal expiry to prevent later revival. It does
not add privileges, settings, environment variables or schema changes. Required
password-change state remains available without granting protected access.

An app-root foreground monitor uses that endpoint without loading overlays on
healthy checks. It suppresses overlap and stops polling while backgrounded,
signed out, validating or disposed. Generation guards discard stale responses.
401 clears all protected state/routes; network/service errors gate interaction.
Protected destination, profile, preferences and dashboard navigation now perform
ordinary principal/capability validation first. User actions retain normal
server activity semantics; passive monitoring cannot keep idle sessions alive.

Verification: 75 Flutter tests and analysis pass; English/Arabic phone/tablet
widget regressions detect revocation while a route remains open, prevent Back
restoration and reject revoked navigation before the next periodic check.
Controller tests cover overlap, stale completion and offline gating; the HTTP
contract test covers the passive bearer endpoint. All 17 focused backend tests
pass in a new disposable DB, dropped afterward, proving unchanged activity and
deadlines on repeated probes, normal activity refresh, idle/absolute expiry,
non-revival, revoked/invalid/service rejection and password-change state.
Catalogue/configuration checks pass; no catalogue keys or artifacts changed.
Android debug APK and iOS simulator builds pass. The local stack was restarted,
its new status route verified, and both final builds installed and launched for
user retesting. No database schema or environment/template change was required.

Foreground revocation and idle expiry with passive monitoring still require
user/device acceptance on both platforms. Earlier user-reported idle-timeout
success is retained; this correction does not claim a new device pass or close
Phase 1.

## User-reported foreground revocation acceptance — 4 November 2026

Following the foreground revocation correction in `3a00910` and the requested
open-app retest, the user confirms that session revocation worked on both iOS
and Android. Record foreground revocation as passed on both platforms on
user-reported evidence. Exact detection latency, language, and detailed
Back-navigation observations were not specified; those dimensions remain
unclaimed. This is not an independently observed device run.

This closes the reported foreground-revocation acceptance gap for both
platforms. It does not establish the remaining absolute-lifetime, offline
recovery, legacy-reminder cleanup or bilingual/device coverage. Phase 1 remains
in progress.

## Controlled offline recovery acceptance — 4 November 2026

Both rebuilt apps were signed in with valid sessions. A read-only prerequisite
inspection confirmed the current server policy (10-minute idle, 12-hour absolute
lifetime). The identified local API process was paused for 55 seconds, from
10:33:55 to 10:34:50 Asia/Dubai, with automatic restoration in a finally block.
An HTTP health probe timed out during the interruption and returned 200 after
restoration. This simulated unavailable API responses; it did not disable device
radios or change network/security or session-policy settings. No database-backed
test suite or fixtures targeted the persistent local database.

During the interruption, the user confirmed that both Android and iOS showed
the offline dialog and blocked navigation. After restoration, the user confirmed
that both apps resumed the same signed-in screen without losing their place,
either through automatic recovery or Retry (the mechanism was not distinguished).
Post-outage logs show successful principal/capability revalidation. Record
offline gating and valid-session recovery as passed on both platforms, combining
automated interruption/recovery evidence with user-reported UI observations.

Native/browser UI controls were unavailable in this agent session, so the agent
did not independently inspect the dialogs, press Retry, or revoke sessions via
WebUI. Revocation during an outage remains untested by this run; do not infer
that case from earlier online revocation acceptance. Language, detailed Back
behavior and radio-specific connectivity coverage remain unclaimed. The API was
restored successfully, and the stack and both sessions were left available.
Phase 1 remains in progress.

## Revocation during outage acceptance — 4 November 2026

The user authorized automation with both mobile sessions active. A prerequisite
read identified exactly one active Android and one active iOS session, each with
more than eight minutes of idle lifetime remaining. The identified local API
process was paused for 55 seconds; a health probe verified unavailable responses.
After 46 seconds, while API responses were still unavailable, a bounded local
administrative transaction revoked only those two mobile sessions and appended
an individual `SESSION_REVOKED` event for each. Audit source is
`administrative_tool`, actor type `automated_process`; no human was impersonated
and no other sessions, credentials or policy settings were changed.

The API was resumed automatically in a finally block. Post-run verification
confirmed HTTP 200 health, both revoked flags and the two corresponding audit
events. Request logs show unauthorized authentication after restoration. The
user then confirmed that both Android and iOS showed sign-in after recovery or
Retry, and Back could not restore protected screens. Record revocation during
an outage and protected Back-state clearing as passed on both platforms, using
automated operational evidence plus user-reported UI acceptance.

Native/browser UI controls were unavailable, so on-screen behavior was not
independently observed by the agent. Automatic recovery versus explicit Retry
and the tested language were not distinguished. This was an API-response outage,
not a radio/network-configuration test, and no database test suite or fixtures
ran against the persistent database. The stack remains healthy; the two mobile
sessions are intentionally revoked and require sign-in for further tests.
Private operational evidence is retained in
`.runtime/mobile-acceptance/revocation-during-outage-2026-11-04.json`.

This closes the previously pending revocation-during-outage device acceptance
on both platforms. Absolute-lifetime and other remaining Phase 1 verification
requirements are unchanged; Phase 1 remains in progress.
