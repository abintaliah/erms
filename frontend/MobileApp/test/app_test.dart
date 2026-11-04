import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:wathiq_mobile/app/app.dart';
import 'package:wathiq_mobile/core/localization/message_catalogue.dart';
import 'package:wathiq_mobile/core/network/api_failure.dart';
import 'package:wathiq_mobile/features/auth/application/session_controller.dart';
import 'package:wathiq_mobile/features/auth/data/auth_api.dart';
import 'package:wathiq_mobile/features/auth/domain/auth_principal.dart';

void main() {
  for (final language in ['en', 'ar']) {
    for (final size in [const Size(390, 844), const Size(1024, 768)]) {
      testWidgets(
        'ordered capability drawer and retained Back $language $size',
        (tester) async {
          addTearDown(() => tester.pumpWidget(const SizedBox.shrink()));
          tester.view.physicalSize = size;
          tester.view.devicePixelRatio = 1;
          addTearDown(tester.view.resetPhysicalSize);
          addTearDown(tester.view.resetDevicePixelRatio);
          final controller = SessionController(
            _FakeAuthApi(languageTag: language),
          );
          addTearDown(controller.dispose);
          await controller.signIn(
            email: 'user@example.test',
            password: 'secret',
          );
          await tester.pumpWidget(
            WathiqApp(catalogue: _catalogue, sessionController: controller),
          );
          await tester.pumpAndSettle();
          if (size.width < 700) {
            await tester.tap(
              find.byTooltip(
                language == 'ar' ? 'فتح قائمة التنقل' : 'Open navigation menu',
              ),
            );
            await tester.pumpAndSettle();
          }
          final ids = [
            'global-search',
            'dashboard',
            'classification-browser',
            'favourites',
            'recent-activity',
            'profile',
            'sign-out',
          ];
          double previous = -1;
          for (final id in ids) {
            final tile = find.byKey(ValueKey('shell-$id'));
            await tester.ensureVisible(tile);
            final y = tester.getTopLeft(tile).dy;
            expect(tile, findsOneWidget);
            expect(y, greaterThan(previous));
            previous = y;
          }
          expect(previous, greaterThanOrEqualTo(0));
          final tile = find.byKey(const ValueKey('shell-favourites'));
          await tester.ensureVisible(tile);
          await tester.tap(tile);
          await tester.pumpAndSettle();
          expect(
            find.byKey(const ValueKey('destination-favourites')),
            findsOneWidget,
          );
          await tester.tap(find.byType(BackButton));
          await tester.pumpAndSettle();
          final shell = tester.state<ScaffoldState>(
            find.byKey(const ValueKey('authenticated-shell')),
          );
          expect(shell.isDrawerOpen, isFalse);
          if (size.width < 700) {
            await tester.tap(
              find.byTooltip(
                language == 'ar' ? 'فتح قائمة التنقل' : 'Open navigation menu',
              ),
            );
            await tester.pumpAndSettle();
          }
          await tester.ensureVisible(tile);
          await tester.tap(tile);
          await tester.pumpAndSettle();
          tester.view.physicalSize = Size(size.height, size.width);
          await tester.pumpAndSettle();
          expect(
            find.byKey(const ValueKey('destination-favourites')),
            findsOneWidget,
          );
          await tester.tap(find.byType(BackButton));
          await tester.pumpAndSettle();
          expect(
            find.byKey(const ValueKey('authenticated-shell')),
            findsOneWidget,
          );
          expect(tester.takeException(), isNull);
        },
      );
    }
  }
  testWidgets('disabled server search hides drawer and top-bar entry', (
    tester,
  ) async {
    tester.view.physicalSize = const Size(1024, 768);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final controller = SessionController(_FakeAuthApi(searchEnabled: false));
    addTearDown(controller.dispose);
    await controller.signIn(email: 'user@example.test', password: 'secret');
    await tester.pumpWidget(
      WathiqApp(catalogue: _catalogue, sessionController: controller),
    );
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('shell-global-search')), findsNothing);
    expect(find.byKey(const ValueKey('shell-search-action')), findsNothing);
    expect(
      find.byKey(const ValueKey('shell-classification-browser')),
      findsOneWidget,
    );
  });

  testWidgets('sign-in defaults to English independently of device locale', (
    tester,
  ) async {
    tester.platformDispatcher.localeTestValue = const Locale('ar');
    addTearDown(tester.platformDispatcher.clearLocaleTestValue);
    final controller = SessionController(_FakeAuthApi());
    await tester.pumpWidget(
      WathiqApp(catalogue: _catalogue, sessionController: controller),
    );

    expect(find.byKey(const ValueKey('wathiq-logo-mark')), findsOneWidget);
    expect(find.text('Wathiq'), findsOneWidget);
    expect(find.text('Sign in'), findsNWidgets(2));
    expect(find.text('Email address'), findsOneWidget);
    expect(
      Directionality.of(tester.element(find.text('Email address'))),
      TextDirection.ltr,
    );
  });

  testWidgets('saved Arabic preference becomes authoritative after sign-in', (
    tester,
  ) async {
    final controller = SessionController(_FakeAuthApi(languageTag: 'ar'));
    await tester.pumpWidget(
      WathiqApp(catalogue: _catalogue, sessionController: controller),
    );

    expect(find.text('Sign in'), findsNWidgets(2));
    await tester.enterText(
      find.byKey(const ValueKey('sign-in-email')),
      'user@example.test',
    );
    await tester.enterText(
      find.byKey(const ValueKey('sign-in-password')),
      'secret',
    );
    await tester.tap(find.byKey(const ValueKey('sign-in-submit')));
    await tester.pumpAndSettle();

    expect(find.text('لوحة المعلومات'), findsWidgets);
    expect(
      Directionality.of(tester.element(find.text('لوحة المعلومات').first)),
      TextDirection.rtl,
    );
  });

  testWidgets('successful sign-in opens authenticated foundation', (
    tester,
  ) async {
    final api = _FakeAuthApi();
    final controller = SessionController(api);
    await tester.pumpWidget(
      WathiqApp(catalogue: _catalogue, sessionController: controller),
    );

    await tester.enterText(
      find.byKey(const ValueKey('sign-in-email')),
      ' user@example.test ',
    );
    await tester.enterText(
      find.byKey(const ValueKey('sign-in-password')),
      'secret',
    );
    await tester.tap(find.byKey(const ValueKey('sign-in-submit')));
    await tester.pumpAndSettle();

    expect(api.lastEmail, 'user@example.test');
    expect(find.text('Dashboard'), findsWidgets);
    expect(find.byIcon(Icons.logout), findsOneWidget);
  });

  testWidgets('required password change replaces sign-in safely', (
    tester,
  ) async {
    final controller = SessionController(
      _FakeAuthApi(principal: _principal(mustChangePassword: true)),
    );
    await tester.pumpWidget(
      WathiqApp(catalogue: _catalogue, sessionController: controller),
    );

    await controller.signIn(email: 'user@example.test', password: 'temporary');
    await tester.pumpAndSettle();

    expect(find.text('Set a new password'), findsOneWidget);
    expect(find.byKey(const ValueKey('current-password')), findsOneWidget);
    expect(find.byKey(const ValueKey('new-password')), findsOneWidget);
    expect(find.byKey(const ValueKey('confirm-password')), findsOneWidget);
    expect(find.text('Dashboard'), findsNothing);
  });

  testWidgets('phone shell exposes authenticated navigation in a drawer', (
    tester,
  ) async {
    tester.view.physicalSize = const Size(390, 844);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final controller = SessionController(_FakeAuthApi());
    await controller.signIn(email: 'user@example.test', password: 'secret');

    await tester.pumpWidget(
      WathiqApp(catalogue: _catalogue, sessionController: controller),
    );
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('shell-dashboard')), findsNothing);

    await tester.tap(find.byTooltip('Open navigation menu'));
    await tester.pumpAndSettle();

    expect(find.byKey(const ValueKey('shell-dashboard')), findsOneWidget);
    expect(find.byKey(const ValueKey('shell-sign-out')), findsOneWidget);
    expect(find.text('user@example.test'), findsOneWidget);
  });

  testWidgets('tablet shell keeps navigation persistently visible', (
    tester,
  ) async {
    tester.view.physicalSize = const Size(1024, 768);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final controller = SessionController(_FakeAuthApi());
    await controller.signIn(email: 'user@example.test', password: 'secret');

    await tester.pumpWidget(
      WathiqApp(catalogue: _catalogue, sessionController: controller),
    );
    await tester.pumpAndSettle();

    expect(find.byKey(const ValueKey('shell-dashboard')), findsOneWidget);
    expect(find.byKey(const ValueKey('shell-sign-out')), findsOneWidget);
    expect(find.byTooltip('Open navigation menu'), findsNothing);
  });

  testWidgets('preferences save changes language without logout', (
    tester,
  ) async {
    tester.view.physicalSize = const Size(1024, 768);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final controller = SessionController(_FakeAuthApi());
    await controller.signIn(email: 'user@example.test', password: 'secret');
    await tester.pumpWidget(
      WathiqApp(catalogue: _catalogue, sessionController: controller),
    );

    await tester.tap(find.byKey(const ValueKey('shell-preferences')));
    await tester.pumpAndSettle();
    expect(find.text('Asia/Dubai'), findsOneWidget);
    final englishBefore = tester.getCenter(find.text('English')).dx;
    final arabicBefore = tester.getCenter(find.text('العربية')).dx;
    expect(englishBefore, lessThan(arabicBefore));

    await tester.tap(find.text('العربية'));
    await tester.pumpAndSettle();

    expect(controller.effectiveLanguageTag, 'ar');
    expect(find.text('التفضيلات'), findsWidgets);
    expect(controller.status, SessionStatus.authenticated);
    expect(tester.getCenter(find.text('English')).dx, englishBefore);
    expect(tester.getCenter(find.text('العربية')).dx, arabicBefore);
  });
  for (final language in ['en', 'ar']) {
    for (final size in [const Size(390, 844), const Size(1024, 768)]) {
      testWidgets('foreground revocation clears pushed route $language $size', (
        tester,
      ) async {
        addTearDown(() => tester.pumpWidget(const SizedBox.shrink()));
        tester.view.physicalSize = size;
        tester.view.devicePixelRatio = 1;
        addTearDown(tester.view.resetPhysicalSize);
        addTearDown(tester.view.resetDevicePixelRatio);
        final api = _FakeAuthApi(languageTag: language);
        final controller = SessionController(api);
        await controller.signIn(email: 'user@example.test', password: 'secret');
        await tester.pumpWidget(
          WathiqApp(catalogue: _catalogue, sessionController: controller),
        );
        await tester.tap(find.byKey(const ValueKey('shell-search-action')));
        await tester.pumpAndSettle();
        expect(
          find.byKey(const ValueKey('destination-global-search')),
          findsOneWidget,
        );
        api.principalFailure = const ApiFailure(ApiFailureKind.unauthenticated);
        await tester.pump(const Duration(seconds: 15));
        await tester.pumpAndSettle();
        expect(find.byKey(const ValueKey('authenticated-shell')), findsNothing);
        expect(
          find.byKey(const ValueKey('destination-global-search')),
          findsNothing,
        );
        expect(find.byKey(const ValueKey('sign-in-notice')), findsOneWidget);
        expect(api.statusReads, 1);
        await tester.state<NavigatorState>(find.byType(Navigator)).maybePop();
        await tester.pumpAndSettle();
        expect(
          find.byKey(const ValueKey('destination-global-search')),
          findsNothing,
        );
      });

      testWidgets(
        'navigation detects revocation before periodic check $language $size',
        (tester) async {
          addTearDown(() => tester.pumpWidget(const SizedBox.shrink()));
          tester.view.physicalSize = size;
          tester.view.devicePixelRatio = 1;
          addTearDown(tester.view.resetPhysicalSize);
          addTearDown(tester.view.resetDevicePixelRatio);
          final api = _FakeAuthApi(languageTag: language);
          final controller = SessionController(api);
          await controller.signIn(
            email: 'user@example.test',
            password: 'secret',
          );
          await tester.pumpWidget(
            WathiqApp(catalogue: _catalogue, sessionController: controller),
          );
          api.principalFailure = const ApiFailure(
            ApiFailureKind.unauthenticated,
          );
          await tester.tap(find.byKey(const ValueKey('shell-search-action')));
          await tester.pumpAndSettle();
          expect(
            find.byKey(const ValueKey('destination-global-search')),
            findsNothing,
          );
          expect(find.byKey(const ValueKey('sign-in-notice')), findsOneWidget);
          expect(api.statusReads, 0);
        },
      );
    }
  }

  testWidgets('navigation uses refreshed destination availability', (
    tester,
  ) async {
    addTearDown(() => tester.pumpWidget(const SizedBox.shrink()));
    final api = _FakeAuthApi();
    final controller = SessionController(api);
    await controller.signIn(email: 'user@example.test', password: 'secret');
    await tester.pumpWidget(
      WathiqApp(catalogue: _catalogue, sessionController: controller),
    );
    api.searchEnabled = false;
    await tester.tap(find.byKey(const ValueKey('shell-search-action')));
    await tester.pumpAndSettle();
    expect(
      find.byKey(const ValueKey('destination-global-search')),
      findsNothing,
    );
    expect(find.byKey(const ValueKey('shell-search-action')), findsNothing);
    expect(controller.status, SessionStatus.authenticated);
  });

  testWidgets('foreground checks stop in background and after disposal', (
    tester,
  ) async {
    addTearDown(() => tester.pumpWidget(const SizedBox.shrink()));
    final api = _FakeAuthApi();
    final controller = SessionController(api);
    await controller.signIn(email: 'user@example.test', password: 'secret');
    await tester.pumpWidget(
      WathiqApp(catalogue: _catalogue, sessionController: controller),
    );
    await tester.pump(const Duration(seconds: 15));
    await tester.pumpAndSettle();
    expect(api.statusReads, 1);
    tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.hidden);
    await tester.pump(const Duration(seconds: 45));
    expect(api.statusReads, 1);
    await tester.pumpWidget(const SizedBox.shrink());
    await tester.pump(const Duration(seconds: 45));
    expect(api.statusReads, 1);
  });

  testWidgets(
    'revocation removes pushed preferences and prevents back into identity',
    (tester) async {
      addTearDown(() => tester.pumpWidget(const SizedBox.shrink()));
      tester.view.physicalSize = const Size(390, 844);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      final controller = SessionController(_FakeAuthApi());
      await controller.signIn(email: 'user@example.test', password: 'secret');
      await tester.pumpWidget(
        WathiqApp(catalogue: _catalogue, sessionController: controller),
      );
      await tester.tap(find.byTooltip('Open navigation menu'));
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const ValueKey('shell-preferences')));
      await tester.pumpAndSettle();
      expect(find.text('Working timezone'), findsOneWidget);
      controller.clearForRevocation();
      await tester.pumpAndSettle();
      expect(find.text('Working timezone'), findsNothing);
      expect(find.byKey(const ValueKey('authenticated-shell')), findsNothing);
      expect(find.byKey(const ValueKey('sign-in-notice')), findsOneWidget);
      await tester.state<NavigatorState>(find.byType(Navigator)).maybePop();
      await tester.pumpAndSettle();
      expect(find.byKey(const ValueKey('authenticated-shell')), findsNothing);
    },
  );

  for (final language in ['en', 'ar']) {
    for (final expired in [false, true]) {
      testWidgets(
        'server decides session after long background $language expired=$expired',
        (tester) async {
          addTearDown(() => tester.pumpWidget(const SizedBox.shrink()));
          final api = _FakeAuthApi(languageTag: language);
          final controller = SessionController(api);
          await controller.signIn(
            email: 'user@example.test',
            password: 'secret',
          );
          await tester.pumpWidget(
            WathiqApp(catalogue: _catalogue, sessionController: controller),
          );
          tester.binding.handleAppLifecycleStateChanged(
            AppLifecycleState.hidden,
          );
          await tester.pump();
          await tester.pump(const Duration(days: 1));
          if (expired) {
            api.principalFailure = const ApiFailure(
              ApiFailureKind.unauthenticated,
            );
          }
          tester.binding.handleAppLifecycleStateChanged(
            AppLifecycleState.resumed,
          );
          await tester.pumpAndSettle();
          expect(
            find.byKey(const ValueKey('authenticated-shell')),
            expired ? findsNothing : findsOneWidget,
          );
          expect(
            find.byKey(const ValueKey('sign-in-notice')),
            expired ? findsOneWidget : findsNothing,
          );
          expect(controller.effectiveLanguageTag, expired ? 'en' : language);
        },
      );
    }
  }
}

