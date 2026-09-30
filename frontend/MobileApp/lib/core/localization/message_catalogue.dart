import 'dart:convert';

import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';

class MessageCatalogue {
  const MessageCatalogue({required this.english, required this.arabic});

  static const englishLocale = Locale('en');
  static const arabicLocale = Locale('ar');
  static const supportedLocales = [englishLocale, arabicLocale];

  final Map<String, String> english;
  final Map<String, String> arabic;

  static Future<MessageCatalogue> load() async {
    final values = await Future.wait([
      rootBundle.loadString('assets/i18n/messages.en.json'),
      rootBundle.loadString('assets/i18n/messages.ar.json'),
    ]);
    return MessageCatalogue.fromJson(values[0], values[1]);
  }

  factory MessageCatalogue.fromJson(String englishJson, String arabicJson) {
    Map<String, String> decode(String source) {
      final value = jsonDecode(source);
      if (value is! Map<String, dynamic>) {
        throw const FormatException('Message catalogue must be a JSON object.');
      }
      return value.map((key, text) {
        if (text is! String || text.trim().isEmpty) {
          throw FormatException('Invalid translation for $key.');
        }
        return MapEntry(key, text);
      });
    }

    final english = decode(englishJson);
    final arabic = decode(arabicJson);
    if (!english.keys.toSet().containsAll(arabic.keys) ||
        !arabic.keys.toSet().containsAll(english.keys)) {
      throw const FormatException(
        'English and Arabic message keys must have exact coverage.',
      );
    }
    return MessageCatalogue(english: english, arabic: arabic);
  }

  String text(String key, Locale locale) {
    final messages = locale.languageCode == arabicLocale.languageCode
        ? arabic
        : english;
    final value = messages[key];
    if (value == null) {
      throw StateError('Missing active message key: $key');
    }
    return value;
  }
}
