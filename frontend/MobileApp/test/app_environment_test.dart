import 'package:flutter_test/flutter_test.dart';
import 'package:wathiq_mobile/core/config/app_environment.dart';

void main() {
  test('environment accepts and retains an HTTPS API base URL', () {
    final environment = AppEnvironment.fromValue('https://erms.example.test');

    expect(environment.apiBaseUrl.scheme, 'https');
    expect(environment.apiBaseUrl.host, 'erms.example.test');
  });

  test('environment permits HTTP only for local development hosts', () {
    for (final host in ['localhost', '127.0.0.1', '[::1]']) {
      expect(
        AppEnvironment.fromValue('http://$host:8000').apiBaseUrl.scheme,
        'http',
      );
    }
  });

  test('environment rejects a missing API base URL', () {
    expect(() => AppEnvironment.fromValue(''), throwsFormatException);
  });

  test('environment rejects a relative API base URL', () {
    expect(() => AppEnvironment.fromValue('/api/v1'), throwsFormatException);
  });

  test('environment rejects non-HTTPS remote API URLs', () {
    expect(
      () => AppEnvironment.fromValue('http://erms.example.test'),
      throwsFormatException,
    );
  });
}
