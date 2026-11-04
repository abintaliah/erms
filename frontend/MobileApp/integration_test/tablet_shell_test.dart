import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';
import 'package:wathiq_mobile/app/app.dart';
import 'package:wathiq_mobile/core/localization/message_catalogue.dart';
import 'package:wathiq_mobile/features/auth/application/session_controller.dart';
import 'package:wathiq_mobile/features/auth/data/auth_api.dart';
import 'package:wathiq_mobile/features/auth/domain/auth_principal.dart';

// Test-only composition: production UI and catalogues, no real account/database.
void main() {
  final binding = IntegrationTestWidgetsFlutterBinding.ensureInitialized();
  testWidgets('tablet landscape language and navigation acceptance', (
    tester,
  ) async {
    final catalogue = await MessageCatalogue.load();
    final controller = SessionController(_TabletAuthApi());
    addTearDown(() async {
      await tester.pumpWidget(const SizedBox.shrink());
      controller.dispose();
    });
    await controller.signIn(
      email: 'tablet@example.test',
      password: 'fixture-only',
    );
    await tester.pumpWidget(
      WathiqApp(catalogue: catalogue, sessionController: controller),
    );
    await tester.pumpAndSettle();
    if (Platform.isAndroid) {
      await binding.convertFlutterSurfaceToImage();
      await tester.pumpAndSettle();
    }

    Size size() => tester.view.physicalSize / tester.view.devicePixelRatio;
    void verifyLandscape() {
      expect(
        size().shortestSide,
        greaterThanOrEqualTo(700),
        reason: 'Use a real tablet target.',
      );
      expect(
        size().width,
        greaterThan(size().height),
        reason: 'Set the tablet simulator to landscape before this test.',
      );
      expect(tester.takeException(), isNull);
    }

    void checkVisible(Finder finder) {
      final bounds = tester.getRect(finder);
      expect(bounds.left, greaterThanOrEqualTo(-1));
      expect(bounds.top, greaterThanOrEqualTo(-1));
      expect(bounds.right, lessThanOrEqualTo(size().width + 1));
      expect(bounds.bottom, lessThanOrEqualTo(size().height + 1));
    }

    Future<void> screenshot(String name) async {
      expect(tester.takeException(), isNull);
      for (final paragraph
          in tester.allRenderObjects.whereType<RenderParagraph>()) {
        expect(
          paragraph.didExceedMaxLines,
          isFalse,
          reason: paragraph.text.toPlainText(),
        );
      }
      binding.reportData ??= <String, dynamic>{};
      binding.reportData!['fixture'] = 'production widgets and canonical catalogues with injected test-only API';
      final metrics = binding.reportData!.putIfAbsent(
        'viewport_checks',
        () => <Map<String, Object>>[],
      ) as List<Map<String, Object>>;
      metrics.add({
        'name': name,
        'width': size().width,
        'height': size().height,
      });
      await binding.takeScreenshot('${Platform.operatingSystem}-$name');
    }

    for (final language in ['en', 'ar']) {
      await tester.tap(find.byKey(const ValueKey('shell-preferences')));
      await tester.pumpAndSettle();
      await tester.tap(find.text(language == 'ar' ? 'العربية' : 'English'));
      await tester.pumpAndSettle();
      expect(controller.effectiveLanguageTag, language);
      expect(
        Directionality.of(tester.element(find.byType(Scaffold).last)),
        language == 'ar' ? TextDirection.rtl : TextDirection.ltr,
      );
      await screenshot('$language-landscape-preferences');
      await tester.tap(find.byType(BackButton));
      await tester.pumpAndSettle();

      {
        verifyLandscape();
        final suffix = '$language-landscape';
        final dashboard = find.byKey(const ValueKey('shell-dashboard'));
        final navigationX = tester.getCenter(dashboard).dx;
        expect(
          language == 'ar'
              ? navigationX > size().width / 2
              : navigationX < size().width / 2,
          isTrue,
        );
        for (final id in [
          'global-search',
          'dashboard',
          'classification-browser',
          'favourites',
          'recent-activity',
          'profile',
          'preferences',
          'sign-out',
        ]) {
          final tile = find.byKey(ValueKey('shell-$id'));
          await tester.ensureVisible(tile);
          checkVisible(tile);
        }
        await screenshot('$suffix-shell');
        for (final id in [
          'global-search',
          'classification-browser',
          'favourites',
          'recent-activity',
        ]) {
          final tile = find.byKey(ValueKey('shell-$id'));
          await tester.ensureVisible(tile);
          await tester.tap(tile);
          await tester.pumpAndSettle();
          final destination = find.byKey(ValueKey('destination-$id'));
          expect(destination, findsOneWidget);
          if (id == 'favourites') {
            expect(destination, findsOneWidget);
            await screenshot('$suffix-retained-favourites');
          }
          await tester.tap(find.byType(BackButton));
          await tester.pumpAndSettle();
          expect(
            find.byKey(const ValueKey('authenticated-shell')),
            findsOneWidget,
          );

          expect(tester.takeException(), isNull);
        }
        await tester.ensureVisible(find.byKey(const ValueKey('shell-profile')));
        await tester.tap(find.byKey(const ValueKey('shell-profile')));
        await tester.pumpAndSettle();
        expect(find.text('Tablet Acceptance'), findsWidgets);
        await tester.tap(find.byType(BackButton));
        await tester.pumpAndSettle();
      }
    }
    // Switch back through the real preference control without losing identity.
    await tester.tap(find.byKey(const ValueKey('shell-preferences')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('English'));
    await tester.pumpAndSettle();
    expect(controller.effectiveLanguageTag, 'en');
    expect(controller.principal?.user.id, 1);
    expect(tester.takeException(), isNull);
  });
}

class _TabletAuthApi implements AuthApi {
  String language = 'en';
  int version = 1;
  final principal = const AuthPrincipal(
    user: AuthUser(
      id: 1,
      name: 'Tablet Acceptance',
      email: 'tablet@example.test',
      accountType: 'person',
    ),
    sessionId: 1,
    mustChangePassword: false,
    globalPrivileges: {},
    roles: [],
  );
  @override
  Future<AuthSession> signIn({
    required String email,
    required String password,
  }) async =>
      AuthSession(principal: principal, token: 'test-only-memory-token');
  @override
  Future<AuthPrincipal> currentPrincipal(String token) async => principal;
  @override
  Future<AuthPrincipal> sessionStatus(String token) async => principal;
  @override
  Future<List<String>> mobileCapabilities(String token) async => [
    'global-search',
    'dashboard',
    'classification-browser',
    'favourites',
    'recent-activity',
    'user-profile',
    'sign-out',
  ];
  @override
  Future<String> effectiveLanguage(String token) async => language;
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
    version: version,
  );
  @override
  Future<UserPreferences> updatePreferences({
    required String token,
    required String languageTag,
    required String workingTimezone,
    required int version,
  }) async {
    language = languageTag;
    this.version++;
    return UserPreferences(
      languageTag: language,
      workingTimezone: workingTimezone,
      version: this.version,
    );
  }

  @override
  Future<void> changePassword({
    required String token,
    required String currentPassword,
    required String newPassword,
  }) async {}
  @override
  Future<void> signOut(String token) async {}
}
