import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:wathiq_mobile/core/network/api_failure.dart';
import 'package:wathiq_mobile/features/auth/application/session_controller.dart';
import 'package:wathiq_mobile/features/auth/data/auth_api.dart';
import 'package:wathiq_mobile/features/auth/domain/auth_principal.dart';

void main() {
  test('sign-in keeps session material only in controller memory', () async {
    final api = _FakeAuthApi();
    final controller = SessionController(api);

    await controller.signIn(
      email: 'user@example.test',
      password: 'not-recorded',
    );

    expect(controller.status, SessionStatus.authenticated);
    expect(controller.principal?.user.id, 7);
    expect(controller.hasProtectedState, isTrue);
    expect(controller.effectiveLanguageTag, 'en');
    expect(api.lastEmail, 'user@example.test');
  });

  test('required password change prevents authenticated shell state', () async {
    final api = _FakeAuthApi(principal: _principal(mustChangePassword: true));
    final controller = SessionController(api);

    await controller.signIn(email: 'user@example.test', password: 'temporary');

    expect(controller.status, SessionStatus.passwordChangeRequired);
  });

  test('failed sign-in exposes category without retaining identity', () async {
    final api = _FakeAuthApi(
      signInFailure: const ApiFailure(ApiFailureKind.unauthenticated),
    );
    final controller = SessionController(api);

    await controller.signIn(email: 'unknown@example.test', password: 'wrong');

    expect(controller.status, SessionStatus.signedOut);
    expect(controller.hasProtectedState, isFalse);
    expect(controller.failure?.kind, ApiFailureKind.unauthenticated);
  });

  test(
    'sign-out clears protected state even when API sign-out fails',
    () async {
      final api = _FakeAuthApi(
        signOutFailure: const ApiFailure(ApiFailureKind.offline),
      );
      final controller = SessionController(api);
      await controller.signIn(email: 'user@example.test', password: 'password');

      await controller.signOut();

      expect(controller.status, SessionStatus.signedOut);
      expect(controller.hasProtectedState, isFalse);
      expect(controller.effectiveLanguageTag, 'en');
    },
  );

  test('response from a prior sign-in generation is ignored', () async {
    final completion = Completer<AuthSession>();
    final api = _FakeAuthApi(signInCompletion: completion);
    final controller = SessionController(api);

    final pending = controller.signIn(
      email: 'first@example.test',
      password: 'password',
    );
    controller.clearForRevocation();
    completion.complete(AuthSession(principal: _principal(), token: 'stale'));
    await pending;

    expect(controller.status, SessionStatus.signedOut);
    expect(controller.hasProtectedState, isFalse);
  });

  test('resume retains a session accepted by the server', () async {
    final api = _FakeAuthApi();
    final controller = SessionController(api);
    await controller.signIn(email: 'user@example.test', password: 'password');
    await controller.onBackgrounded();
    expect(await controller.onResumed(), isFalse);
    expect(api.principalReads, 1);
    expect(controller.status, SessionStatus.authenticated);
  });

  test('repeated background callbacks require one server validation', () async {
    final api = _FakeAuthApi();
    final controller = SessionController(api);
    await controller.signIn(email: 'user@example.test', password: 'password');
    await controller.onBackgrounded();
    await controller.onBackgrounded();
    await controller.onResumed();
    await controller.onResumed();
    expect(api.principalReads, 1);
    expect(controller.hasProtectedState, isTrue);
  });

  test(
    'server expiry or revocation clears protected state on resume',
    () async {
      final api = _FakeAuthApi();
      final controller = SessionController(api);
      await controller.signIn(email: 'user@example.test', password: 'password');
      await controller.onBackgrounded();
      api.principalFailure = const ApiFailure(ApiFailureKind.unauthenticated);
      expect(await controller.onResumed(), isTrue);
      expect(controller.status, SessionStatus.signedOut);
    },
  );

  test(
    'offline revalidation gates protected routes until explicit retry',
    () async {
      final api = _FakeAuthApi();
      final controller = SessionController(api);
      await controller.signIn(email: 'user@example.test', password: 'password');
      await controller.onBackgrounded();
      api.principalFailure = const ApiFailure(ApiFailureKind.offline);
      await controller.onResumed();
      expect(controller.status, SessionStatus.validatingSession);
      expect(controller.failure?.kind, ApiFailureKind.offline);
      api.principalFailure = null;
      await controller.validateSession();
      expect(controller.status, SessionStatus.authenticated);
    },
  );

  test(
    'delayed preference response cannot repopulate a revoked session',
    () async {
      final api = _FakeAuthApi();
      final controller = SessionController(api);
      await controller.signIn(email: 'user@example.test', password: 'password');
      api.preferenceCompletion = Completer<UserPreferences>();
      final pending = controller.loadPreferences();
      controller.clearForRevocation();
      api.preferenceCompletion!.complete(
        const UserPreferences(
          languageTag: 'ar',
          workingTimezone: 'Asia/Dubai',
          version: 1,
        ),
      );
      await pending;
      expect(controller.preferences, isNull);
      expect(controller.supportedLanguages, isEmpty);
      expect(controller.effectiveLanguageTag, 'en');
    },
  );
  test(
    'delayed localization bootstrap cannot restore a revoked language',
    () async {
      final api = _FakeAuthApi()..languageCompletion = Completer<String>();
      final controller = SessionController(api);
      final signingIn = controller.signIn(
        email: 'user@example.test',
        password: 'password',
      );
      await Future<void>.delayed(Duration.zero);
      controller.clearForRevocation();
      api.languageCompletion!.complete('ar');
      await signingIn;
      expect(controller.hasProtectedState, isFalse);
      expect(controller.effectiveLanguageTag, 'en');
      expect(controller.destinations, isEmpty);
    },
  );
}

class _FakeAuthApi implements AuthApi {
  _FakeAuthApi({
    AuthPrincipal? principal,
    this.signInFailure,
    this.signOutFailure,
    this.signInCompletion,
  }) : principal = principal ?? _principal();

  final AuthPrincipal principal;
  final ApiFailure? signInFailure;
  final ApiFailure? signOutFailure;
  final Completer<AuthSession>? signInCompletion;
  String? lastEmail;
  ApiFailure? principalFailure;
  int principalReads = 0;
  Completer<String>? languageCompletion;
  Completer<UserPreferences>? preferenceCompletion;

  @override
  Future<AuthSession> signIn({
    required String email,
    required String password,
  }) async {
    lastEmail = email;
    if (signInCompletion case final completion?) {
      return completion.future;
    }
    if (signInFailure case final failure?) {
      throw failure;
    }
    return AuthSession(principal: principal, token: 'session-token');
  }

  @override
  Future<List<String>> mobileCapabilities(String token) async => const [
    'global-search',
    'dashboard',
    'classification-browser',
    'favourites',
    'recent-activity',
    'user-profile',
    'sign-out',
  ];

  @override
  Future<AuthPrincipal> currentPrincipal(String token) async {
    principalReads++;
    if (principalFailure case final error?) throw error;
    return principal;
  }

  @override
  Future<String> effectiveLanguage(String token) async =>
      languageCompletion != null ? await languageCompletion!.future : 'en';

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
  Future<UserPreferences> preferences(String token) async =>
      preferenceCompletion != null
      ? await preferenceCompletion!.future
      : const UserPreferences(
          languageTag: 'en',
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
  Future<void> signOut(String token) async {
    if (signOutFailure case final failure?) {
      throw failure;
    }
  }
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
