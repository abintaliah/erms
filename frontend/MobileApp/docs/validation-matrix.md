# Mobile implementation validation matrix

Maintained as of 17 November 2026. Each delivered requirement maps to an owner
and retained automated checks. Current acceptance and pending work are maintained
in [Phase 1 status](phase-1-progress.md), not inferred from old test counts.
The [historical matrix](history/validation-matrix-through-2026-11-17.md) preserves
all earlier rows, superseded timing experiments and dated observations.

Paths in the implementation/test columns are relative to `frontend/MobileApp`
unless prefixed with `backend/`, `frontend/webui/` or `tools/` (repository root).

## Phase 0 foundation

| Requirement | Implementation | Automated checks | Evidence/status |
| --- | --- | --- | --- |
| Project boundary and temporary identity (§§24, 26) | Project tree, `pubspec.yaml`, Android/iOS configurations | `test/project_structure_test.dart`, `test/platform_configuration_test.dart` | Scaffold accepted; permanent distribution identifier remains deferred |
| Supported platforms and orientation (§§4, 25) | Android manifest/Gradle, iOS project/Info.plist, README | `test/platform_configuration_test.dart` | Local runtime evidence on Android API 36/iOS 27; supported floors Android API 24/iOS 15 |
| Canonical catalogue ingestion (§6) | `tool/sync_i18n.dart`, `MessageCatalogue`, packaged assets | `test/message_catalogue_test.dart` | Exact source equality, coverage and blank/mismatch rejection; currently 4,089 keys per language |
| Locale, direction and responsive foundation (§§4, 6) | `WathiqApp`, responsive widgets | `test/app_test.dart` | Current language-precedence rules and LTR/RTL checked; see Phase 1 rows |
| Wathiq visual foundation (§5) | `lib/core/design/` and approved mockups | `test/wathiq_theme_test.dart` | Mobile-focused option approved 30 September; original review in `docs/mockups/phase-0-review.md` |
| API URL and secret boundary (§§19, 26) | `AppEnvironment`, `.gitignore`, connectivity verifier | `test/app_environment_test.dart`, `test/project_structure_test.dart` | HTTPS/loopback rules and absence of common credential files verified; this is not a comprehensive security audit |
| API ownership (§§3, 21) | `docs/architecture.md`, `docs/existing-api-inventory.md` | `test/project_structure_test.dart` | Required architecture/ownership documents retained; product authority remains in specifications |

## Phase 1 current contracts

