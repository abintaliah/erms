import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:wathiq_mobile/app/app.dart';
import 'package:wathiq_mobile/core/localization/message_catalogue.dart';
import 'package:wathiq_mobile/features/auth/application/session_controller.dart';
import 'package:wathiq_mobile/features/auth/data/auth_api.dart';
import 'package:wathiq_mobile/features/auth/domain/auth_principal.dart';

void main() {
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

    expect(find.text('لوحة المعلومات'), findsOneWidget);
    expect(
      Directionality.of(tester.element(find.text('لوحة المعلومات'))),
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
    expect(find.text('Dashboard'), findsOneWidget);
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
}

const _catalogue = MessageCatalogue(
  english: {
    'common.error.bad_request': 'Request failed',
    'common.error.forbidden': 'Forbidden',
    'common.error.service_unavailable': 'Service unavailable',
    'common.error.validation_failed': 'Review the information',
    'navigation.item.dashboard': 'Dashboard',
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
    'common.error.bad_request': 'تعذر إكمال الطلب',
    'common.error.forbidden': 'غير مسموح',
    'common.error.service_unavailable': 'الخدمة غير متاحة',
    'common.error.validation_failed': 'راجع المعلومات',
    'navigation.item.dashboard': 'لوحة المعلومات',
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
  _FakeAuthApi({AuthPrincipal? principal, this.languageTag = 'en'})
    : principal = principal ?? _principal();

  final AuthPrincipal principal;
  final String languageTag;
  String? lastEmail;

  @override
  Future<AuthSession> signIn({
    required String email,
    required String password,
  }) async {
    lastEmail = email;
    return AuthSession(principal: principal, token: 'memory-token');
  }

  @override
  Future<AuthPrincipal> currentPrincipal(String token) async => principal;

  @override
  Future<String> effectiveLanguage(String token) async => languageTag;

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
