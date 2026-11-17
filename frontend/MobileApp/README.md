# Wathiq Mobile

Flutter client for the Wathiq ERMS. All mobile application code and related
project files live in this directory.

The product contract is maintained in
[`../../specs/flutter-mobile-application.md`](../../specs/flutter-mobile-application.md).
Existing backend and domain specifications remain authoritative; this client
must not reproduce authorization or records-management policy.

For a new maintainer, start with the [documentation guide](docs/README.md),
then read [current Phase 1 status and remaining work](docs/phase-1-progress.md).
[Architecture](docs/architecture.md) owns implementation boundaries;
[the validation matrix](docs/validation-matrix.md) maps each delivered requirement
to concrete tests. Dated history is retained separately and is not a backlog.

## Recorded bootstrap toolchain

These versions were recorded during the verified bootstrap. They are evidence
of that setup, not a request to upgrade tools or install another SDK.

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
dart run tool/verify_connectivity.dart http://127.0.0.1:8000
```

Supply the same address at launch with
`--dart-define=WATHIQ_API_BASE_URL=http://127.0.0.1:8000`. On an Android
emulator, reverse the selected local port through ADB before launch so that the
emulator's loopback address reaches the host. Do not commit environment URLs or
credentials.

## Native tablet acceptance

Native tablet layout acceptance is documented in
[`docs/tablet-acceptance.md`](docs/tablet-acceptance.md), including its test-only
API boundary, landscape setup, screenshot artifacts and normal-build restoration.

## Language and session behavior

Before saved preferences are available, the app follows device Arabic or falls
back to English. Saved ERMS language takes precedence afterward. Session expiry
and lockout remain server-owned; there are no local expiry reminders or periodic
checks on a healthy screen. See [architecture](docs/architecture.md) for the
credential-state sequence, offline recovery and identity-clearing rules.

## Build and install for local review

Start/check the managed services from the **repository root**:

```sh
./run-local-stack.sh up
./run-local-stack.sh status
```

The launcher synchronizes definitions and seeds only missing Arabic drafts. It
does not publish translations or run migrations. Use the URLs printed by status;
the commands below assume the ordinary local API port 8000.

From `frontend/MobileApp`, build normal development entrypoints:

```sh
flutter build apk --debug \
  --dart-define=WATHIQ_API_BASE_URL=http://127.0.0.1:8000
flutter build ios --simulator --debug \
  --dart-define=WATHIQ_API_BASE_URL=http://127.0.0.1:8000
```

Outputs are `build/app/outputs/flutter-apk/app-debug.apk` and
`build/ios/iphonesimulator/Runner.app`. The latter is a simulator build, not a
signed physical-iPhone package. Credentials are not compiled into either build.

Inspect `adb devices -l` and `xcrun simctl list devices booted`; choose explicit
targets before installing. Do not overwrite another target by guessing its ID.
For an Android emulator, reverse its API port:

```sh
adb -s <android-serial> reverse tcp:8000 tcp:8000
adb -s <android-serial> install -r build/app/outputs/flutter-apk/app-debug.apk
xcrun simctl install <booted-ios-udid> build/ios/iphonesimulator/Runner.app
```

A physical device needs an appropriate reachable API configuration; host
loopback does not automatically refer to the development Mac. Do not disable TLS
validation or embed private environment values to make a device test work.
The product environment validator requires HTTPS outside loopback development.

For acceptance, use [the current handoff checklist](docs/phase-1-progress.md#remaining-handoff-work).
Use dedicated local test accounts and existing administrative password-reset
flows when a new mandatory-password trial is needed. Resets revoke that user's
sessions; do not reset another user's password or change password policy merely
to manufacture a test. Never put temporary credentials in documentation or Git.

## Publishing translations

Publish/review in Translation Administration, then obtain a complete Arabic
export with reviewed drafts excluded. Deliberately merge it into the canonical
artifact while preserving per-item administrator wording and provenance; run
catalogue checks and `dart run tool/sync_i18n.dart`, then rebuild the mobile app.
Publication alone updates the selected database, not installed mobile binaries.
Current translation status and any remaining work are tracked in [Phase 1 status](docs/phase-1-progress.md#remaining-handoff-work).
