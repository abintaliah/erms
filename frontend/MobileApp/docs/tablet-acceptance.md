# Native tablet acceptance

The test in `integration_test/tablet_shell_test.dart` runs the production app
widgets with the canonical catalogues and an injected, test-only `AuthApi`.
It does not log in to a real account, call an ERMS API, or modify a database.
It is a layout/navigation acceptance test, not an authentication integration test.

The 4 November 2026 user decision limits this native acceptance run to landscape.
The product continues to support tablet portrait and landscape; existing widget
tests still cover orientation transitions. Native portrait/rotation acceptance
is omitted at the user's request, not reported as passed.

## Run

Run these commands from `frontend/MobileApp` after selecting a tablet from
`flutter devices`. The tablet's actual viewport must already be landscape;
the test rejects a portrait or phone-sized viewport rather than resizing a
Flutter test surface to simulate a tablet.

```sh
flutter pub get
flutter drive --driver=test_driver/tablet_shell_driver.dart \
  --target=integration_test/tablet_shell_test.dart -d <tablet-device-id> --no-pub
```

For the Android emulator, use its native rotation control if landscape setup is
needed: `adb -s <tablet-serial> emu rotate`. Android API 36 large-screen policy
ignores application orientation-lock requests; no compatibility override is used.

On iPadOS, the current windowing mode can reject app-programmatic orientation
changes. The included XCTest helper sets only the simulator's native device
orientation, without modifying the app's supported orientations or multitasking:

```sh
xcodebuild test \
  -project test_driver/ipad_orientation/TabletOrientation.xcodeproj \
  -scheme TabletOrientation -destination id=<ipad-device-id> \
  -derivedDataPath ../../.runtime/tablet-acceptance/ipad-helper \
  CODE_SIGNING_ALLOWED=NO -quiet
```

Then run `flutter drive` for that same iPad. Use tablet targets only; the tests
install their own composition under the development application identifier.
Phone installations and real signed-in sessions are not part of this test.

## Coverage and evidence

- Switch English → Arabic → English through Preferences without losing identity.
- Verify effective direction and tablet navigation placement in both languages.
- Check each navigation control is reachable and inside the actual viewport.
- Open Global Search, Classification Browser, Favourites, Recent Activity,
  User/Profile and Preferences, and return with Back.
- Detect framework layout exceptions and text exceeding its configured lines.
- Save native screenshots of shell, Preferences and Favourites in each language.

The driver writes images and per-platform JSON summaries to
`.runtime/tablet-acceptance/` at repository root. Inspect the screenshots before
promoting results into the validation matrix. The reviewed 4 November run is
retained under `docs/verification/tablet-landscape-2026-11-04/`.

`flutter drive` builds a test entrypoint. Rebuild the normal `lib/main.dart`
Android APK/iOS simulator app afterward before distributing or installing the
normal application. The fixture token and account exist only in test memory.
