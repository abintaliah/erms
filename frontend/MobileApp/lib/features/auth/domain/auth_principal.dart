class AuthPrincipal {
  const AuthPrincipal({
    required this.user,
    required this.sessionId,
    required this.mustChangePassword,
    required this.globalPrivileges,
    required this.roles,
    this.previousLoginAt,
  });

  factory AuthPrincipal.fromJson(Map<String, Object?> json) {
    final user = _map(json['user'], 'user');
    final session = _map(json['session'], 'session');
    final roles = _list(json['roles'], 'roles')
        .map((value) => AuthRole.fromJson(_map(value, 'role')))
        .toList(growable: false);
    final privileges = _list(json['global_privileges'], 'global_privileges')
        .map((value) {
          if (value is! String) {
            throw const FormatException('Invalid global privilege.');
          }
          return value;
        })
        .toSet();

    return AuthPrincipal(
      user: AuthUser.fromJson(user),
      sessionId: _integer(session['id'], 'session.id'),
      mustChangePassword: _boolean(
        json['must_change_password'],
        'must_change_password',
      ),
      previousLoginAt: _optionalDateTime(
        json['previous_login_at'],
        'previous_login_at',
      ),
      globalPrivileges: Set.unmodifiable(privileges),
      roles: List.unmodifiable(roles),
    );
  }

  final AuthUser user;
  final int sessionId;
  final bool mustChangePassword;
  final DateTime? previousLoginAt;
  final Set<String> globalPrivileges;
  final List<AuthRole> roles;
}

class AuthUser {
  const AuthUser({
    required this.id,
    required this.name,
    required this.email,
    required this.accountType,
    this.localizedName,
  });

  factory AuthUser.fromJson(Map<String, Object?> json) {
    final localized = json['localized'];
    return AuthUser(
      id: _integer(json['id'], 'user.id'),
      name: _string(json['name'], 'user.name'),
      email: _string(json['email'], 'user.email'),
      accountType: _string(json['account_type'], 'user.account_type'),
      localizedName: localized is Map ? localized['name'] as String? : null,
    );
  }

  final int id;
  final String name;
  final String email;
  final String accountType;
  final String? localizedName;
}

class AuthRole {
  const AuthRole({required this.id, required this.code, required this.name});

  factory AuthRole.fromJson(Map<String, Object?> json) => AuthRole(
    id: _integer(json['id'], 'role.id'),
    code: _string(json['code'], 'role.code'),
    name: _string(json['name'], 'role.name'),
  );

  final int id;
  final String code;
  final String name;
}

Map<String, Object?> _map(Object? value, String field) {
  if (value is! Map) {
    throw FormatException('Invalid $field.');
  }
  return value.map((key, item) => MapEntry(key.toString(), item));
}

List<Object?> _list(Object? value, String field) {
  if (value is! List) {
    throw FormatException('Invalid $field.');
  }
  return value;
}

String _string(Object? value, String field) {
  if (value is! String) {
    throw FormatException('Invalid $field.');
  }
  return value;
}

int _integer(Object? value, String field) {
  if (value is! int) {
    throw FormatException('Invalid $field.');
  }
  return value;
}

bool _boolean(Object? value, String field) {
  if (value is! bool) {
    throw FormatException('Invalid $field.');
  }
  return value;
}

DateTime? _optionalDateTime(Object? value, String field) {
  if (value == null) {
    return null;
  }
  if (value is! String) {
    throw FormatException('Invalid $field.');
  }
  final parsed = DateTime.tryParse(value);
  if (parsed == null) {
    throw FormatException('Invalid $field.');
  }
  return parsed;
}
