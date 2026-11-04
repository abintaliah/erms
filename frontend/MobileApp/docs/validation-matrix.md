# Mobile implementation validation matrix

Every delivered implementation unit must have a requirement, implementation,
and retained validation mapping. A row is added or updated in the same change
as its implementation. A phase cannot complete with an unresolved delivered
row.

## Current session-policy amendment — 4 November 2026

The user's approved amendment to mobile specification §8.3 supersedes all
historical mobile 15/10-minute timing, warning-delivery, cancellation and
full-duration acceptance requirements below. Phase 1 now requires server-owned
session expiry, safe background-return validation and no session reminder.
Historical test results are retained as history, not current acceptance gates.

User-reported acceptance (4 November 2026): server-owned idle timeout worked
successfully on both Android and iOS after the latest builds were installed and
launched. Idle-timeout behavior passes on both platforms on the user's report;
configured duration, elapsed time, language and detailed sign-in/Back-navigation
outcomes were not specified. Do not infer absolute-lifetime, revocation,
offline-recovery or reminder-cleanup acceptance. Phase 1 remains open.

User-reported foreground-revocation acceptance (4 November 2026): following
the `3a00910` fix and requested open-app retest, session revocation passed on
both iOS and Android. Exact latency, language and detailed Back-navigation
observations were not specified. Remaining acceptance checks are unchanged;
Phase 1 remains open.

| Requirement | Implementation | Verification | Current status |
| --- | --- | --- | --- |
| Foreground expiry/revocation without renewing idle activity (§8.3; approved status endpoint) | Passive `/auth/me/session-status`; one nonoverlapping 15-second foreground monitor; guarded protected navigation; generation-owned state clearing | `test_mobile_session_status.py` plus existing policy/capability tests: 17 passed in disposable DB, dropped; `test/app_test.dart`: foreground route/Back and navigation rejection in English/Arabic phone/tablet, background/disposal pause; `test/session_controller_test.dart`: passive overlap/stale/offline; `test/auth_api_test.dart`: bearer endpoint; full Flutter suite 75 passed | Automated verified; foreground revocation passed on iOS/Android (user-reported); exact latency/language/Back coverage unclaimed |
| Server exclusively owns idle/absolute expiry (§8.3) | `SessionController` has no local timeout/clock; background return calls the existing principal/capability validation | `test/session_controller_test.dart`: server-valid resume, one validation after repeated background callbacks, server rejection, offline/retry and state isolation; `test/app_test.dart`: simulated one-day background in English/Arabic, server-valid retention and server-expired sign-in | Automated verified; new-policy device acceptance pending |
| No session reminder or permission prompt (§8.3) | Removed Dart scheduler, Android receiver/manifest permission and all native scheduling/permission requests; startup cancels legacy identifiers only | `test/platform_configuration_test.dart` guards removal and legacy cleanup; Android APK and iOS simulator native builds pass | Static/build verified; legacy-install cleanup must be checked on devices |
| Application settings enforce current policy | Existing API uses `AUTH_SESSION_IDLE_MINUTES` / `AUTH_SESSION_ABSOLUTE_HOURS`; no duplicate mobile settings | `test_application_settings_phase5_authentication.py` and `test_mobile_capabilities.py`: 11 tests passed in a uniquely named disposable DB, dropped afterward | Verified |
| Removed reminder text | Removed only `mobile.session.warning_title` and `mobile.session.warning_body`; synchronized 3,982 keys per source/artifact/mobile asset | Catalogue reference/stale-key, order, placeholder, blank, terminology, quality, hash and retained-provenance checks pass | Verified; existing unrelated mobile drafts still require review |

All 61 Flutter tests, formatting and static analysis pass. Android and iOS native builds pass. No service setting
or schema migration is introduced. Existing installations require the rebuilt
app to receive this policy and clear old reminders. Phase 1 remains open for
runtime verification of server expiry/revocation, offline retry and legacy
notification cleanup on both platforms; a fixed fifteen-minute run is no longer
a requirement.

## Phase 0

