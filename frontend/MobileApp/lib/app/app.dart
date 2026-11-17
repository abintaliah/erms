import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';

import '../core/design/wathiq_theme.dart';
import '../core/network/api_failure.dart';
import '../core/localization/message_catalogue.dart';
import '../features/auth/application/session_controller.dart';
import '../features/auth/presentation/authentication_screen.dart';
import '../features/auth/presentation/password_change_screen.dart';
import '../features/shell/presentation/authenticated_shell.dart';

class WathiqApp extends StatefulWidget {
  const WathiqApp({
    required this.catalogue,
    required this.sessionController,
    super.key,
  });

  final MessageCatalogue catalogue;
  final SessionController sessionController;

  @override
  State<WathiqApp> createState() => _WathiqAppState();
}

class _WathiqAppState extends State<WathiqApp> with WidgetsBindingObserver {
  SessionController get sessionController => widget.sessionController;
  MessageCatalogue get catalogue => widget.catalogue;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  @override
  void didChangeLocales(List<Locale>? locales) {
    if (!sessionController.hasEffectiveLanguagePreference) {
      setState(() {});
    }
  }

  Locale get _effectiveLocale {
    if (sessionController.hasEffectiveLanguagePreference) {
      return Locale(sessionController.effectiveLanguageTag);
    }
    final deviceLanguage =
        WidgetsBinding.instance.platformDispatcher.locale.languageCode;
    return deviceLanguage == 'ar'
        ? MessageCatalogue.arabicLocale
        : MessageCatalogue.englishLocale;
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.hidden ||
        state == AppLifecycleState.paused) {
      unawaited(sessionController.onBackgrounded());
    } else if (state == AppLifecycleState.resumed) {
      unawaited(sessionController.onResumed());
    }
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: sessionController,
      builder: (context, _) => MaterialApp(
        key: ValueKey(sessionController.sessionGeneration),
        debugShowCheckedModeBanner: false,
        title: 'Wathiq',
        locale: _effectiveLocale,
        supportedLocales: MessageCatalogue.supportedLocales,
        localizationsDelegates: const [
          GlobalMaterialLocalizations.delegate,
          GlobalWidgetsLocalizations.delegate,
          GlobalCupertinoLocalizations.delegate,
        ],
        theme: WathiqTheme.light,
        builder: (context, child) => Stack(
          children: [
            ?child,
            if (sessionController.status == SessionStatus.validatingSession ||
                sessionController.status == SessionStatus.signingOut) ...[
              const ModalBarrier(dismissible: false, color: Colors.black45),
              Center(
                child: _SessionValidationScreen(
                  catalogue: catalogue,
                  controller: sessionController,
                ),
              ),
            ],
          ],
        ),
        home: switch (sessionController.status) {
          SessionStatus.passwordChangeRequired ||
          SessionStatus.changingPassword => PasswordChangeScreen(
            catalogue: catalogue,
            controller: sessionController,
          ),
          SessionStatus.validatingSession || SessionStatus.signingOut
              when sessionController.principal?.mustChangePassword == true =>
            PasswordChangeScreen(
              catalogue: catalogue,
              controller: sessionController,
            ),
          SessionStatus.authenticated ||
          SessionStatus.validatingSession ||
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

class _SessionValidationScreen extends StatefulWidget {
  const _SessionValidationScreen({
    required this.catalogue,
    required this.controller,
  });
  final MessageCatalogue catalogue;
  final SessionController controller;

  @override
  State<_SessionValidationScreen> createState() =>
      _SessionValidationScreenState();
}

class _SessionValidationScreenState extends State<_SessionValidationScreen> {
  Timer? _reconnect;
  bool _checking = false;
  SessionController get controller => widget.controller;
  MessageCatalogue get catalogue => widget.catalogue;

  @override
  void initState() {
    super.initState();
    // One bounded safe-read probe only while the foreground offline gate exists.
    // No mutation retries; the retained Navigator remains blocked until success.
    _reconnect = Timer.periodic(const Duration(seconds: 30), (_) async {
      if (_checking ||
          !mounted ||
          controller.status != SessionStatus.validatingSession ||
          controller.failure?.kind != ApiFailureKind.offline ||
          WidgetsBinding.instance.lifecycleState != AppLifecycleState.resumed) {
        return;
      }
      _checking = true;
      try {
        await controller.validateSession();
      } finally {
        _checking = false;
      }
    });
  }

  @override
  void dispose() {
    _reconnect?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    String text(String key) =>
        catalogue.text(key, Localizations.localeOf(context));
    return Dialog(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            if (controller.failure == null ||
                controller.status == SessionStatus.signingOut) ...[
              const CircularProgressIndicator(),
              Text(
                text(
                  controller.status == SessionStatus.signingOut
                      ? 'webui.index.button.sign_out_a4610dd4'
                      : 'mobile.state.validating_session',
                ),
              ),
            ] else ...[
              Text(
                text(
                  controller.failure?.kind == ApiFailureKind.offline
                      ? 'mobile.state.offline'
                      : 'common.error.service_unavailable',
                ),
              ),
              const SizedBox(height: 16),
              FilledButton(
                onPressed: controller.validateSession,
                child: Text(text('classification_browser.retry')),
              ),
            ],
            TextButton(
              onPressed: controller.signOut,
              child: Text(text('webui.index.button.sign_out_a4610dd4')),
            ),
          ],
        ),
      ),
    );
  }
}
