import 'dart:convert';
import 'dart:io';

import 'package:integration_test/integration_test_driver_extended.dart';

Future<void> main() async {
  final output = Directory('../../.runtime/language-acceptance')
    ..createSync(recursive: true);
  await integrationDriver(
    onScreenshot: (name, bytes, [arguments]) async {
      await File('${output.path}/$name.png').writeAsBytes(bytes);
      return bytes.isNotEmpty;
    },
    responseDataCallback: (data) async {
      if (data == null) return;
      // Screenshots are saved separately; avoid duplicating their bytes in JSON.
      final summary = Map<String, dynamic>.from(data)..remove('screenshots');
      final screenshots = data['screenshots'] as List<dynamic>;
      final firstName =
          (screenshots.first as Map<String, dynamic>)['screenshotName']
              as String;
      final platform = firstName.split('-').first;
      summary['screenshot_files'] = screenshots
          .map(
            (item) => '${(item as Map<String, dynamic>)['screenshotName']}.png',
          )
          .toList();
      await File('${output.path}/$platform-results.json').writeAsString(
        '${const JsonEncoder.withIndent('  ').convert(summary)}\n',
      );
    },
  );
}