| Implementation unit | Requirement | Implementation | Automated validation | Additional evidence | Status |
| --- | --- | --- | --- | --- | --- |
| Repository ownership and project identity | Mobile specification §§24, 26 Phase 0 | `pubspec.yaml`, project tree, Android Gradle configuration, iOS Xcode project | `test/project_structure_test.dart`, `test/platform_configuration_test.dart` enforce temporary `erms.wathiq` identity and absence of `com.example` | `git status`, repository review; permanent distribution identity deferred | Verified for local development |
| English/Arabic canonical ingestion | Mobile specification §§6, 26 Phase 0 | `tool/sync_i18n.dart`, `assets/i18n`, `MessageCatalogue` | `test/message_catalogue_test.dart` exact source equality, coverage, blank and mismatch failures | Synchronizer reports 2,615 keys per language | Verified |
| Effective locale and direction | Mobile specification §§6, 26 Phase 0 | `WathiqApp`, `MessageCatalogue` | `test/app_test.dart` English LTR and Arabic RTL widget checks | English and Arabic inspected on iPhone 18 Pro, Pixel 8, and Pixel Tablet portrait/landscape where applicable; no clipping or overflow | Verified |
| Wathiq light design tokens | Mobile specification §§5, 26 Phase 0 | `lib/core/design/wathiq_theme.dart` | `test/wathiq_theme_test.dart` exact canonical token and light-theme checks | User approved Option B — Mobile-focused on 30 September 2026 | Verified |
| Environment base URL boundary and connectivity | Mobile specification §§19, 26 Phase 0 | `lib/core/config/app_environment.dart`, `tool/verify_connectivity.dart` | `test/app_environment_test.dart` HTTPS, local HTTP, missing, relative, and insecure remote cases; `test/project_structure_test.dart` verifies the bounded connectivity utility | Local WebUI connectivity was confirmed at `http://127.0.0.1:8080`; the documented mobile API target is `http://127.0.0.1:8000` | Verified for local development |
| Platform name and orientation foundation | Mobile specification §§4–5, 26 Phase 0 | Android manifest, iOS Info.plist | `test/platform_configuration_test.dart` | Clean Flutter Doctor pass; iPhone 18 Pro simulator build/run; Android debug APK build; Pixel 8 portrait runtime; Pixel Tablet portrait and landscape runtime; all inspected without clipping or overflow | Verified for Phase 0 scaffold |
| Supported OS boundary documentation | Mobile specification §§4, 25–26 Phase 0 | `README.md`, Android Gradle configuration, iOS Xcode project | `test/platform_configuration_test.dart` verifies documented iOS 15 and Android API 24 floors against platform configuration | Flutter 3.47 supported-platform matrix reviewed; runtime checks performed on iOS 27 and Android API 36 | Verified |
| Architecture and API ownership boundaries | Mobile specification §§3, 21, 24, 26 Phase 0 | `docs/architecture.md`, `docs/existing-api-inventory.md` | `test/project_structure_test.dart` presence and project declaration checks | Contract review | Verified for Phase 0 scaffold |
| Sensitive-file exclusion | Mobile specification §§8, 19, 26 Phase 0 | Project boundary and `.gitignore` | `test/project_structure_test.dart` rejects common credential files | Secret scanning expansion pending dependency selection | Automated baseline passes |
| Foundation visual-direction proposals | Mobile specification §§5, 26 Phase 0 | `docs/mockups/phase-0-review.md` and two option boards | Visual artifact presence is covered by repository review; implementation checks begin only after selection | User approved Option B — Mobile-focused on 30 September 2026 | Verified |

## Phase 1

| Implementation unit | Requirement | Implementation | Automated validation | Additional evidence | Status |
| --- | --- | --- | --- | --- | --- |
| Authentication response model | Mobile specification §§3.1, 8.1, 21, 26 Phase 1 | `lib/features/auth/domain/auth_principal.dart` | `test/auth_principal_test.dart` covers successful parsing and malformed authorization/session fields | Matches `PrincipalRead` in the existing API schema | Verified |
| Authentication HTTP boundary | Mobile specification §§8.1–8.2, 8.4–8.5, 19, 21, 26 Phase 1 | `lib/features/auth/data/auth_api.dart` | `test/auth_api_test.dart` covers existing paths, request fields, session cookie, bearer token, localization bootstrap, mobile user-agent, governed `mobile` event source, non-disclosing failure category, and missing-cookie failure | Live iOS login reached Dashboard; the immutable `AUTHENTICATION_SUCCEEDED` event stored source `mobile` and user agent `WathiqMobile/0.1 (ios)` | Verified against local API |
| In-memory session ownership and isolation | Mobile specification §§8.2–8.4, 18–19, 26 Phase 1 | `lib/features/auth/application/session_controller.dart` | `test/session_controller_test.dart` covers success, credential-change gate, failure, unconditional local sign-out clearing, and stale-response rejection | No persistence dependency or credential file introduced | Verified |
| Server-owned session policy | Mobile specification §8.3 and §26 Phase 1 | `SessionController` background-return validation | `test/session_controller_test.dart` and bilingual long-background cases in `test/app_test.dart` | Existing server authentication settings enforce expiry; see current amendment above | Automated verified; device acceptance pending |
| Canonical mobile brand mark | Mobile specification §§5, 8.1, 26 Phase 1 and approved Phase 1 mockups | `lib/core/design/wathiq_brand.dart` | `test/app_test.dart` locates the rendered logo mark on authentication | Geometry and colors match `frontend/webui/static/brand/wathiq-mark.svg`; live device review pending | Widget verified |
| Sign-in and required-password-change presentation | Mobile specification §§6, 8.1, 8.2, 26 Phase 1 | `AuthenticationScreen`, `PasswordChangeScreen`, `WathiqApp` composition | `test/app_test.dart` covers English/LTR, Arabic/RTL, submitted email normalization, authenticated transition, password-change gate, protected-screen absence, canonical logo, and field presence | Uses existing canonical catalogue keys; live device and service checks pending | Widget verified |
| Effective mobile language lifecycle | Mobile specification §6, existing internationalization specification §§5–6, and §26 Phase 1 | `WathiqApp`, `SessionController`, `AuthApi.effectiveLanguage` | `test/app_test.dart` proves an Arabic device still receives English anonymous sign-in and a saved Arabic preference switches the authenticated shell to RTL; session tests verify user state clearing | Uses existing `/api/v1/i18n/bootstrap`; Preferences editing UI is implemented and covered by `test/app_test.dart` | Automated behavior verified |

