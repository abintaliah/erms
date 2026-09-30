# Phase 0 progress record

Status: Complete

Started: 30 September 2026

Completed: 30 September 2026

## Completed

- Flutter project scaffolded under the required `frontend/MobileApp` boundary.
- iOS and Android platform projects use the user-approved temporary development
  identifier `erms.wathiq`; replacement is deferred until a permanent
  organization identifier is chosen.
- Flutter 3.47.5, Dart 3.13.4, and project dependency baseline recorded.
- Official VS Code Flutter and Dart extensions installed and documented.
- Xcode 27, iOS 27 Simulator runtime, and CocoaPods 1.17.0 verified.
- Android Studio, Android SDK 36.0.0, Build-Tools 36.0.0, Platform-Tools,
  Android Emulator 37.1.11.0, and Android command-line tools installed.
- Android Studio's bundled JDK is recognized and all installed Android SDK
  licences are accepted.
- Android API 36 Google APIs ARM64 system image installed and its separate
  licence accepted.
- Pixel 8 phone and Pixel Tablet API 36 Android virtual devices configured.
- `flutter doctor -v` reports no Android, iOS, Flutter, device, network, or
  toolchain issues.
- Initial source layout and server-authoritative architecture boundary recorded.
- Existing API ownership inventory recorded without introducing an endpoint.
- Unit-level validation contract and Phase 0 traceability matrix established.
- Wathiq light-theme tokens aligned with the existing WebUI color tokens.
- Canonical WebUI catalogue synchronization implemented.
- 2,615 English and Arabic active messages synchronized with exact key coverage.
- Minimal Wathiq foundation shell created with explicit effective-locale support.
- English LTR and Arabic RTL widget behavior verified.
- Environment configuration rejects absent, malformed, and non-HTTPS remote API
  base URLs when used.
- Dart formatting and Flutter static analysis pass with no issues.
- Twenty-one project checks pass, covering project structure, sensitive-file
  exclusion, environment boundaries, canonical catalogue drift and failures,
  Wathiq design tokens, English/Arabic direction, platform configuration, and
  enforcement of the temporary `erms.wathiq` identifier and supported OS
  floor documentation, plus the repeatable connectivity verifier.
- Debug iOS Simulator application builds successfully.
- Android debug APK builds successfully with Gradle and NDK 28.2.13676358.
- Android debug APK and iOS Simulator builds pass after applying the temporary
  `erms.wathiq` platform identifier.
- Wathiq installs and runs successfully on an iPhone 18 Pro simulator using the
  iOS 27.0 runtime and Metal/Impeller renderer.
- Live iOS inspection confirms the light foundation shell, Wathiq application
  title, canonical English Dashboard label, safe-area placement, and portrait
  presentation render without clipping or overflow.
- Wathiq installs and runs successfully on the Pixel 8 API 36 phone emulator
  and Pixel Tablet API 36 emulator using the Impeller OpenGL renderer.
- Live Android inspection confirms the foundation shell renders without
  clipping or overflow on the phone in portrait and on the tablet in both
  portrait and landscape.
- The mobile project's validated environment boundary reached the locally
  running ERMS service at `http://127.0.0.1:8080` and received HTTP 200.
- A repeatable, credential-free connectivity verifier is available at
  `tool/verify_connectivity.dart`.
- Separate Web-familiar and mobile-focused Phase 0 foundation mockup boards are
  recorded under `docs/mockups`, and the user approved Option B — Mobile-focused
  as the foundation visual direction on 30 September 2026.
- Live Arabic/RTL inspection confirms the foundation shell renders canonical
  Arabic text without clipping or overflow on the iPhone 18 Pro, Pixel 8, and
  Pixel Tablet in portrait and landscape where applicable.
- Post-merge validation passes all twenty-one project checks, Dart formatting,
  and Flutter static analysis after synchronizing 2,615 canonical messages.

## Deferred items

- Replace temporary `erms.wathiq` with the permanent organization/application
  identifier before external distribution.
- Select routing, networking, and state packages only when the Phase 1 concrete
  requirements justify them.

All applicable Phase 0 exit gates in the mobile specification are supported by
the evidence recorded above and in `docs/validation-matrix.md`. The deferred
items are not Phase 0 blockers and remain explicit prerequisites for their
respective later work.
