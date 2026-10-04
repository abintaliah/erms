import 'package:flutter/foundation.dart';

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
  validatingSession,
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

class SessionController extends ChangeNotifier {
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
  String? signInNoticeKey;
  String effectiveLanguageTag = 'en';
  List<String> destinations = const [];
  UserPreferences? preferences;
  List<SupportedLanguage> supportedLanguages = const [];
  bool preferencesBusy = false;
  ApiFailure? preferencesFailure;
  String? _token;
  DateTime? _backgroundedAt;
  int _generation = 0;
  int? _validationGeneration;

  int get sessionGeneration => _generation;

  bool get hasProtectedState => principal != null && _token != null;

  Future<void> loadPreferences() async {
    final token = _token;
    if (token == null || preferencesBusy) return;
    final generation = _generation;
    preferencesBusy = true;
    preferencesFailure = null;
    notifyListeners();
    try {
      final results = await Future.wait<Object>([
        _api.preferences(token),
        _api.supportedLanguages(token),
      ]);
      if (generation != _generation) return;
      preferences = results[0] as UserPreferences;
      supportedLanguages = results[1] as List<SupportedLanguage>;
    } on ApiFailure catch (error) {
      if (generation != _generation) return;
      if (error.kind == ApiFailureKind.unauthenticated) {
        clearForRevocation();
      } else {
        preferencesFailure = error;
        if (error.kind == ApiFailureKind.offline) {
          status = SessionStatus.validatingSession;
          failure = error;
        }
      }
    } finally {
      if (generation == _generation) {
        preferencesBusy = false;
        notifyListeners();
      }
    }
  }

  Future<bool> updateLanguage(String languageTag) async {
    final token = _token;
    final current = preferences;
    if (token == null || current == null || preferencesBusy) return false;
    final generation = _generation;
    preferencesBusy = true;
    preferencesFailure = null;
    notifyListeners();
    try {
      final updated = await _api.updatePreferences(
        token: token,
        languageTag: languageTag,
        workingTimezone: current.workingTimezone,
        version: current.version,
      );
      if (generation != _generation) return false;
      preferences = updated;
      effectiveLanguageTag = updated.languageTag;
      return true;
    } on ApiFailure catch (error) {
      if (generation != _generation) return false;
      if (error.kind == ApiFailureKind.unauthenticated) {
        clearForRevocation();
      } else {
        preferencesFailure = error;
        if (error.kind == ApiFailureKind.offline) {
          status = SessionStatus.validatingSession;
          failure = error;
        }
      }
      return false;
    } finally {
      if (generation == _generation) {
        preferencesBusy = false;
        notifyListeners();
      }
    }
  }

  Future<void> signIn({required String email, required String password}) async {
    final generation = ++_generation;
    status = SessionStatus.signingIn;
    failure = null;
    signInNoticeKey = null;
    notifyListeners();
    try {
      final session = await _api.signIn(email: email, password: password);
      if (generation != _generation) {
        return;
      }
      _token = session.token;
      principal = session.principal;
      final language = await _api.effectiveLanguage(session.token);
      if (generation != _generation) {
        return;
      }
      effectiveLanguageTag = language;
      if (!session.principal.mustChangePassword) {
        final capabilities = await _api.mobileCapabilities(session.token);
        if (generation != _generation) return;
        destinations = capabilities;
      }
      status = session.principal.mustChangePassword
          ? SessionStatus.passwordChangeRequired
          : SessionStatus.authenticated;
      notifyListeners();
    } on ApiFailure catch (error) {
      if (generation != _generation) {
        return;
      }
      _clear();
      failure = error;
      notifyListeners();
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
    notifyListeners();
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
      final capabilities = await _api.mobileCapabilities(token);
      if (generation != _generation) return;
      principal = refreshed;
      destinations = capabilities;
      status = refreshed.mustChangePassword
          ? SessionStatus.passwordChangeRequired
          : SessionStatus.authenticated;
      notifyListeners();
    } on ApiFailure catch (error) {
      if (generation != _generation) {
        return;
      }
      if (error.kind == ApiFailureKind.unauthenticated) {
        clearForRevocation();
        return;
      }
      failure = error;
      status = SessionStatus.passwordChangeRequired;
      notifyListeners();
    }
  }

  Future<void> signOut() async {
    final token = _token;
    final generation = ++_generation;
    status = SessionStatus.signingOut;
    notifyListeners();
    try {
      if (token != null) {
        await _api.signOut(token);
      }
    } on ApiFailure catch (_) {
      // Local protected state is cleared even when server sign-out fails.
    } finally {
      if (generation == _generation) {
        try {
          await _warningScheduler.cancel();
        } catch (_) {
          // Best-effort platform cancellation cannot prevent local sign-out.
        }
        if (generation == _generation) {
          _clear();
          notifyListeners();
        }
      }
    }
  }

  Future<void> onBackgrounded() async {
    if (!hasProtectedState || _backgroundedAt != null) {
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
      await validateSession();
      return !hasProtectedState;
    }
    ++_generation;
    _clear();
    signInNoticeKey = 'common.error.authentication_required';
    notifyListeners();
    return true;
  }

  Future<void> validateSession() async {
    final token = _token;
    if (token == null || _validationGeneration == _generation) return;
    final generation = _generation;
    _validationGeneration = generation;
    status = SessionStatus.validatingSession;
    failure = null;
    notifyListeners();
    try {
      final refreshed = await _api.currentPrincipal(token);
      if (generation != _generation) return;
      // A session may never silently switch identity.
      if (refreshed.user.id != principal?.user.id) {
        clearForRevocation();
        return;
      }
      final capabilities = refreshed.mustChangePassword
          ? const <String>[]
          : await _api.mobileCapabilities(token);
      if (generation != _generation) return;
      principal = refreshed;
      destinations = capabilities;
      status = refreshed.mustChangePassword
          ? SessionStatus.passwordChangeRequired
          : SessionStatus.authenticated;
    } on ApiFailure catch (error) {
      if (generation != _generation) return;
      if (error.kind == ApiFailureKind.unauthenticated) {
        clearForRevocation();
        return;
      }
      failure = error;
    } finally {
      if (_validationGeneration == generation) _validationGeneration = null;
    }
    notifyListeners();
  }

  void clearForRevocation() {
    ++_generation;
    _clear();
    signInNoticeKey = 'common.error.authentication_required';
    notifyListeners();
  }

  void _clear() {
    status = SessionStatus.signedOut;
    failure = null;
    signInNoticeKey = null;
    principal = null;
    destinations = const [];
    _token = null;
    _backgroundedAt = null;
    effectiveLanguageTag = 'en';
    preferences = null;
    supportedLanguages = const [];
    preferencesBusy = false;
    preferencesFailure = null;
  }
}
