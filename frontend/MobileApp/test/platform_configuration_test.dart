import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

void main() {
  test('iOS uses the Wathiq display name and phone portrait orientation', () {
    final plist = File('ios/Runner/Info.plist').readAsStringSync();

    expect(plist, contains('<string>Wathiq</string>'));
    final phoneSection = plist
        .split('<key>UISupportedInterfaceOrientations</key>')[1]
        .split('<key>UISupportedInterfaceOrientations~ipad</key>')[0];
    expect(phoneSection, contains('UIInterfaceOrientationPortrait'));
    expect(phoneSection, isNot(contains('UIInterfaceOrientationLandscape')));
  });

  test('iPad retains portrait and landscape orientations', () {
    final plist = File('ios/Runner/Info.plist').readAsStringSync();
    final tabletSection = plist.split(
      '<key>UISupportedInterfaceOrientations~ipad</key>',
    )[1];

    expect(tabletSection, contains('UIInterfaceOrientationPortrait'));
    expect(tabletSection, contains('UIInterfaceOrientationLandscapeLeft'));
    expect(tabletSection, contains('UIInterfaceOrientationLandscapeRight'));
  });

  test('Android uses the Wathiq display name', () {
    final manifest = File('android/app/src/main/AndroidManifest.xml')
        .readAsStringSync();

    expect(manifest, contains('android:label="Wathiq"'));
  });

  test('platforms use the approved temporary application identifier', () {
    final androidBuild = File('android/app/build.gradle.kts')
        .readAsStringSync();
    final iosProject = File('ios/Runner.xcodeproj/project.pbxproj')
        .readAsStringSync();
    final mainActivity = File(
      'android/app/src/main/kotlin/erms/wathiq/MainActivity.kt',
    ).readAsStringSync();

    expect(androidBuild, contains('namespace = "erms.wathiq"'));
    expect(androidBuild, contains('applicationId = "erms.wathiq"'));
    expect(iosProject, contains('PRODUCT_BUNDLE_IDENTIFIER = erms.wathiq;'));
    expect(mainActivity, contains('package erms.wathiq'));
    expect(androidBuild, isNot(contains('com.example')));
    expect(iosProject, isNot(contains('com.example')));
  });

  test('README records the effective supported OS floor', () {
    final readme = File('README.md').readAsStringSync();
    final iosProject = File('ios/Runner.xcodeproj/project.pbxproj')
        .readAsStringSync();
    final androidBuild = File('android/app/build.gradle.kts')
        .readAsStringSync();

    expect(readme, contains('iOS and iPadOS | 15'));
    expect(readme, contains('Android 7.0, API level 24'));
    expect(iosProject, contains('IPHONEOS_DEPLOYMENT_TARGET = 15.0;'));
    expect(androidBuild, contains('minSdk = flutter.minSdkVersion'));
  });
}
