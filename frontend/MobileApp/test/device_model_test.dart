import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:wathiq_mobile/features/auth/data/auth_api.dart';

void main() {
  test('model sanitization bounds header content', () {
    expect(IoAuthApi.sanitizeDeviceModel('Pixel\r\n8; (test)'), 'Pixel 8 test');
    expect(IoAuthApi.sanitizeDeviceModel('  '), isNull);
    expect(IoAuthApi.sanitizeDeviceModel('x' * 101)!.length, 100);
  });

  for (final platform in ['ios', 'android']) {
    test(
      '$platform model is transmitted in the recorded login header',
      () async {
        final server = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
        addTearDown(() => server.close(force: true));
        final received = server.first.then((request) async {
          final agent = request.headers.value(HttpHeaders.userAgentHeader);
          await request.drain<void>();
          request.response.statusCode = 401;
          await request.response.close();
          return agent;
        });
        final api = IoAuthApi(
          Uri.parse('http://127.0.0.1:${server.port}'),
          platformFamily: platform,
          deviceModel: 'Example Model',
        );
        try {
          await api.signIn(email: 'test@example.org', password: 'test');
        } catch (_) {}
        expect(
          await received,
          'WathiqMobile/0.1 ($platform; model=Example Model)',
        );
      },
    );
  }
}