| Requirement | Implementation | Automated checks | Acceptance/evidence |
| --- | --- | --- | --- |
| Existing login and bearer-session contract (§§8.1–8.2) | `IoAuthApi`, `AuthPrincipal` | `test/auth_api_test.dart`, `test/auth_principal_test.dart`; `backend/services/api/tests/test_authentication.py` | Android/iOS sign-in accepted in Phase 1 closure; later Android temporary-password success reported |
| Required password change before protected bootstrap (§8.1) | `SessionController._completeSessionSetup`, `PasswordChangeScreen` | HTTP gate/request-order tests in `test/auth_api_test.dart`; controller tests; phone/tablet form-to-shell tests in `test/app_test.dart` | No forbidden bootstrap/capability requests before clearance; server access restriction preserved |
| Server validation feedback (§§8.1, 19) | Whitelisted response mapping, `ApiFailure`, field error decorations | 400/422/429 and safe-fallback tests in `test/auth_api_test.dart`; English/Arabic field/cooldown tests in `test/app_test.dart` | User explicitly considers feedback review done; individual additional platform/scenario observations not supplied |
| Confirmation mismatch (§8.1, user-reported issue) | Confirmation field error and existing disabled-submit rule | Four English/Arabic phone/tablet cases in `test/app_test.dart` | Covered by user-reported feedback acceptance; no premature mismatch on empty confirmation |
| Server-owned credential lock (§8.1; authentication lifecycle §2.4) | Backend counter/lock and mobile cooldown feedback | `backend/services/api/tests/test_password_attempt_limits.py`; mobile HTTP/widget tests | Backend enforcement and safe presentation verified; no client lockout policy |
| Server-owned destination availability (§7) | `mobileCapabilities`, controller destinations, shell filtering | `test/auth_api_test.dart`, `test/session_controller_test.dart`, `test/app_test.dart`; `backend/services/api/tests/test_mobile_capabilities.py` | No local role/privilege reconstruction; implemented shell subset only |
| Drawer, Back and responsive layout (§§4, 7) | `AuthenticatedShell`, generation-owned Navigator | `test/app_test.dart`, `integration_test/tablet_shell_test.dart` | Phone review accepted; native landscape tablets use an injected API; see tablet evidence limits |
| Device language before preference (§6, 17 November amendment) | `WathiqApp._effectiveLocale` / `didChangeLocales` | Regional Arabic/English, unsupported fallback, changing device locale and password-feedback tests in `test/app_test.dart` | 115-test suite/builds pass; native Android/iOS acceptance passed with controlled platform locales and injected API |
| Saved ERMS language takes precedence (§6) | `hasEffectiveLanguagePreference`, bootstrap, Preferences | `test/session_controller_test.dart`, `test/app_test.dart` | Opposite device/saved-language cases on phone/tablet; logout/revocation returns to device fallback |
| Preferences and optimistic concurrency (§§6, 8) | Existing GET/PUT preference contract, If-Match version | `test/auth_api_test.dart`, `test/session_controller_test.dart`, `test/app_test.dart` | Preference update changes language without logout; stale/unauthenticated responses remain isolated |
| Safe state and sign-out (§§8.2, 17.4, 19) | In-memory token, generation guards, clearing and Navigator reset | `test/session_controller_test.dart`, `test/app_test.dart` | User-reported process-restart/account-switch acceptance retained; delayed replies cannot restore prior state |
| Action-triggered revocation (§§8.3, 17.4) | Protected-action and resume validation; no healthy-screen polling | `test/session_controller_test.dart`, `test/app_test.dart`; `backend/services/api/tests/test_search_session_concurrency.py` | Approved and manually accepted 5 November; untouched screens intentionally remain rendered |
| Server-exclusive idle/absolute expiry (§8.3) | Existing API settings and resume validation | `backend/services/api/tests/test_application_settings_phase5_authentication.py`; controller and long-background widget cases | Idle acceptance reported on Android/iOS; manual absolute-lifetime check waived, not a device pass |
| Offline recovery and uncertain mutation outcome (§§8.3, 16–17) | Blocking validation overlay, safe-read Retry, no mutation replay | `test/session_controller_test.dart`, `test/app_test.dart` | Prior Android/iOS outage/revocation acceptance retained; explicit Retry vs automatic recovery not distinguished |
| Native client/model identity (§8.5) | Platform adapters, sanitized user-agent model, shared WebUI presenter | `test/device_model_test.dart`, `test/platform_device_model_test.dart`, `test/auth_api_test.dart`; `frontend/webui/tests/test_session_client.py` | Device-model/session presentation accepted in Phase 1 closure; no unique device identifier collected |
| Removed reminder behavior (§8.3 amendment) | Native legacy cancellation only | `test/platform_configuration_test.dart` | No new notification permission/scheduling; legacy-install cleanup not independently observed |
| Translation quality and provenance (§6; i18n §§7.5, 7.8) | Canonical key merge, packaged assets and whitelisted parameter rendering | `test/message_catalogue_test.dart`; `tools/tests/test_arabic_ui_drafts.py`, `tools/tests/test_arabic_record_grammar.py`, `tools/tests/test_arabic_terminology_context.py`; catalogue reference/runtime checks | Existing wording/provenance preserved; complete published export promoted 17 November; all 4,089 entries validated and existing wording/provenance preserved |
| Imported cooldown draft safety (i18n §7.8) | Existing seeder plus corrected regression expectation | `backend/services/api/tests/test_password_attempt_limits.py` | Imported provenance/wording retained, draft not auto-reviewed/published, repeat missing-only seed unchanged, source-change preservation checked |
| API refactor compatibility (§§3, 21) | Existing principal parser, route-local policy declarations and session integration | `backend/services/api/tests/test_mobile_capabilities.py`, `backend/services/api/tests/test_mobile_session_status.py`, `backend/services/api/tests/test_search_session_concurrency.py`; mobile parser tests | Preserved during merge; passive status route remains backend-only; [integration review](integration-review-2026-11.md) records scope |

## Latest recorded runs

| Run | Result | Scope/limits |
| --- | --- | --- |
| Flutter suite, 17 November | 115 passing tests; clean analysis | Unit/widget/local HTTP contract tests; not a live-account acceptance run |
| Password-attempt module, 17 November | 21 passing tests | New canonical disposable database created and dropped by the repository runner |
| Arabic validator checks, 17 November | 17 passing Python tests; catalogue quality/coverage/order/hash/runtime checks pass | Existing 4,087 entries retained; two generated feedback entries added without replacing curated values |
| Published export promotion, 17 November | 4,089 keys, no wording changes; 17 Arabic tests, four Flutter catalogue tests and one targeted provenance regression pass | Existing export builder, read-only transaction; regression database created/dropped; no publication/database mutation |
| Native language acceptance, 17 November | Both Android/iOS runs passed; three primary-locale cases per platform; 18 retained screenshots | Production widgets/native viewports; controlled platform locales and injected API; [evidence](verification/language-2026-11-17/README.md), [procedure](language-acceptance.md); no real accounts/DB or persistent OS settings changed |
| Native builds/install, latest device-language correction | Android debug APK and iOS simulator app succeeded and were launched on Pixel 8/iPhone 18 Pro | Normal main-entrypoint builds; language behavior is verified separately by the native acceptance run above |
| Native tablet landscape run, 4 November | Passed on Pixel Tablet and iPad Pro 11-inch M5 | Test-only injected API and canonical assets; retained screenshots/manifests; no real-server authentication |

Do not rerun database-backed tests against development data. Follow the
[repository database rules](../../../AGENTS.md) and the disposable runner.
Detailed dated acceptance, waived checks and superseded validation are preserved
in the [historical matrix](history/validation-matrix-through-2026-11-17.md) and
[historical progress](history/phase-1-progress-through-2026-11-17.md).

## Phase 2 boundary

Only API mapping/preparation exists. Details, child collections, resource history,
favourite controls and typed content navigation have not been implemented in
Flutter. Refresh the [historical API snapshot](phase-2-api-map.md), resolve its
recorded choices and obtain required mockup approval first. Neither Phase 1 shell
navigation nor a passing unrelated test proves a Phase 2 feature complete.
