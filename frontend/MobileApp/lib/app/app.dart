import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';

import '../core/design/wathiq_theme.dart';
import '../core/localization/message_catalogue.dart';
import '../features/auth/application/session_controller.dart';
import '../features/auth/presentation/authentication_screen.dart';
import '../features/auth/presentation/password_change_screen.dart';
import '../features/shell/presentation/authenticated_shell.dart';

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
          SessionStatus.signingOut => AuthenticatedShell(
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
