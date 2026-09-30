import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';

import '../core/design/wathiq_theme.dart';
import '../core/localization/message_catalogue.dart';

class WathiqApp extends StatelessWidget {
  const WathiqApp({required this.catalogue, this.locale, super.key});

  final MessageCatalogue catalogue;
  final Locale? locale;

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      debugShowCheckedModeBanner: false,
      title: 'Wathiq',
      locale: locale,
      supportedLocales: MessageCatalogue.supportedLocales,
      localizationsDelegates: const [
        GlobalMaterialLocalizations.delegate,
        GlobalWidgetsLocalizations.delegate,
        GlobalCupertinoLocalizations.delegate,
      ],
      localeResolutionCallback: (deviceLocale, supportedLocales) {
        if (deviceLocale?.languageCode == 'ar') {
          return MessageCatalogue.arabicLocale;
        }
        return MessageCatalogue.englishLocale;
      },
      theme: WathiqTheme.light,
      home: _FoundationScreen(catalogue: catalogue),
    );
  }
}

class _FoundationScreen extends StatelessWidget {
  const _FoundationScreen({required this.catalogue});

  final MessageCatalogue catalogue;

  @override
  Widget build(BuildContext context) {
    final locale = Localizations.localeOf(context);
    return Scaffold(
      appBar: AppBar(title: const Text('Wathiq')),
      body: SafeArea(
        child: Center(
          child: Text(
            catalogue.text('navigation.item.dashboard', locale),
            style: Theme.of(context).textTheme.headlineMedium,
          ),
        ),
      ),
    );
  }
}
