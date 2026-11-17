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

class SessionController extends ChangeNotifier {
  SessionController(this._api);

  final AuthApi _api;

  SessionStatus status = SessionStatus.signedOut;
  AuthPrincipal? principal;
  ApiFailure? failure;
  String? signInNoticeKey;
  String effectiveLanguageTag = 'en';
  bool _hasEffectiveLanguagePreference = false;
  List<String> destinations = const [];
  UserPreferences? preferences;
  List<SupportedLanguage> supportedLanguages = const [];
  bool preferencesBusy = false;
  ApiFailure? preferencesFailure;
  String? _token;
  bool _needsResumeValidation = false;
  bool _needsLanguageInitialization = false;
  int _generation = 0;
  int? _validationGeneration;

  int get sessionGeneration => _generation;

  bool get hasEffectiveLanguagePreference => _hasEffectiveLanguagePreference;

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
      _hasEffectiveLanguagePreference = true;
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
    _hasEffectiveLanguagePreference = false;
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
      _needsLanguageInitialization = true;
      if (!await _completeSessionSetup(
        session.principal,
        session.token,
        generation,
      )) {
        return;
      }
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
    var passwordChanged = false;
    status = SessionStatus.changingPassword;
    failure = null;
    notifyListeners();
    try {
      await _api.changePassword(
        token: token,
        currentPassword: currentPassword,
        newPassword: newPassword,
      );
      if (generation != _generation) return;
      passwordChanged = true;
      _needsLanguageInitialization = true;
      final refreshed = await _api.currentPrincipal(token);
      if (generation != _generation) return;
      if (!await _completeSessionSetup(refreshed, token, generation)) return;
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
      // A lost response may follow a committed password change. Revalidate on
      // Retry instead of resubmitting the old password or opening the shell.
      status = error.kind == ApiFailureKind.offline || passwordChanged
          ? SessionStatus.validatingSession
          : SessionStatus.passwordChangeRequired;
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
        _clear();
        notifyListeners();
      }
    }
  }

  Future<void> onBackgrounded() async {
    if (hasProtectedState) _needsResumeValidation = true;
  }

  Future<bool> onResumed() async {
    if (!hasProtectedState || !_needsResumeValidation) return false;
    _needsResumeValidation = false;
    await validateSession();
    return !hasProtectedState;
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
      if (!await _completeSessionSetup(refreshed, token, generation)) return;
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

  Future<bool> _completeSessionSetup(
    AuthPrincipal refreshed,
    String token,
    int generation,
  ) async {
    if (generation != _generation) return false;
    // A session may never silently switch identity.
    if (refreshed.user.id != principal?.user.id) {
      clearForRevocation();
      return false;
    }
    if (refreshed.mustChangePassword) {
      principal = refreshed;
      destinations = const [];
      _needsLanguageInitialization = true;
      status = SessionStatus.passwordChangeRequired;
      return true;
    }
    // Bootstrap and capabilities are forbidden while a password change is
    // required. Publish authenticated state only after both have succeeded.
    final language = _needsLanguageInitialization
        ? await _api.effectiveLanguage(token)
        : effectiveLanguageTag;
    if (generation != _generation) return false;
    final capabilities = await _api.mobileCapabilities(token);
    if (generation != _generation) return false;
    principal = refreshed;
    effectiveLanguageTag = language;
    _hasEffectiveLanguagePreference = true;
    destinations = capabilities;
    _needsLanguageInitialization = false;
    status = SessionStatus.authenticated;
    return true;
  }

  Future<bool> authorizeNavigation() async {
    if (status != SessionStatus.authenticated) return false;
    final generation = _generation;
    await validateSession();
    return generation == _generation && status == SessionStatus.authenticated;
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
    _needsResumeValidation = false;
    _needsLanguageInitialization = false;
    effectiveLanguageTag = 'en';
    _hasEffectiveLanguagePreference = false;
    preferences = null;
    supportedLanguages = const [];
    preferencesBusy = false;
    preferencesFailure = null;
  }
}