## Historical implementation and acceptance records

Add one or more rows for every independently meaningful parser, configuration
rule, state transition, adapter, widget, route, responsive layout, platform
setting, and generated artifact before reporting that unit complete. Rows must
name concrete test files and may not use a phase-wide manual statement as a
substitute for automated unit evidence.

### MobileFlutterV0.2 continuation — 4 October 2026

| Requirement | Implementation | Evidence | Status |
| --- | --- | --- | --- |
| Approved server-owned navigation availability | `authentication.mobile_capabilities`, `AuthApi.mobileCapabilities`, `SessionController.destinations`, shell disclosure | Two disposable-database endpoint tests; existing mobile HTTP/widget suites | Implemented destination subset verified; remaining shell destinations pending |
| Continuous background limit and server precedence (§8.3) | `WathiqApp` lifecycle observer; session resume validation | Repeated callback, 14:59/15:00, early revocation, offline retry, lifecycle widget tests | Automated verified |
| User state isolation and safe revocation (§§8.2, 17.4, 19) | Session generation guards and generation-owned Navigator | Delayed preferences after revocation; pushed Preferences removed and Back cannot restore identity | Automated verified |
| Best-effort ten-minute device warning (§8.3) | Native iOS UserNotifications / Android AlarmManager adapters; localized method-channel scheduler | Android/iOS debug builds and channel payload/cancellation test | Device permission/delivery matrix pending |
| Central loading, error, offline and explicit retry (§§16–17) | Nondismissible overlay retaining current Navigator; safe principal retry; preference read retry | Session offline/retry tests and shell widget checks | Explicit Retry and bounded foreground monitoring implemented |
| Contextual localization (§6) | Five new mobile keys; preserved canonical Arabic merge; synchronized mobile assets | 2,899-key coverage; full catalogue and Arabic/hash checks; three invariant-prefix tests | Automated verified; new Arabic drafts await administrator review |

### Phase 1 shell integration — 4 October 2026

| Requirement | Implementation | Evidence | Status |
| --- | --- | --- | --- |
| Ordered server-authoritative drawer and prominent search (§7.1–7.2) | `AuthenticatedShell`, capability-filtered destination entries and search action | `test/app_test.dart`: ordered drawer in both languages on phone/tablet; search omission | Automated verified |
| Retained Back and responsive destination (§4, §7.3) | Navigator-owned destination foundations and scrollable drawer | `test/app_test.dart`: open Favourites, rotate, Back to shell; no framework errors in LTR/RTL phone/tablet | Automated verified; interactive checks pending |
| Contextual destination labels (§6) | Four canonical `mobile.navigation.*` definitions and merged Arabic drafts | Catalogue validator, Arabic validation, preserved-item equality, hash check; 2,903 synchronized keys | Automated verified; Arabic drafts await review |

The destination foundations provide Phase 1 navigation only; resource content
and executable search remain governed by phases 3, 5 and 6. Full Phase 1 OS
runtime acceptance remains pending, as recorded in `phase-1-progress.md`.

User-reported iOS runtime evidence (4 October 2026): all requested interactive
checks were reported tested except the fifteen-minute tests. Retain the native
fifteen-minute boundary and Android runtime checks as pending; automated timeout
checks do not replace this evidence.

User-reported accelerated iOS acceptance (7 October 2026): warning delivery,
expiry on resume, and early-return warning cancellation passed with a temporary
three-minute timeout and a one-minute warning. Approved 15/10-minute timing and
canonical warning text were restored afterward. Full-duration iOS boundary and
Android runtime acceptance remain pending; accelerated evidence does not close
the complete Phase 1 exit gate.

### Mobile audit/session identification — 20 October 2026

