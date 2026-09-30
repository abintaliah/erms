import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:wathiq_mobile/core/network/api_failure.dart';
import 'package:wathiq_mobile/features/auth/data/auth_api.dart';

void main() {
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
    await api.changePassword(
      token: 'memory-token',
      currentPassword: 'current-secret',
      newPassword: 'new-secret-value',
    );
    await api.signOut('memory-token');

    expect(requests.map((request) => request.uri.path), [
      '/api/v1/auth/me',
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
  });

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
