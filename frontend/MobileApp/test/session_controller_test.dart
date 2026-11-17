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

  for (final language in ['en', 'ar']) {
    test(
      'password change loads saved $language only after server clearance',
      () async {
        final api = _FakeAuthApi(
          principal: _principal(mustChangePassword: true),
        )..languageTag = language;
        final controller = SessionController(api);
        await controller.signIn(
          email: 'user@example.test',
          password: 'temporary',
        );
        expect(controller.hasProtectedState, isTrue);
        expect(controller.effectiveLanguageTag, 'en');
        expect(controller.destinations, isEmpty);
        expect(api.languageReads, 0);
        expect(api.capabilityReads, 0);
        await controller.onBackgrounded();
        await controller.onResumed();
        expect(controller.status, SessionStatus.passwordChangeRequired);
        expect(api.languageReads, 0);
        await controller.changePassword(
          currentPassword: 'temporary',
          newPassword: 'replacement',
        );
        expect(controller.status, SessionStatus.authenticated);
        expect(controller.effectiveLanguageTag, language);
        expect(controller.principal!.mustChangePassword, isFalse);
        expect(controller.destinations, contains('dashboard'));
        expect(api.languageReads, 1);
        expect(api.capabilityReads, 1);
      },
    );
  }

  for (final kind in [
    ApiFailureKind.invalidRequest,
    ApiFailureKind.unauthenticated,
  ]) {
    test('password-change rejection $kind does not open the shell', () async {
      final api = _FakeAuthApi(principal: _principal(mustChangePassword: true))
        ..passwordChangeFailure = ApiFailure(kind);
      final controller = SessionController(api);
      await controller.signIn(
        email: 'user@example.test',
        password: 'temporary',
      );
      await controller.changePassword(
        currentPassword: 'wrong',
        newPassword: 'replacement',
      );
      expect(
        controller.status,
        kind == ApiFailureKind.unauthenticated
            ? SessionStatus.signedOut
            : SessionStatus.passwordChangeRequired,
      );
      expect(
        controller.hasProtectedState,
        kind != ApiFailureKind.unauthenticated,
      );
      expect(controller.destinations, isEmpty);
      expect(api.languageReads, 0);
    });
  }

  for (final lostMutationResponse in [false, true]) {
    test(
      'offline password completion recovers without replay; lost response=$lostMutationResponse',
      () async {
        final api = _FakeAuthApi(
          principal: _principal(mustChangePassword: true),
        )..languageTag = 'ar';
        final controller = SessionController(api);
        await controller.signIn(
          email: 'user@example.test',
          password: 'temporary',
        );
        if (lostMutationResponse) {
          api.passwordChangeFailure = const ApiFailure(ApiFailureKind.offline);
        } else {
          api.languageFailure = const ApiFailure(ApiFailureKind.offline);
        }
        await controller.changePassword(
          currentPassword: 'temporary',
          newPassword: 'replacement',
        );
        expect(controller.status, SessionStatus.validatingSession);
        expect(controller.hasProtectedState, isTrue);
        expect(controller.destinations, isEmpty);
        // The server may have committed even if the mutation response was lost.
        api.principal = _principal();
        api.passwordChangeFailure = null;
        api.languageFailure = null;
        await controller.validateSession();
        expect(controller.status, SessionStatus.authenticated);
        expect(controller.effectiveLanguageTag, 'ar');
        expect(api.passwordChanges, 1);
      },
    );
  }

  test(
    'offline before password commit returns to the required form on safe retry',
    () async {
      final api = _FakeAuthApi(principal: _principal(mustChangePassword: true))
        ..passwordChangeFailure = const ApiFailure(ApiFailureKind.offline);
      final controller = SessionController(api);
      await controller.signIn(
        email: 'user@example.test',
        password: 'temporary',
      );
      await controller.changePassword(
        currentPassword: 'temporary',
        newPassword: 'replacement',
      );
      await controller.validateSession();
      expect(controller.status, SessionStatus.passwordChangeRequired);
      expect(controller.hasProtectedState, isTrue);
      expect(api.passwordChanges, 1);
      expect(api.languageReads, 0);
      expect(controller.destinations, isEmpty);
    },
  );

  test('revoked post-password setup clears protected state', () async {
    final api = _FakeAuthApi(principal: _principal(mustChangePassword: true))
      ..capabilityFailure = const ApiFailure(ApiFailureKind.unauthenticated);
    final controller = SessionController(api);
    await controller.signIn(email: 'user@example.test', password: 'temporary');
    await controller.changePassword(
      currentPassword: 'temporary',
      newPassword: 'replacement',
    );
    expect(controller.status, SessionStatus.signedOut);
    expect(controller.hasProtectedState, isFalse);
    expect(controller.destinations, isEmpty);
  });

  test(
    'post-password capability failure retries setup rather than the mutation',
    () async {
      final api = _FakeAuthApi(principal: _principal(mustChangePassword: true))
        ..languageTag = 'ar'
        ..capabilityFailure = const ApiFailure(ApiFailureKind.server);
      final controller = SessionController(api);
      await controller.signIn(
        email: 'user@example.test',
        password: 'temporary',
      );
      await controller.changePassword(
        currentPassword: 'temporary',
        newPassword: 'replacement',
      );
      expect(controller.status, SessionStatus.validatingSession);
      expect(controller.destinations, isEmpty);
      expect(controller.effectiveLanguageTag, 'en');
      api.capabilityFailure = null;
      await controller.validateSession();
      expect(controller.status, SessionStatus.authenticated);
      expect(controller.effectiveLanguageTag, 'ar');
      expect(api.passwordChanges, 1);
    },
  );

  test(
    'late post-password bootstrap cannot restore a revoked session',
    () async {
      final api = _FakeAuthApi(principal: _principal(mustChangePassword: true));
      final controller = SessionController(api);
      await controller.signIn(
        email: 'user@example.test',
        password: 'temporary',
      );
      api.languageCompletion = Completer<String>();
      final pending = controller.changePassword(
        currentPassword: 'temporary',
        newPassword: 'replacement',
      );
      await Future<void>.delayed(Duration.zero);
      controller.clearForRevocation();
      api.languageCompletion!.complete('ar');
      await pending;
      expect(controller.status, SessionStatus.signedOut);
      expect(controller.effectiveLanguageTag, 'en');
      expect(controller.destinations, isEmpty);
      expect(api.capabilityReads, 0);
    },
  );

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

  test(
    'navigation network failure gates interaction without clearing identity',
    () async {
      final api = _FakeAuthApi()
        ..principalFailure = const ApiFailure(ApiFailureKind.offline);
      final controller = SessionController(api);
      await controller.signIn(email: 'user@example.test', password: 'secret');
      expect(await controller.authorizeNavigation(), isFalse);
      expect(controller.status, SessionStatus.validatingSession);
      expect(controller.hasProtectedState, isTrue);
      expect(controller.failure?.kind, ApiFailureKind.offline);
    },
  );

  test('late navigation validation cannot reopen signed-out state', () async {
    final api = _FakeAuthApi()
      ..principalCompletion = Completer<AuthPrincipal>();
    final controller = SessionController(api);
    await controller.signIn(email: 'user@example.test', password: 'secret');
    final navigation = controller.authorizeNavigation();
    await controller.signOut();
    api.principalCompletion!.complete(_principal());
    expect(await navigation, isFalse);
    expect(controller.hasProtectedState, isFalse);
  });

  for (final mutation in [false, true]) {
    test(
      'authenticated ${mutation ? 'mutation' : 'read'} rejection clears protected state',
      () async {
        final api = _FakeAuthApi();
        final controller = SessionController(api);
        await controller.signIn(email: 'user@example.test', password: 'secret');
        if (mutation) await controller.loadPreferences();
        api.preferenceFailure = const ApiFailure(
          ApiFailureKind.unauthenticated,
        );
        if (mutation) {
          expect(await controller.updateLanguage('ar'), isFalse);
        } else {
          await controller.loadPreferences();
        }
        expect(controller.status, SessionStatus.signedOut);
        expect(controller.hasProtectedState, isFalse);
        expect(controller.preferences, isNull);
        expect(controller.destinations, isEmpty);
      },
    );
  }

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
      expect(controller.hasEffectiveLanguagePreference, isFalse);
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

  AuthPrincipal principal;
  final ApiFailure? signInFailure;
  final ApiFailure? signOutFailure;
  final Completer<AuthSession>? signInCompletion;
  String? lastEmail;
  ApiFailure? principalFailure;
  ApiFailure? preferenceFailure;
  int principalReads = 0;
  int languageReads = 0;
  int capabilityReads = 0;
  int passwordChanges = 0;
  String languageTag = 'en';
  ApiFailure? passwordChangeFailure;
  ApiFailure? languageFailure;
  ApiFailure? capabilityFailure;
  Completer<AuthPrincipal>? principalCompletion;
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
  Future<List<String>> mobileCapabilities(String token) async {
    capabilityReads++;
    if (principal.mustChangePassword) {
      throw const ApiFailure(ApiFailureKind.forbidden);
    }
    if (capabilityFailure case final error?) throw error;
    return const [
      'global-search',
      'dashboard',
      'classification-browser',
      'favourites',
      'recent-activity',
      'user-profile',
      'sign-out',
    ];
  }

  @override
  Future<AuthPrincipal> currentPrincipal(String token) async {
    principalReads++;
    if (principalCompletion != null) return principalCompletion!.future;
    if (principalFailure case final error?) throw error;
    return principal;
  }

  @override
  Future<String> effectiveLanguage(String token) async {
    languageReads++;
    if (principal.mustChangePassword) {
      throw const ApiFailure(ApiFailureKind.forbidden);
    }
    if (languageFailure case final error?) throw error;
    return languageCompletion != null
        ? await languageCompletion!.future
        : languageTag;
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
  Future<UserPreferences> preferences(String token) async {
    if (preferenceFailure case final failure?) throw failure;
    return preferenceCompletion != null
        ? await preferenceCompletion!.future
        : const UserPreferences(
            languageTag: 'en',
            workingTimezone: 'Asia/Dubai',
            version: 1,
          );
  }

  @override
  Future<UserPreferences> updatePreferences({
    required String token,
    required String languageTag,
    required String workingTimezone,
    required int version,
  }) async {
    if (preferenceFailure case final failure?) throw failure;
    return UserPreferences(
      languageTag: languageTag,
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
    passwordChanges++;
    if (passwordChangeFailure case final error?) throw error;
    principal = _principal();
  }

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
