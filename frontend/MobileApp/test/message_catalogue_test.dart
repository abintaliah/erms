import 'dart:convert';
import 'dart:io';

import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:wathiq_mobile/core/localization/message_catalogue.dart';

void main() {
  test('generated catalogues exactly match their canonical sources', () {
    final english = File('assets/i18n/messages.en.json').readAsStringSync();
    final arabic = File('assets/i18n/messages.ar.json').readAsStringSync();
    final catalogue = MessageCatalogue.fromJson(english, arabic);
    final canonicalEnglish = jsonDecode(
      File('../webui/i18n/messages.en.json').readAsStringSync(),
    ) as List<dynamic>;
    final canonicalArabic = jsonDecode(
      File('../webui/i18n/messages.ar.generated.json').readAsStringSync(),
    ) as Map<String, dynamic>;
    final expectedEnglish = {
      for (final item in canonicalEnglish.cast<Map<String, dynamic>>())
        item['message_key'] as String: item['default_text'] as String,
    };
    final expectedArabic = {
      for (final item
          in (canonicalArabic['items'] as List<dynamic>)
              .cast<Map<String, dynamic>>())
        item['message_key'] as String: item['translated_text'] as String,
    };

    expect(jsonDecode(english), expectedEnglish);
    expect(jsonDecode(arabic), expectedArabic);
    expect(
      catalogue.text('navigation.item.dashboard', const Locale('en')),
      isNotEmpty,
    );
    expect(
      catalogue.text('navigation.item.dashboard', const Locale('ar')),
      isNotEmpty,
    );
  });

  test('localized feedback substitutes server parameters without exposing placeholders', () {
    const catalogue = MessageCatalogue(
      english: {'example': 'At least {minimum} characters.'},
      arabic: {'example': '{minimum} حرفًا على الأقل.'},
    );
    expect(
      catalogue.text(
        'example',
        const Locale('en'),
        parameters: {'minimum': 15},
      ),
      'At least 15 characters.',
    );
    expect(
      catalogue.text(
        'example',
        const Locale('ar'),
        parameters: {'minimum': 15},
      ),
      '15 حرفًا على الأقل.',
    );
    expect(
      () => catalogue.text('example', const Locale('en')),
      throwsArgumentError,
    );
  });

  test('catalogue rejects blank translations', () {
    expect(
      () => MessageCatalogue.fromJson(
        jsonEncode({'key.one': 'One'}),
        jsonEncode({'key.one': '  '}),
      ),
      throwsFormatException,
    );
  });

  test('catalogue rejects unequal language coverage', () {
    expect(
      () => MessageCatalogue.fromJson(
        jsonEncode({'key.one': 'One'}),
        jsonEncode({'key.two': 'اثنان'}),
      ),
      throwsFormatException,
    );
  });
}
