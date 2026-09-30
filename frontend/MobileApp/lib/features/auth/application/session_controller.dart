import '../../../core/network/api_failure.dart';
import '../data/auth_api.dart';
import '../domain/auth_principal.dart';

enum SessionStatus {
  signedOut,
  signingIn,
  passwordChangeRequired,
  authenticated,
  changingPassword,
  signingOut,
}

abstract interface class SessionWarningScheduler {
  Future<void> schedule(Duration delay);

  Future<void> cancel();
}

class NoopSessionWarningScheduler implements SessionWarningScheduler {
  const NoopSessionWarningScheduler();

  @override
  Future<void> cancel() async {}

  @override
  Future<void> schedule(Duration delay) async {}
}

class SessionController {
  SessionController(
    this._api, {
    SessionWarningScheduler? warningScheduler,
    DateTime Function()? clock,
  }) : _warningScheduler =
           warningScheduler ?? const NoopSessionWarningScheduler(),
       _clock = clock ?? DateTime.now;

  static const warningAfter = Duration(minutes: 10);
  static const expireAfter = Duration(minutes: 15);

  final AuthApi _api;
  final SessionWarningScheduler _warningScheduler;
  final DateTime Function() _clock;

  SessionStatus status = SessionStatus.signedOut;
  AuthPrincipal? principal;
  ApiFailure? failure;
  String? _token;
  DateTime? _backgroundedAt;
  int _generation = 0;

  bool get hasProtectedState => principal != null && _token != null;

  Future<void> signIn({required String email, required String password}) async {
    final generation = ++_generation;
    status = SessionStatus.signingIn;
    failure = null;
    try {
      final session = await _api.signIn(email: email, password: password);
      if (generation != _generation) {
        return;
      }
      _token = session.token;
      principal = session.principal;
      status = session.principal.mustChangePassword
          ? SessionStatus.passwordChangeRequired
          : SessionStatus.authenticated;
    } on ApiFailure catch (error) {
      if (generation != _generation) {
        return;
      }
      _clear();
      failure = error;
    }
  }

  Future<void> changePassword({
    required String currentPassword,
    required String newPassword,
  }) async {
    final token = _token;
    if (token == null || principal == null) {
      return;
    }
    final generation = _generation;
    status = SessionStatus.changingPassword;
    failure = null;
    try {
      await _api.changePassword(
        token: token,
        currentPassword: currentPassword,
        newPassword: newPassword,
      );
      final refreshed = await _api.currentPrincipal(token);
      if (generation != _generation) {
        return;
      }
      principal = refreshed;
      status = SessionStatus.authenticated;
    } on ApiFailure catch (error) {
      if (generation != _generation) {
        return;
      }
      failure = error;
      status = SessionStatus.passwordChangeRequired;
    }
  }

  Future<void> signOut() async {
    final token = _token;
    ++_generation;
    status = SessionStatus.signingOut;
    try {
      if (token != null) {
        await _api.signOut(token);
      }
    } on ApiFailure catch (_) {
      // Local protected state is cleared even when server sign-out fails.
    } finally {
      await _warningScheduler.cancel();
      _clear();
    }
  }

  Future<void> onBackgrounded() async {
    if (!hasProtectedState) {
      return;
    }
    _backgroundedAt = _clock();
    try {
      await _warningScheduler.schedule(warningAfter);
    } catch (_) {
      // Warning delivery is best effort and never changes expiry behavior.
    }
  }

  Future<bool> onResumed() async {
    try {
      await _warningScheduler.cancel();
    } catch (_) {
      // Warning cancellation failure does not change session behavior.
    }
    final backgroundedAt = _backgroundedAt;
    _backgroundedAt = null;
    if (!hasProtectedState || backgroundedAt == null) {
      return false;
    }
    if (_clock().difference(backgroundedAt) < expireAfter) {
      return false;
    }
    ++_generation;
    _clear();
    return true;
  }

  void clearForRevocation() {
    ++_generation;
    _clear();
  }

  void _clear() {
    status = SessionStatus.signedOut;
    principal = null;
    _token = null;
    _backgroundedAt = null;
  }
}
