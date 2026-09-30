enum ApiFailureKind {
  offline,
  unauthenticated,
  forbidden,
  invalidRequest,
  server,
  invalidResponse,
}

class ApiFailure implements Exception {
  const ApiFailure(this.kind, {this.statusCode});

  final ApiFailureKind kind;
  final int? statusCode;
}
