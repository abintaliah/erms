class AppEnvironment {
  const AppEnvironment({required this.apiBaseUrl});

  factory AppEnvironment.fromCompileTime() {
    const rawBaseUrl = String.fromEnvironment('WATHIQ_API_BASE_URL');
    return AppEnvironment.fromValue(rawBaseUrl);
  }

  factory AppEnvironment.fromValue(String rawBaseUrl) {
    if (rawBaseUrl.isEmpty) {
      throw const FormatException(
        'WATHIQ_API_BASE_URL must be supplied with --dart-define.',
      );
    }
    final baseUrl = Uri.tryParse(rawBaseUrl);
    if (baseUrl == null || !baseUrl.hasScheme || baseUrl.host.isEmpty) {
      throw const FormatException(
        'WATHIQ_API_BASE_URL must be an absolute URL.',
      );
    }
    final isLocalDevelopment =
        baseUrl.host == 'localhost' ||
        baseUrl.host == '127.0.0.1' ||
        baseUrl.host == '::1';
    if (baseUrl.scheme != 'https' && !isLocalDevelopment) {
      throw const FormatException(
        'WATHIQ_API_BASE_URL must use HTTPS outside local development.',
      );
    }
    return AppEnvironment(apiBaseUrl: baseUrl);
  }

  final Uri apiBaseUrl;
}
