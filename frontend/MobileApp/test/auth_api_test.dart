import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:wathiq_mobile/core/network/api_failure.dart';
import 'package:wathiq_mobile/features/auth/data/auth_api.dart';
import 'package:wathiq_mobile/features/auth/application/session_controller.dart';

void main() {
  for (final language in ['en', 'ar']) {
    test('temporary-password HTTP gate completes in $language', () async {
      var mustChange = true;
      final paths = <String>[];
      final server = await _server((request) async {
        final path = request.uri.path;
        paths.add(path);
        request.response.headers.contentType = ContentType.json;
        if (path != '/api/v1/auth/login') {
          expect(
            request.headers.value(HttpHeaders.authorizationHeader),
            'Bearer temporary-session',
          );
        }
        if (mustChange &&
            !const [
              '/api/v1/auth/login',
              '/api/v1/auth/me',
              '/api/v1/auth/change-password',
              '/api/v1/auth/logout',
            ].contains(path)) {
          request.response
            ..statusCode = 403
            ..write(jsonEncode({'detail': 'password change required'}));
        } else if (path == '/api/v1/auth/login' || path == '/api/v1/auth/me') {
          if (path.endsWith('/login')) {
            request.response.cookies.add(
              Cookie('erms_session', 'temporary-session'),
            );
          }
          request.response.write(
            jsonEncode({
              ..._principalJson(),
              'must_change_password': mustChange,
            }),
          );
        } else if (path == '/api/v1/auth/change-password') {
          final body = jsonDecode(await utf8.decoder.bind(request).join());
          expect(body, {
            'current_password': 'temporary',
            'new_password': 'replacement',
          });
          mustChange = false;
          request.response.statusCode = 204;
        } else if (path == '/api/v1/i18n/bootstrap') {
          request.response.write(jsonEncode({'effective_language': language}));
        } else if (path == '/api/v1/auth/me/mobile-capabilities') {
          request.response.write(jsonEncode(['dashboard', 'sign-out']));
        } else {
          request.response.statusCode = 404;
        }
        await request.response.close();
      });
      addTearDown(() => server.close(force: true));
      final controller = SessionController(
        IoAuthApi(Uri.parse('http://${server.address.address}:${server.port}')),
      );
      addTearDown(controller.dispose);
      await controller.signIn(
        email: 'user@example.test',
        password: 'temporary',
      );
      expect(controller.status, SessionStatus.passwordChangeRequired);
      expect(controller.effectiveLanguageTag, 'en');
      expect(paths, ['/api/v1/auth/login']);
      await controller.changePassword(
        currentPassword: 'temporary',
        newPassword: 'replacement',
      );
      expect(controller.status, SessionStatus.authenticated);
      expect(controller.effectiveLanguageTag, language);
      expect(controller.destinations, ['dashboard', 'sign-out']);
      expect(paths, [
        '/api/v1/auth/login',
        '/api/v1/auth/change-password',
        '/api/v1/auth/me',
        '/api/v1/i18n/bootstrap',
        '/api/v1/auth/me/mobile-capabilities',
      ]);
    });
  }

  test('sign-in uses existing contract and captures session cookie', () async {
    late HttpRequest received;
    late Map<String, Object?> body;
    final server = await _server((request) async {
      received = request;
      body = (jsonDecode(await utf8.decoder.bind(request).join()) as Map).map(
        (key, value) => MapEntry(key.toString(), value),
      );
      request.response
        ..statusCode = HttpStatus.ok
        ..cookies.add(Cookie('erms_session', 'issued-token')..httpOnly = true)
        ..headers.contentType = ContentType.json
        ..write(jsonEncode(_principalJson()));
      await request.response.close();
    });
    addTearDown(() => server.close(force: true));
    final api = IoAuthApi(
      Uri.parse('http://${server.address.address}:${server.port}'),
      platformFamily: 'android',
    );

    final session = await api.signIn(
      email: 'user@example.test',
      password: 'secret-value',
    );

    expect(received.method, 'POST');
    expect(received.uri.path, '/api/v1/auth/login');
    expect(received.headers.value('X-Event-Source'), mobileEventSource);
    expect(
      received.headers.value(HttpHeaders.userAgentHeader),
      'WathiqMobile/0.1 (android)',
    );
    expect(body, {'email': 'user@example.test', 'password': 'secret-value'});
    expect(session.token, 'issued-token');
    expect(session.principal.user.id, 7);
  });

  test('authenticated requests use bearer token and existing paths', () async {
    final requests = <HttpRequest>[];
    final server = await _server((request) async {
      requests.add(request);
      if (request.uri.path == '/api/v1/auth/me') {
        request.response
          ..headers.contentType = ContentType.json
          ..write(jsonEncode(_principalJson()));
      } else if (request.uri.path == '/api/v1/i18n/bootstrap') {
        request.response
          ..headers.contentType = ContentType.json
          ..write(
            jsonEncode({
              'effective_language': 'ar',
              'supported_languages': [
                {
                  'language_tag': 'en',
                  'english_name': 'English',
                  'native_name': 'English',
                },
                {
                  'language_tag': 'ar',
                  'english_name': 'Arabic',
                  'native_name': 'العربية',
                },
              ],
            }),
          );
      } else if (request.uri.path == '/api/v1/preferences') {
        request.response
          ..headers.contentType = ContentType.json
          ..write(
            jsonEncode({
              'language_tag': request.method == 'PUT' ? 'ar' : 'en',
              'working_timezone': 'Asia/Dubai',
              'version': request.method == 'PUT' ? 2 : 1,
            }),
          );
      } else {
        request.response.statusCode = HttpStatus.noContent;
      }
      await request.response.close();
    });
    addTearDown(() => server.close(force: true));
    final api = IoAuthApi(
      Uri.parse('http://${server.address.address}:${server.port}'),
      platformFamily: 'ios',
    );

    await api.currentPrincipal('memory-token');
    expect(await api.effectiveLanguage('memory-token'), 'ar');
    expect(
      (await api.supportedLanguages('memory-token'))
          .map((language) => language.languageTag),
      ['en', 'ar'],
    );
    expect((await api.preferences('memory-token')).version, 1);
    final updated = await api.updatePreferences(
      token: 'memory-token',
      languageTag: 'ar',
      workingTimezone: 'Asia/Dubai',
      version: 1,
    );
    expect(updated.languageTag, 'ar');
    expect(updated.version, 2);
    await api.changePassword(
      token: 'memory-token',
      currentPassword: 'current-secret',
      newPassword: 'new-secret-value',
    );
    await api.signOut('memory-token');

    expect(requests.map((request) => request.uri.path), [
      '/api/v1/auth/me',
      '/api/v1/i18n/bootstrap',
      '/api/v1/i18n/bootstrap',
      '/api/v1/preferences',
      '/api/v1/preferences',
      '/api/v1/auth/change-password',
      '/api/v1/auth/logout',
    ]);
    for (final request in requests) {
      expect(
        request.headers.value(HttpHeaders.authorizationHeader),
        'Bearer memory-token',
      );
      expect(
        request.headers.value(HttpHeaders.userAgentHeader),
        'WathiqMobile/0.1 (ios)',
      );
    }
    expect(requests[4].headers.value(HttpHeaders.ifMatchHeader), '"1"');
  });

  final passwordErrors = [
    (
      422,
      'password must contain at least 15 characters',
      'mobile.authentication.password_too_short',
      'new_password',
      {'minimum': 15},
    ),
    (
      400,
      'current password is incorrect',
      'mobile.authentication.current_password_incorrect',
      'current_password',
      <String, int>{},
    ),
    (
      429,
      {
        'code': 'password_attempts_locked',
        'message_key': 'authentication.error.password_attempts_locked',
        'parameters': {'seconds': 120},
      },
      'authentication.error.password_attempts_locked',
      null,
      {'seconds': 120},
    ),
  ];
  for (final (status, detail, key, field, parameters) in passwordErrors) {
    test(
      'password response $status retains only recognized safe feedback',
      () async {
        final server = await _server((request) async {
          request.response
            ..statusCode = status
            ..headers.contentType = ContentType.json
            ..write(jsonEncode({'detail': detail}));
          await request.response.close();
        });
        addTearDown(() => server.close(force: true));
        final api = IoAuthApi(
          Uri.parse('http://${server.address.address}:${server.port}'),
        );
        try {
          await api.changePassword(
            token: 'token',
            currentPassword: 'old',
            newPassword: 'short',
          );
          fail('Expected rejected password');
        } on ApiFailure catch (error) {
          expect(error.statusCode, status);
          expect(error.kind, ApiFailureKind.invalidRequest);
          expect(error.messageKey, key);
          expect(error.passwordField, field);
          expect(error.parameters, parameters);
        }
      },
    );
  }

  test('unknown password errors never expose raw server details', () async {
    final server = await _server((request) async {
      request.response
        ..statusCode = 422
        ..headers.contentType = ContentType.json
        ..write(
          jsonEncode({'detail': 'private diagnostic or reflected password'}),
        );
      await request.response.close();
    });
    addTearDown(() => server.close(force: true));
    final api = IoAuthApi(
      Uri.parse('http://${server.address.address}:${server.port}'),
    );
    try {
      await api.changePassword(
        token: 'token',
        currentPassword: 'old',
        newPassword: 'short',
      );
      fail('Expected rejected password');
    } on ApiFailure catch (error) {
      expect(error.messageKey, isNull);
      expect(error.passwordField, isNull);
      expect(error.parameters, isEmpty);
    }
  });

  test(
    'cooldown falls back to server Retry-After for malformed seconds',
    () async {
      final server = await _server((request) async {
        request.response
          ..statusCode = 429
          ..headers.contentType = ContentType.json
          ..headers.set(HttpHeaders.retryAfterHeader, '30')
          ..write(
            jsonEncode({
              'detail': {
                'code': 'password_attempts_locked',
                'message_key': 'authentication.error.password_attempts_locked',
                'parameters': {'seconds': -1},
              },
            }),
          );
        await request.response.close();
      });
      addTearDown(() => server.close(force: true));
      final api = IoAuthApi(
        Uri.parse('http://${server.address.address}:${server.port}'),
      );
      try {
        await api.changePassword(
          token: 'token',
          currentPassword: 'old',
          newPassword: 'short',
        );
        fail('Expected cooldown');
      } on ApiFailure catch (error) {
        expect(error.parameters, {'seconds': 30});
        expect(
          error.messageKey,
          'authentication.error.password_attempts_locked',
        );
      }
    },
  );

  test('authentication failure remains non-disclosing category', () async {
    final server = await _server((request) async {
      request.response
        ..statusCode = HttpStatus.unauthorized
        ..headers.contentType = ContentType.json
        ..write(jsonEncode({'detail': 'invalid email or password'}));
      await request.response.close();
    });
    addTearDown(() => server.close(force: true));
    final api = IoAuthApi(
      Uri.parse('http://${server.address.address}:${server.port}'),
    );

    expect(
      () => api.signIn(email: 'user@example.test', password: 'wrong'),
      throwsA(
        isA<ApiFailure>().having(
          (failure) => failure.kind,
          'kind',
          ApiFailureKind.unauthenticated,
        ),
      ),
    );
  });

  test('successful login without session cookie is rejected', () async {
    final server = await _server((request) async {
      request.response
        ..headers.contentType = ContentType.json
        ..write(jsonEncode(_principalJson()));
      await request.response.close();
    });
    addTearDown(() => server.close(force: true));
    final api = IoAuthApi(
      Uri.parse('http://${server.address.address}:${server.port}'),
    );

    expect(
      () => api.signIn(email: 'user@example.test', password: 'password'),
      throwsA(
        isA<ApiFailure>().having(
          (failure) => failure.kind,
          'kind',
          ApiFailureKind.invalidResponse,
        ),
      ),
    );
  });
  test(
    'mobile destinations come from the approved bearer-authenticated response',
    () async {
      late HttpRequest received;
      final server = await _server((request) async {
        received = request;
        request.response.headers.contentType = ContentType.json;
        request.response.write(
          jsonEncode(['dashboard', 'user-profile', 'sign-out']),
        );
        await request.response.close();
      });
      addTearDown(() => server.close(force: true));
      final api = IoAuthApi(
        Uri.parse('http://${server.address.address}:${server.port}'),
      );
      expect(await api.mobileCapabilities('session-token'), [
        'dashboard',
        'user-profile',
        'sign-out',
      ]);
      expect(received.uri.path, '/api/v1/auth/me/mobile-capabilities');
      expect(
        received.headers.value(HttpHeaders.authorizationHeader),
        'Bearer session-token',
      );
    },
  );

  test('malformed mobile destination response is rejected', () async {
    final server = await _server((request) async {
      request.response.headers.contentType = ContentType.json;
      request.response.write(jsonEncode(['dashboard', 42]));
      await request.response.close();
    });
    addTearDown(() => server.close(force: true));
    final api = IoAuthApi(
      Uri.parse('http://${server.address.address}:${server.port}'),
    );
    expect(
      () => api.mobileCapabilities('session-token'),
      throwsA(isA<ApiFailure>()),
    );
  });
}

Future<HttpServer> _server(
  Future<void> Function(HttpRequest request) handler,
) async {
  final server = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
  server.listen(handler);
  return server;
}

Map<String, Object?> _principalJson() => {
  'user': {
    'id': 7,
    'name': 'Records User',
    'email': 'user@example.test',
    'account_type': 'person',
    'localized': {'name': 'Records User'},
  },
  'roles': [
    {
      'id': 2,
      'code': 'records-user',
      'name': 'Records User',
      'org_unit': {'id': 1, 'code': 'root', 'name': 'Root'},
    },
  ],
  'session': {'id': 19},
  'must_change_password': false,
  'previous_login_at': null,
  'global_privileges': ['records.view'],
};
