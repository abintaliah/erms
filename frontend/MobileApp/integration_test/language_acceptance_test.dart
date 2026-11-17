import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';
import 'package:wathiq_mobile/app/app.dart';
import 'package:wathiq_mobile/core/localization/message_catalogue.dart';
import 'package:wathiq_mobile/core/network/api_failure.dart';
import 'package:wathiq_mobile/features/auth/application/session_controller.dart';
import 'package:wathiq_mobile/features/auth/data/auth_api.dart';
import 'package:wathiq_mobile/features/auth/domain/auth_principal.dart';

// Native rendering with controlled Flutter platform-locale values and an
// injected API. No real credentials, OS language changes or database access.
void main() {
  final binding = IntegrationTestWidgetsFlutterBinding.ensureInitialized();
  testWidgets('native device-language and saved-preference acceptance', (
    tester,
  ) async {
    final catalogue = await MessageCatalogue.load();
    final cases = <Map<String, Object>>[];
    binding.reportData = {
      'fixture': 'production widgets/canonical catalogues; injected AuthApi and platform locale; no ERMS database',
      'cases': cases,
    };
    addTearDown(tester.platformDispatcher.clearLocaleTestValue);
    var surfaceReady = false;

    Future<void> capture(String name) async {
      FocusManager.instance.primaryFocus?.unfocus();
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull);
      for (final paragraph
          in tester.allRenderObjects.whereType<RenderParagraph>()) {
        expect(
          paragraph.didExceedMaxLines,
          isFalse,
          reason: paragraph.text.toPlainText(),
        );
      }
      if (Platform.isAndroid && !surfaceReady) {
        await binding.convertFlutterSurfaceToImage();
        await tester.pumpAndSettle();
        surfaceReady = true;
      }
      await binding.takeScreenshot('${Platform.operatingSystem}-$name');
    }

    void verifyDirection(Key key, String language) {
      expect(
        Directionality.of(tester.element(find.byKey(key))),
        language == 'ar' ? TextDirection.rtl : TextDirection.ltr,
      );
    }

    for (final primary in ['en', 'ar', 'fr']) {
      final fallback = primary == 'ar' ? 'ar' : 'en';
      final saved = fallback == 'ar' ? 'en' : 'ar';
      tester.platformDispatcher.localeTestValue = Locale(
        primary,
        primary == 'ar' ? 'AE' : null,
      );
      final api = _LanguageAuthApi(saved);
      final controller = SessionController(api);
      await tester.pumpWidget(
        WathiqApp(catalogue: catalogue, sessionController: controller),
      );
      await tester.pumpAndSettle();
      final viewport = tester.view.physicalSize / tester.view.devicePixelRatio;
      expect(
        viewport.shortestSide,
        lessThan(700),
        reason: 'Use a native phone target; no synthetic viewport resize.',
      );
      expect(viewport.width, lessThan(viewport.height));
      verifyDirection(const ValueKey('sign-in-email'), fallback);
      expect(
        find.text(
          catalogue.text(
            'webui.index.input.email_address_2569f0e9',
            Locale(fallback),
          ),
        ),
        findsOneWidget,
      );
      await capture('$primary-sign-in');

      // A device-language change before preference initialization must be live.
      tester.platformDispatcher.localeTestValue = Locale(
        fallback == 'ar' ? 'en' : 'ar',
      );
      await tester.pumpAndSettle();
      verifyDirection(
        const ValueKey('sign-in-email'),
        fallback == 'ar' ? 'en' : 'ar',
      );
      tester.platformDispatcher.localeTestValue = Locale(primary);
      await tester.pumpAndSettle();
      await tester.enterText(
        find.byKey(const ValueKey('sign-in-email')),
        'language@example.test',
      );
      await tester.enterText(
        find.byKey(const ValueKey('sign-in-password')),
        'fixture-only',
      );
      await tester.pumpAndSettle();
      await tester.ensureVisible(find.byKey(const ValueKey('sign-in-submit')));
      await tester.tap(find.byKey(const ValueKey('sign-in-submit')));
      await tester.pumpAndSettle();
      expect(controller.status, SessionStatus.passwordChangeRequired);
      expect(api.bootstrapReads, 0);
      expect(api.capabilityReads, 0);
      verifyDirection(const ValueKey('new-password'), fallback);

      await tester.enterText(
        find.byKey(const ValueKey('current-password')),
        'fixture-only',
      );
      await tester.enterText(
        find.byKey(const ValueKey('new-password')),
        'tiny',
      );
      await tester.enterText(
        find.byKey(const ValueKey('confirm-password')),
        'tiny',
      );
      await tester.pumpAndSettle();
      await tester.ensureVisible(
        find.byKey(const ValueKey('password-change-submit')),
      );
      await tester.tap(find.byKey(const ValueKey('password-change-submit')));
      await tester.pumpAndSettle();
      expect(
        tester
            .widget<TextField>(find.byKey(const ValueKey('new-password')))
            .decoration!
            .errorText,
        catalogue.text(
          'mobile.authentication.password_too_short',
          Locale(fallback),
          parameters: {'minimum': 12},
        ),
      );
      await tester.enterText(
        find.byKey(const ValueKey('confirm-password')),
        'different',
      );
      await tester.pumpAndSettle();
      expect(
        tester
            .widget<TextField>(find.byKey(const ValueKey('confirm-password')))
            .decoration!
            .errorText,
        catalogue.text(
          'webui.save_password.notify.new_passwords_do_not_match_26d93e32',
          Locale(fallback),
        ),
      );
      expect(
        tester
            .widget<FilledButton>(
              find.byKey(const ValueKey('password-change-submit')),
            )
            .onPressed,
        isNull,
      );
      await capture('$primary-password-feedback');

      await tester.enterText(
        find.byKey(const ValueKey('new-password')),
        'fixture-replacement',
      );
      await tester.enterText(
        find.byKey(const ValueKey('confirm-password')),
        'fixture-replacement',
      );
      await tester.pumpAndSettle();
      await tester.ensureVisible(
        find.byKey(const ValueKey('password-change-submit')),
      );
      await tester.tap(find.byKey(const ValueKey('password-change-submit')));
      await tester.pumpAndSettle();
      expect(controller.status, SessionStatus.authenticated);
      expect(controller.hasEffectiveLanguagePreference, isTrue);
      expect(controller.effectiveLanguageTag, saved);
      verifyDirection(const ValueKey('authenticated-shell'), saved);
      expect(
        find.text(catalogue.text('navigation.item.dashboard', Locale(saved))),
        findsWidgets,
      );
      await capture('$primary-saved-$saved-shell');
      tester.platformDispatcher.localeTestValue = Locale(fallback);
      await tester.pumpAndSettle();
      verifyDirection(const ValueKey('authenticated-shell'), saved);
      tester.platformDispatcher.localeTestValue = Locale(primary);
      await tester.pumpAndSettle();
      await controller.signOut();
      await tester.pumpAndSettle();
      expect(controller.hasEffectiveLanguagePreference, isFalse);
      verifyDirection(const ValueKey('sign-in-email'), fallback);
      await controller.signIn(
        email: 'language@example.test',
        password: 'fixture-replacement',
      );
      await tester.pumpAndSettle();
      expect(controller.effectiveLanguageTag, saved);
      controller.clearForRevocation();
      await tester.pumpAndSettle();
      verifyDirection(const ValueKey('sign-in-email'), fallback);
      expect(controller.hasProtectedState, isFalse);
      expect(controller.hasEffectiveLanguagePreference, isFalse);
      cases.add({
        'platform_locale': primary,
        'fallback': fallback,
        'saved_language': saved,
        'width': viewport.width,
        'height': viewport.height,
        'passed': true,
        'checks': [
          'sign-in copy/direction',
          'live pre-auth locale change',
          'credential gate',
          'minimum-length feedback',
          'confirmation mismatch',
          'saved-language override',
          'device change cannot override preference',
          'sign-out fallback',
          'revocation fallback',
        ],
      });
      await tester.pumpWidget(const SizedBox.shrink());
      controller.dispose();
    }
    expect(tester.takeException(), isNull);
  });
}