const _catalogue = MessageCatalogue(
  english: {
    'mobile.navigation.global_search': 'Global Search',
    'mobile.navigation.classification_browser': 'Classification Browser',
    'mobile.navigation.favourites': 'Favourites',
    'mobile.navigation.recent_activity': 'Recent Activity',

    'common.error.bad_request': 'Request failed',
    'common.error.forbidden': 'Forbidden',
    'common.error.service_unavailable': 'Service unavailable',
    'common.error.validation_failed': 'Review the information',
    'navigation.item.dashboard': 'Dashboard',
    'preferences.action.open': 'Preferences',
    'mobile.navigation.user_profile': 'User/Profile',
    'mobile.state.offline': 'Unable to connect.',
    'mobile.state.validating_session': 'Checking your session…',
    'common.error.authentication_required': 'Sign in to continue.',
    'classification_browser.retry': 'Retry',
    'preferences.field.language': 'Language',
    'preferences.field.working_timezone': 'Working timezone',
    'preferences.guidance.personal':
        'Choose the language and working timezone used by Wathiq.',
    'preferences.guidance.working_timezone':
        'Dates and times are displayed in this timezone.',
    'preferences.heading.personal': 'Preferences',
    'webui.index.button.sign_out_a4610dd4': 'Sign out',
    'webui.index.input.email_address_2569f0e9': 'Email address',
    'webui.index.input.password_f76ddde6': 'Password',
    'webui.index.label.sign_in_01f3842a': 'Sign in',
    'webui.index.label.wathiq_d1dfb800': 'Wathiq',
    'webui.show_change_password.button.set_new_password_067753d1':
        'Set new password',
    'webui.show_change_password.input.confirm_new_password_abd1d774':
        'Confirm new password',
    'webui.show_change_password.input.current_password_00f4f73a':
        'Current password',
    'webui.show_change_password.input.new_password_28399c5b': 'New password',
    'webui.show_change_password.label.set_a_new_password_f6a268ba':
        'Set a new password',
    'webui.show_change_password.label.your_temporary_password_must_be_replaced_b_2cba2da1':
        'Replace your temporary password.',
  },
  arabic: {
    'mobile.navigation.global_search': 'البحث الشامل',
    'mobile.navigation.classification_browser': 'متصفح التصنيفات',
    'mobile.navigation.favourites': 'المفضلة',
    'mobile.navigation.recent_activity': 'النشاط الأخير',

    'common.error.bad_request': 'تعذر إكمال الطلب',
    'common.error.forbidden': 'غير مسموح',
    'common.error.service_unavailable': 'الخدمة غير متاحة',
    'common.error.validation_failed': 'راجع المعلومات',
    'navigation.item.dashboard': 'لوحة المعلومات',
    'preferences.action.open': 'التفضيلات',
    'mobile.navigation.user_profile': 'المستخدم/الملف الشخصي',
    'mobile.state.offline': 'تعذّر الاتصال.',
    'mobile.state.validating_session': 'جارٍ التحقّق من جلستك…',
    'common.error.authentication_required': 'سجّل الدخول للمتابعة.',
    'classification_browser.retry': 'إعادة المحاولة',
    'preferences.field.language': 'اللغة',
    'preferences.field.working_timezone': 'المنطقة الزمنية للعمل',
    'preferences.guidance.personal': 'اختر اللغة والمنطقة الزمنية للعمل.',
    'preferences.guidance.working_timezone':
        'تُعرض التواريخ والأوقات وفق هذه المنطقة الزمنية.',
    'preferences.heading.personal': 'التفضيلات',
    'webui.index.button.sign_out_a4610dd4': 'تسجيل الخروج',
    'webui.index.input.email_address_2569f0e9': 'البريد الإلكتروني',
    'webui.index.input.password_f76ddde6': 'كلمة المرور',
    'webui.index.label.sign_in_01f3842a': 'تسجيل الدخول',
    'webui.index.label.wathiq_d1dfb800': 'وثق',
    'webui.show_change_password.button.set_new_password_067753d1':
        'تعيين كلمة مرور جديدة',
    'webui.show_change_password.input.confirm_new_password_abd1d774':
        'تأكيد كلمة المرور الجديدة',
    'webui.show_change_password.input.current_password_00f4f73a':
        'كلمة المرور الحالية',
    'webui.show_change_password.input.new_password_28399c5b':
        'كلمة المرور الجديدة',
    'webui.show_change_password.label.set_a_new_password_f6a268ba':
        'تعيين كلمة مرور جديدة',
    'webui.show_change_password.label.your_temporary_password_must_be_replaced_b_2cba2da1':
        'يجب استبدال كلمة المرور المؤقتة.',
  },
);

