# Mobile implementation validation matrix

Every delivered implementation unit must have a requirement, implementation,
and retained validation mapping. A row is added or updated in the same change
as its implementation. A phase cannot complete with an unresolved delivered
row.

## Phase 0

| Implementation unit | Requirement | Implementation | Automated validation | Additional evidence | Status |
| --- | --- | --- | --- | --- | --- |
| Repository ownership and project identity | Mobile specification §§24, 26 Phase 0 | `pubspec.yaml`, project tree, Android Gradle configuration, iOS Xcode project | `test/project_structure_test.dart`, `test/platform_configuration_test.dart` enforce temporary `erms.wathiq` identity and absence of `com.example` | `git status`, repository review; permanent distribution identity deferred | Verified for local development |
| English/Arabic canonical ingestion | Mobile specification §§6, 26 Phase 0 | `tool/sync_i18n.dart`, `assets/i18n`, `MessageCatalogue` | `test/message_catalogue_test.dart` exact source equality, coverage, blank and mismatch failures | Synchronizer reports 2,561 keys per language | Verified |
| Effective locale and direction | Mobile specification §§6, 26 Phase 0 | `WathiqApp`, `MessageCatalogue` | `test/app_test.dart` English LTR and Arabic RTL widget checks | English iPhone 18 Pro runtime inspected; Arabic runtime pending | Partially verified |
| Wathiq light design tokens | Mobile specification §§5, 26 Phase 0 | `lib/core/design/wathiq_theme.dart` | `test/wathiq_theme_test.dart` exact canonical token and light-theme checks | Mockup review pending | Automated checks pass |
| Environment base URL boundary and connectivity | Mobile specification §§19, 26 Phase 0 | `lib/core/config/app_environment.dart`, `tool/verify_connectivity.dart` | `test/app_environment_test.dart` HTTPS, local HTTP, missing, relative, and insecure remote cases; `test/project_structure_test.dart` verifies the bounded connectivity utility | Local ERMS at `http://127.0.0.1:8080` returned HTTP 200 through the mobile project verifier | Verified for local development |
| Platform name and orientation foundation | Mobile specification §§4–5, 26 Phase 0 | Android manifest, iOS Info.plist | `test/platform_configuration_test.dart` | Clean Flutter Doctor pass; iPhone 18 Pro simulator build/run; Android debug APK build; Pixel 8 portrait runtime; Pixel Tablet portrait and landscape runtime; all inspected without clipping or overflow | Verified for Phase 0 scaffold |
| Supported OS boundary documentation | Mobile specification §§4, 25–26 Phase 0 | `README.md`, Android Gradle configuration, iOS Xcode project | `test/platform_configuration_test.dart` verifies documented iOS 15 and Android API 24 floors against platform configuration | Flutter 3.47 supported-platform matrix reviewed; runtime checks performed on iOS 27 and Android API 36 | Verified |
| Architecture and API ownership boundaries | Mobile specification §§3, 21, 24, 26 Phase 0 | `docs/architecture.md`, `docs/existing-api-inventory.md` | `test/project_structure_test.dart` presence and project declaration checks | Contract review | Verified for Phase 0 scaffold |
| Sensitive-file exclusion | Mobile specification §§8, 19, 26 Phase 0 | Project boundary and `.gitignore` | `test/project_structure_test.dart` rejects common credential files | Secret scanning expansion pending dependency selection | Automated baseline passes |
| Foundation visual-direction proposals | Mobile specification §§5, 26 Phase 0 | `docs/mockups/phase-0-review.md` and two option boards | Visual artifact presence is covered by repository review; implementation checks begin only after selection | User selection or refinement request pending | Awaiting approval |

## Later phases

Add one or more rows for every independently meaningful parser, configuration
rule, state transition, adapter, widget, route, responsive layout, platform
setting, and generated artifact before reporting that unit complete. Rows must
name concrete test files and may not use a phase-wide manual statement as a
substitute for automated unit evidence.
