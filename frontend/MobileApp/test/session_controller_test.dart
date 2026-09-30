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

  test('resume before fifteen minutes retains the session', () async {
    var now = DateTime.utc(2026, 9, 30, 10);
    final scheduler = _FakeWarningScheduler();
    final controller = SessionController(
      _FakeAuthApi(),
      warningScheduler: scheduler,
      clock: () => now,
    );
    await controller.signIn(email: 'user@example.test', password: 'password');
    await controller.onBackgrounded();
    now = now.add(const Duration(minutes: 14, seconds: 59));

    expect(await controller.onResumed(), isFalse);
    expect(controller.status, SessionStatus.authenticated);
    expect(scheduler.scheduledDelay, SessionController.warningAfter);
    expect(scheduler.cancelled, isTrue);
  });

  test('resume at fifteen minutes clears all protected state', () async {
    var now = DateTime.utc(2026, 9, 30, 10);
    final controller = SessionController(_FakeAuthApi(), clock: () => now);
    await controller.signIn(email: 'user@example.test', password: 'password');
    await controller.onBackgrounded();
    now = now.add(SessionController.expireAfter);

    expect(await controller.onResumed(), isTrue);
    expect(controller.status, SessionStatus.signedOut);
    expect(controller.hasProtectedState, isFalse);
  });

  test('warning delivery failure never extends the session', () async {
    var now = DateTime.utc(2026, 9, 30, 10);
    final controller = SessionController(
      _FakeAuthApi(),
      warningScheduler: _FakeWarningScheduler(throwOnSchedule: true),
      clock: () => now,
    );
    await controller.signIn(email: 'user@example.test', password: 'password');
    await controller.onBackgrounded();
    now = now.add(const Duration(minutes: 16));

    expect(await controller.onResumed(), isTrue);
    expect(controller.status, SessionStatus.signedOut);
  });
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
  Future<AuthPrincipal> currentPrincipal(String token) async => principal;

  @override
  Future<String> effectiveLanguage(String token) async => 'en';

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

class _FakeWarningScheduler implements SessionWarningScheduler {
  _FakeWarningScheduler({this.throwOnSchedule = false});

  final bool throwOnSchedule;
  Duration? scheduledDelay;
  bool cancelled = false;

  @override
  Future<void> schedule(Duration delay) async {
    if (throwOnSchedule) {
      throw StateError('notification unavailable');
    }
    scheduledDelay = delay;
  }

  @override
  Future<void> cancel() async {
    cancelled = true;
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
