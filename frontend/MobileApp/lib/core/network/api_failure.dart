enum ApiFailureKind {
  offline,
  unauthenticated,
  forbidden,
  invalidRequest,
  server,
  invalidResponse,
}

class ApiFailure implements Exception {
  const ApiFailure(
    this.kind, {
    this.statusCode,
    this.messageKey,
    this.parameters = const {},
    this.passwordField,
  });

  final ApiFailureKind kind;
  final int? statusCode;
  final String? messageKey;
  final Map<String, int> parameters;
  final String? passwordField;
}
