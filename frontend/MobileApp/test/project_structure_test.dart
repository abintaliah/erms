import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

void main() {
  test('project identity and governed catalogue assets are declared', () {
    final pubspec = File('pubspec.yaml').readAsStringSync();

    expect(pubspec, contains('name: wathiq_mobile'));
    expect(pubspec, contains('assets/i18n/messages.en.json'));
    expect(pubspec, contains('assets/i18n/messages.ar.json'));
    expect(pubspec, contains('flutter_localizations:'));
  });

  test('Phase 0 architecture and API ownership records exist', () {
    expect(File('docs/architecture.md').existsSync(), isTrue);
    expect(File('docs/existing-api-inventory.md').existsSync(), isTrue);
    expect(File('docs/phase-0-progress.md').existsSync(), isTrue);
    expect(File('docs/validation-matrix.md').existsSync(), isTrue);
  });

  test('repeatable connectivity verifier uses the governed environment', () {
    final verifier = File('tool/verify_connectivity.dart').readAsStringSync();

    expect(verifier, contains('AppEnvironment.fromValue'));
    expect(verifier, contains('HttpClient'));
    expect(verifier, contains('connectionTimeout'));
    expect(verifier, contains('response.statusCode'));
  });

  test('no environment or credential file is committed to the scaffold', () {
    final forbidden = [
      '.env',
      '.env.local',
      'credentials.json',
      'secrets.json',
    ];

    for (final path in forbidden) {
      expect(File(path).existsSync(), isFalse, reason: '$path must not exist');
    }
  });
}