class _LanguageAuthApi implements AuthApi {
  _LanguageAuthApi(this.language);
  String language;
  bool mustChange = true;
  int bootstrapReads = 0;
  int capabilityReads = 0;
  AuthPrincipal get principal => AuthPrincipal(
    user: const AuthUser(
      id: 1,
      name: 'Language Acceptance',
      email: 'language@example.test',
      accountType: 'person',
    ),
    sessionId: 1,
    mustChangePassword: mustChange,
    globalPrivileges: const {},
    roles: const [],
  );
  void requireClearance() {
    if (mustChange) {
      throw const ApiFailure(ApiFailureKind.forbidden, statusCode: 403);
    }
  }

  @override
  Future<AuthSession> signIn({
    required String email,
    required String password,
  }) async =>
      AuthSession(principal: principal, token: 'test-only-memory-token');
  @override
  Future<AuthPrincipal> currentPrincipal(String token) async => principal;
  @override
  Future<List<String>> mobileCapabilities(String token) async {
    capabilityReads++;
    requireClearance();
    return ['dashboard', 'user-profile', 'sign-out'];
  }

  @override
  Future<String> effectiveLanguage(String token) async {
    bootstrapReads++;
    requireClearance();
    return language;
  }

  @override
  Future<List<SupportedLanguage>> supportedLanguages(String token) async =>
      const [
        SupportedLanguage(
          languageTag: 'en',
          englishName: 'English',
          nativeName: 'English',
        ),
        SupportedLanguage(
          languageTag: 'ar',
          englishName: 'Arabic',
          nativeName: 'العربية',
        ),
      ];
  @override
  Future<UserPreferences> preferences(String token) async => UserPreferences(
    languageTag: language,
    workingTimezone: 'Asia/Dubai',
    version: 1,
  );
  @override
  Future<UserPreferences> updatePreferences({
    required String token,
    required String languageTag,
    required String workingTimezone,
    required int version,
  }) async {
    language = languageTag;
    return UserPreferences(
      languageTag: language,
      workingTimezone: workingTimezone,
      version: version + 1,
    );
  }

  @override
  Future<void> changePassword({
    required String token,
    required String currentPassword,
    required String newPassword,
  }) async {
    if (newPassword == 'tiny') {
      throw const ApiFailure(
        ApiFailureKind.invalidRequest,
        statusCode: 422,
        messageKey: 'mobile.authentication.password_too_short',
        parameters: {'minimum': 12},
        passwordField: 'new_password',
      );
    }
    mustChange = false;
  }

  @override
  Future<void> signOut(String token) async {}
}