| Requirement | Implementation | Evidence | Status |
| --- | --- | --- | --- |
| Mobile specification §8.5: truthful native client/platform in session history | Shared `frontend/webui/session_client.py`, used by global Login Sessions and user-detail session cards; original audit user agent/source preserved | `frontend/webui/tests/test_session_client.py`: iOS/Android, version variation, browser compatibility, unknown agents; existing `test/auth_api_test.dart`: Android login and iOS authenticated request headers | Automated verified; live English/Arabic session-card review pending |

| Device-model session identification (§8.5, user request 20 October 2026) | Native `erms.wathiq/device-model` adapters, bounded/sanitized optional model in `IoAuthApi` user agent, model-aware shared session presenter | `test/device_model_test.dart`: model sanitization and actual iOS/Android HTTP headers; `test/platform_device_model_test.dart`: native channel success/failure; WebUI presenter tests: native model and legacy compatibility; Android debug APK and iOS simulator builds | Automated/build verified; authenticated bilingual device-model session-card review pending |

User-reported model-entry acceptance (20 October 2026): iOS session entry verified
on the updated iPhone 18 Pro simulator app; Android platform previously reported
as `Google sdk_gphone64_arm64 (Android)`. Exact iOS model text and review language
were not supplied; bilingual visual coverage remains unclaimed.

User-reported Android accelerated acceptance (20 October 2026): warning delivered
in the notification panel and timeout/logout succeeded with temporary 3/1-minute
timing. No heads-up banner was shown (`IMPORTANCE_DEFAULT` channel). Early-return
cancellation and full-duration native acceptance remain unclaimed. Approved
15/10-minute timing and canonical wording restored after this test.

### Android return-to-app acceptance — 29 October 2026

Temporary debug build with explicit `WATHIQ_ANDROID_ACCEPTANCE=true`: three-minute
expiry, two-minute warning; implementation in `SessionController`, `main.dart`,
and Android `MainActivity.kt`. Governs the existing §8.3 early-return cancellation
and continuous background clock acceptance. Ordinary host tests retain canonical
timing. Runtime early-return/re-background/expiry results remain pending.

User-reported Android early-return result (29 October 2026): session continued
after return; early-return retention passes on reported evidence, exact elapsed
time unspecified. Prior successful warning delivery remains recorded. Current
3/2-minute run had no visible warning; ADB observed pending-alarm cancellation
on return. Displayed-notification cancellation and full-duration acceptance are
not established by this run.

Android notification diagnosis instrumentation (29 October 2026): debug-only
`WathiqSessionWarning` native schedule/cancel/receive/suppress/post event logs
support §8.3 runtime traceability without session or identity data. Device
reproduction with logs remains pending; delivery-window overlap is observed,
receiver suppression is not yet established.

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

| Requirement | Implementation | Evidence | Status |
| --- | --- | --- | --- |
| Approved background expiry/warning (§8.3) | Unconditional 15/10-minute `SessionController` constants; canonical localized body in `main.dart`; Android warning cutoff five minutes after requested warning; temporary acceptance switch removed | All 61 Flutter tests pass, including session boundary/scheduling and platform channel checks; `flutter analyze` clean | Source restored; rebuilt native installation and full-duration device acceptance pending |

No catalogue keys or language artifacts changed. The earlier installed debug
build retains diagnostic timing until rebuilt and reinstalled.

### Post-upgrade integration — 4 November 2026

| Requirement | Implementation | Evidence | Status |
| --- | --- | --- | --- |
| Server-authoritative Phase 1 destination availability (§7 and approved capability response) | Retained `/auth/me/mobile-capabilities`; search visibility reads validated database settings | `test_mobile_capabilities.py`: ordinary person session, enabled/disabled database settings despite opposite environment values, invalid session and credential-change gate; included in 42 passing disposable-database regressions | Automated verified |
| Current database/API compatibility (§§3, 21) | Main through `0cfd587`; 55-setting registry and migration-090 user-translation authorization | Read-only settings-loader inspection against upgraded local DB; `test_application_settings_phase6.py`, `test_application_settings_phase5_authentication.py`, `test_user_translation_authorization.py`, `test_entity_translations.py`; 42 focused tests passed, disposable DB dropped | Verified for integration scope |
| Canonical English/Arabic assets and terminology (§6) | 3,984 sorted keys per artifact/asset, preserved main Arabic entries/provenance and ten mobile keys; user-approved Vital record spelling and comparison-only diacritic normalization | `test/message_catalogue_test.dart`; catalogue/contextual terminology/Arabic-quality/hash/provenance checks; `tools/tests/test_arabic_ui_drafts.py`, `test_arabic_record_grammar.py`, `test_arabic_terminology_context.py`; 28 database-free validator/presenter checks passed | Automated verified; existing mobile drafts require human review |

All 61 Flutter tests, static analysis, Android debug APK and iOS simulator builds
pass. Authenticated English/Arabic runtime review, native installation and the
remaining full-duration Phase 1 acceptance gate are not established by this run.
