import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';

import '../core/design/wathiq_theme.dart';
import '../core/localization/message_catalogue.dart';
import '../features/auth/application/session_controller.dart';
import '../features/auth/presentation/authentication_screen.dart';
import '../features/auth/presentation/password_change_screen.dart';

class WathiqApp extends StatelessWidget {
  const WathiqApp({
    required this.catalogue,
    required this.sessionController,
    super.key,
  });

  final MessageCatalogue catalogue;
  final SessionController sessionController;

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: sessionController,
      builder: (context, _) => MaterialApp(
        debugShowCheckedModeBanner: false,
        title: 'Wathiq',
        locale: Locale(sessionController.effectiveLanguageTag),
        supportedLocales: MessageCatalogue.supportedLocales,
        localizationsDelegates: const [
          GlobalMaterialLocalizations.delegate,
          GlobalWidgetsLocalizations.delegate,
          GlobalCupertinoLocalizations.delegate,
        ],
        theme: WathiqTheme.light,
        home: switch (sessionController.status) {
          SessionStatus.passwordChangeRequired ||
          SessionStatus.changingPassword => PasswordChangeScreen(
            catalogue: catalogue,
            controller: sessionController,
          ),
          SessionStatus.authenticated ||
          SessionStatus.signingOut => _FoundationScreen(
            catalogue: catalogue,
            controller: sessionController,
          ),
          _ => AuthenticationScreen(
            catalogue: catalogue,
            controller: sessionController,
          ),
        },
      ),
    );
  }
}

class _FoundationScreen extends StatelessWidget {
  const _FoundationScreen({required this.catalogue, required this.controller});

  final MessageCatalogue catalogue;
  final SessionController controller;

  @override
  Widget build(BuildContext context) {
    final locale = Localizations.localeOf(context);
    return Scaffold(
      appBar: AppBar(
        title: Text(
          catalogue.text('webui.index.label.wathiq_d1dfb800', locale),
        ),
        actions: [
          IconButton(
            onPressed: controller.status == SessionStatus.signingOut
                ? null
                : controller.signOut,
            tooltip: catalogue.text(
              'webui.index.button.sign_out_a4610dd4',
              locale,
            ),
            icon: const Icon(Icons.logout),
          ),
        ],
      ),
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
