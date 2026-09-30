# Wathiq Mobile

Flutter client for the Wathiq ERMS. All mobile application code and related
project files live in this directory.

The product contract is maintained in
[`../../specs/flutter-mobile-application.md`](../../specs/flutter-mobile-application.md).
Existing backend and domain specifications remain authoritative; this client
must not reproduce authorization or records-management policy.

Every implementation unit requires a retained automated check and traceability
row in [`docs/validation-matrix.md`](docs/validation-matrix.md).

## Verified bootstrap toolchain

- Flutter 3.47.5 stable
- Dart 3.13.4
- DevTools 2.60.0
- Xcode 27.0 and iOS 27 Simulator runtime
- CocoaPods 1.17.0
- Android Studio 2026.1.4 Patch 1
- Android SDK Command-line Tools 15859902
- OpenJDK 17

Android SDK platform installation, licence acceptance, phone and tablet emulator
creation, and runtime checks are complete.

The Android application ID and iOS bundle identifier are temporarily
`erms.wathiq`. Replace this development identity with the organization's
permanent reverse-domain identifier before external distribution.

## Supported mobile OS versions

This project uses Flutter 3.47.5 and follows Flutter's
[supported deployment platforms](https://docs.flutter.dev/reference/supported-platforms).
It currently has the following platform support boundary:

| Platform | Oldest supported version | Current project target | Verified in Phase 0 |
| --- | --- | --- | --- |
| iOS and iPadOS | 15 | iOS deployment target 15.0 | iOS 27 Simulator |
| Android | Android 7.0, API level 24 | Compile and target API level 36 | API 36 phone and tablet emulators |

The application can therefore go back to **iOS 15** and **Android 7.0 (API
24)** without leaving the supported range of the installed Flutter SDK. iOS 14
and earlier and Android API 23 and earlier are unsupported by Flutter 3.47.
Supporting them would require an older Flutter toolchain and separate
compatibility, dependency, security, and device testing; they are not part of
the current mobile specification.

The Flutter-supported upper runtime range for this toolchain is iOS/iPadOS 27
and Android API 37. The project currently compiles and targets Android API 36;
raising that target will be handled as a deliberate toolchain update rather
than an implicit compatibility change.

## Canonical translations

The WebUI catalogues remain authoritative. From this directory, synchronize the
validated project-local assets with:

```sh
dart run tool/sync_i18n.dart
```

The synchronization fails on duplicate, blank, malformed, or unequal English
and Arabic active-key coverage. Never edit the generated files under
`assets/i18n` directly.

## Local verification

```sh
flutter pub get
dart run tool/sync_i18n.dart
dart format --output=none --set-exit-if-changed lib test tool
flutter analyze
flutter test
```

Use `flutter doctor -v`, `flutter devices`, and `flutter emulators` to validate
the host toolchain independently from the project.

For a locally running ERMS instance, verify that the mobile project's validated
environment boundary can reach it with:

```sh
dart run tool/verify_connectivity.dart http://127.0.0.1:8080
```

Supply the same address at launch with
`--dart-define=WATHIQ_API_BASE_URL=http://127.0.0.1:8080`. On an Android
emulator, reverse the selected local port through ADB before launch so that the
emulator's loopback address reaches the host. Do not commit environment URLs or
credentials.
