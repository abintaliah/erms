# Mobile implementation validation matrix

Every delivered implementation unit must have a requirement, implementation,
and retained validation mapping. A row is added or updated in the same change
as its implementation. A phase cannot complete with an unresolved delivered
row.

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
| Authentication HTTP boundary | Mobile specification §§8.1–8.2, 8.4–8.5, 19, 21, 26 Phase 1 | `lib/features/auth/data/auth_api.dart` | `test/auth_api_test.dart` covers existing paths, request fields, session cookie, bearer token, localization bootstrap, mobile user-agent, non-disclosing failure category, and missing-cookie failure | Live non-production contract check pending | Automated contract verified |
| In-memory session ownership and isolation | Mobile specification §§8.2–8.4, 18–19, 26 Phase 1 | `lib/features/auth/application/session_controller.dart` | `test/session_controller_test.dart` covers success, credential-change gate, failure, unconditional local sign-out clearing, and stale-response rejection | No persistence dependency or credential file introduced | Verified |
| Background timeout policy | Mobile specification §8.3 and §26 Phase 1 | `SessionController` and `SessionWarningScheduler` | `test/session_controller_test.dart` covers 14:59 retention, 15:00 clearing, warning scheduling, cancellation, and warning failure | Platform notification adapter pending | Core policy verified |
| Canonical mobile brand mark | Mobile specification §§5, 8.1, 26 Phase 1 and approved Phase 1 mockups | `lib/core/design/wathiq_brand.dart` | `test/app_test.dart` locates the rendered logo mark on authentication | Geometry and colors match `frontend/webui/static/brand/wathiq-mark.svg`; live device review pending | Widget verified |
| Sign-in and required-password-change presentation | Mobile specification §§6, 8.1, 8.2, 26 Phase 1 | `AuthenticationScreen`, `PasswordChangeScreen`, `WathiqApp` composition | `test/app_test.dart` covers English/LTR, Arabic/RTL, submitted email normalization, authenticated transition, password-change gate, protected-screen absence, canonical logo, and field presence | Uses existing canonical catalogue keys; live device and service checks pending | Widget verified |
| Effective mobile language lifecycle | Mobile specification §6, existing internationalization specification §§5–6, and §26 Phase 1 | `WathiqApp`, `SessionController`, `AuthApi.effectiveLanguage` | `test/app_test.dart` proves an Arabic device still receives English anonymous sign-in and a saved Arabic preference switches the authenticated shell to RTL; session tests verify user state clearing | Uses existing `/api/v1/i18n/bootstrap`; Preferences editing UI remains pending | Automated behavior verified |

## Later phases

Add one or more rows for every independently meaningful parser, configuration
rule, state transition, adapter, widget, route, responsive layout, platform
setting, and generated artifact before reporting that unit complete. Rows must
name concrete test files and may not use a phase-wide manual statement as a
substitute for automated unit evidence.
