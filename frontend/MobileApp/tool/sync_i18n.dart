import 'dart:convert';
import 'dart:io';

const _englishSource = '../webui/i18n/messages.en.json';
const _arabicSource = '../webui/i18n/messages.ar.generated.json';
const _englishTarget = 'assets/i18n/messages.en.json';
const _arabicTarget = 'assets/i18n/messages.ar.json';

Never _fail(String message) {
  stderr.writeln(message);
  exit(1);
}

void main() {
  final englishFile = File(_englishSource);
  final arabicFile = File(_arabicSource);
  if (!englishFile.existsSync() || !arabicFile.existsSync()) {
    _fail(
      'Run this tool from frontend/MobileApp. Canonical catalogues missing.',
    );
  }

  final englishDocument = jsonDecode(englishFile.readAsStringSync());
  final arabicDocument = jsonDecode(arabicFile.readAsStringSync());
  if (englishDocument is! List || arabicDocument is! Map<String, dynamic>) {
    _fail('Canonical catalogue shape is invalid.');
  }

  final arabicItems = arabicDocument['items'];
  if (arabicItems is! List) {
    _fail('Canonical Arabic catalogue has no items list.');
  }

  final english = <String, String>{};
  for (final item in englishDocument) {
    if (item is! Map<String, dynamic>) _fail('Invalid English catalogue item.');
    final key = item['message_key'];
    final text = item['default_text'];
    if (key is! String || text is! String || text.trim().isEmpty) {
      _fail('Invalid English message key or text.');
    }
    if (english.containsKey(key)) _fail('Duplicate English message key: $key');
    english[key] = text;
  }

  final arabic = <String, String>{};
  for (final item in arabicItems) {
    if (item is! Map<String, dynamic>) _fail('Invalid Arabic catalogue item.');
    final key = item['message_key'];
    final text = item['translated_text'];
    if (key is! String || text is! String || text.trim().isEmpty) {
      _fail('Invalid Arabic message key or text.');
    }
    if (arabic.containsKey(key)) _fail('Duplicate Arabic message key: $key');
    arabic[key] = text;
  }

  final englishKeys = english.keys.toSet();
  final arabicKeys = arabic.keys.toSet();
  if (englishKeys.length != arabicKeys.length ||
      !englishKeys.containsAll(arabicKeys)) {
    _fail('English and Arabic active-key coverage differs.');
  }

  Map<String, String> sorted(Map<String, String> source) {
    final keys = source.keys.toList()..sort();
    return {for (final key in keys) key: source[key]!};
  }

  void write(String path, Map<String, String> messages) {
    final file = File(path)..parent.createSync(recursive: true);
    file.writeAsStringSync(
      '${const JsonEncoder.withIndent('  ').convert(messages)}\n',
    );
  }

  write(_englishTarget, sorted(english));
  write(_arabicTarget, sorted(arabic));
  stdout.writeln('Synchronized ${english.length} English and Arabic messages.');
}
