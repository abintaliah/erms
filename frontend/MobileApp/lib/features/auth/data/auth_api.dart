import 'dart:async';
import 'dart:convert';
import 'dart:io';

import '../../../core/network/api_failure.dart';
import '../domain/auth_principal.dart';

const mobileEventSource = 'mobile';
const mobileClientVersion = '0.1';

abstract interface class AuthApi {
  Future<AuthSession> signIn({required String email, required String password});

  Future<AuthPrincipal> currentPrincipal(String token);

  Future<void> changePassword({
    required String token,
    required String currentPassword,
    required String newPassword,
  });

  Future<void> signOut(String token);
}

class AuthSession {
  const AuthSession({required this.principal, required this.token});

  final AuthPrincipal principal;
  final String token;
}

class IoAuthApi implements AuthApi {
  IoAuthApi(this._baseUrl, {HttpClient? client, String? platformFamily})
    : _client = client ?? HttpClient(),
      _platformFamily = platformFamily ?? Platform.operatingSystem;

  final Uri _baseUrl;
  final HttpClient _client;
  final String _platformFamily;

  String get userAgent =>
      'WathiqMobile/$mobileClientVersion ($_platformFamily)';

  @override
  Future<AuthSession> signIn({
    required String email,
    required String password,
  }) async {
    final response = await _request(
      'POST',
      '/api/v1/auth/login',
      body: {'email': email, 'password': password},
    );
    final token = response.cookies
        .where((cookie) => cookie.name == 'erms_session')
        .map((cookie) => cookie.value)
        .firstOrNull;
    if (token == null || token.isEmpty) {
      throw const ApiFailure(ApiFailureKind.invalidResponse);
    }
    return AuthSession(principal: _principal(response.payload), token: token);
  }

  @override
  Future<AuthPrincipal> currentPrincipal(String token) async {
    final response = await _request('GET', '/api/v1/auth/me', token: token);
    return _principal(response.payload);
  }

  @override
  Future<void> changePassword({
    required String token,
    required String currentPassword,
    required String newPassword,
  }) async {
    await _request(
      'POST',
      '/api/v1/auth/change-password',
      token: token,
      body: {'current_password': currentPassword, 'new_password': newPassword},
    );
  }

  @override
  Future<void> signOut(String token) async {
    await _request('POST', '/api/v1/auth/logout', token: token);
  }

  Future<_ApiResponse> _request(
    String method,
    String path, {
    String? token,
    Map<String, Object?>? body,
  }) async {
    try {
      final request = await _client
          .openUrl(method, _baseUrl.resolve(path))
          .timeout(const Duration(seconds: 5));
      request.headers
        ..set(HttpHeaders.acceptHeader, 'application/json')
        ..set('X-Event-Source', mobileEventSource)
        ..set(HttpHeaders.userAgentHeader, userAgent);
      if (token != null) {
        request.headers.set(HttpHeaders.authorizationHeader, 'Bearer $token');
      }
      if (body != null) {
        request.headers.contentType = ContentType.json;
        request.write(jsonEncode(body));
      }
      final response = await request.close().timeout(
        const Duration(seconds: 30),
      );
      final bytes = await response.fold<List<int>>(
        <int>[],
        (buffer, chunk) => buffer..addAll(chunk),
      );
      final payload = bytes.isEmpty
          ? null
          : jsonDecode(utf8.decode(bytes, allowMalformed: false));
      if (response.statusCode < 200 || response.statusCode >= 300) {
        throw ApiFailure(
          _failureKind(response.statusCode),
          statusCode: response.statusCode,
        );
      }
      return _ApiResponse(payload: payload, cookies: response.cookies);
    } on ApiFailure {
      rethrow;
    } on SocketException catch (_) {
      throw const ApiFailure(ApiFailureKind.offline);
    } on TimeoutException catch (_) {
      throw const ApiFailure(ApiFailureKind.offline);
    } on FormatException catch (_) {
      throw const ApiFailure(ApiFailureKind.invalidResponse);
    } on JsonUnsupportedObjectError catch (_) {
      throw const ApiFailure(ApiFailureKind.invalidResponse);
    }
  }

  AuthPrincipal _principal(Object? payload) {
    if (payload is! Map) {
      throw const ApiFailure(ApiFailureKind.invalidResponse);
    }
    try {
      return AuthPrincipal.fromJson(
        payload.map((key, value) => MapEntry(key.toString(), value)),
      );
    } on FormatException catch (_) {
      throw const ApiFailure(ApiFailureKind.invalidResponse);
    }
  }

  ApiFailureKind _failureKind(int statusCode) => switch (statusCode) {
    401 => ApiFailureKind.unauthenticated,
    403 => ApiFailureKind.forbidden,
    400 || 409 || 422 => ApiFailureKind.invalidRequest,
    >= 500 => ApiFailureKind.server,
    _ => ApiFailureKind.invalidResponse,
  };
}

class _ApiResponse {
  const _ApiResponse({required this.payload, required this.cookies});

  final Object? payload;
  final List<Cookie> cookies;
}