class _FakeAuthApi implements AuthApi {
  _FakeAuthApi({
    AuthPrincipal? principal,
    this.languageTag = 'en',
    this.searchEnabled = true,
  }) : principal = principal ?? _principal();

  final AuthPrincipal principal;
  final String languageTag;
  bool searchEnabled;
  String? lastEmail;
  ApiFailure? principalFailure;
  int statusReads = 0;

  @override
  Future<AuthSession> signIn({
    required String email,
    required String password,
  }) async {
    lastEmail = email;
    return AuthSession(principal: principal, token: 'memory-token');
  }

  @override
  Future<List<String>> mobileCapabilities(String token) async => [
    if (searchEnabled) 'global-search',
    'dashboard',
    'classification-browser',
    'favourites',
    'recent-activity',
    'user-profile',
    'sign-out',
  ];

  @override
  Future<AuthPrincipal> sessionStatus(String token) async {
    statusReads++;
    return currentPrincipal(token);
  }

  @override
  Future<AuthPrincipal> currentPrincipal(String token) async {
    if (principalFailure case final failure?) throw failure;
    return principal;
  }

  @override
  Future<String> effectiveLanguage(String token) async => languageTag;

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
    languageTag: languageTag,
    workingTimezone: 'Asia/Dubai',
    version: 1,
  );

  @override
  Future<UserPreferences> updatePreferences({
    required String token,
    required String languageTag,
    required String workingTimezone,
    required int version,
  }) async => UserPreferences(
    languageTag: languageTag,
    workingTimezone: workingTimezone,
    version: version + 1,
  );

  @override
  Future<void> changePassword({
    required String token,
    required String currentPassword,
    required String newPassword,
  }) async {}

  @override
  Future<void> signOut(String token) async {}
}

AuthPrincipal _principal({bool mustChangePassword = false}) => AuthPrincipal(
  user: const AuthUser(
    id: 7,
    name: 'Records User',
    email: 'user@example.test',
    accountType: 'person',
  ),
  sessionId: 19,
  mustChangePassword: mustChangePassword,
  globalPrivileges: const {'records.view'},
  roles: const [AuthRole(id: 2, code: 'records-user', name: 'Records User')],
);
