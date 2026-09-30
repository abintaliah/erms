import 'dart:io';

import 'package:wathiq_mobile/core/config/app_environment.dart';

Future<void> main(List<String> arguments) async {
  if (arguments.length != 1) {
    stderr.writeln(
      'Usage: dart run tool/verify_connectivity.dart <API base URL>',
    );
    exitCode = 64;
    return;
  }

  final environment = AppEnvironment.fromValue(arguments.single);
  final client = HttpClient()..connectionTimeout = const Duration(seconds: 5);

  try {
    final request = await client.getUrl(environment.apiBaseUrl);
    request.headers.set(HttpHeaders.acceptHeader, 'text/html,application/json');
    final response = await request.close().timeout(const Duration(seconds: 10));
    await response.drain<void>();

    if (response.statusCode < 200 || response.statusCode >= 400) {
      throw HttpException(
        'Connectivity check returned HTTP ${response.statusCode}.',
        uri: environment.apiBaseUrl,
      );
    }

    stdout.writeln(
      'Connectivity verified: ${environment.apiBaseUrl} '
      'returned HTTP ${response.statusCode}.',
    );
  } finally {
    client.close(force: true);
  }
}
