import 'package:flutter_test/flutter_test.dart';
import 'package:wathiq_mobile/features/auth/domain/auth_principal.dart';

void main() {
  test('principal parses the existing authentication response contract', () {
    final principal = AuthPrincipal.fromJson(_principalJson());

    expect(principal.user.id, 7);
    expect(principal.user.email, 'user@example.test');
    expect(principal.sessionId, 19);
    expect(principal.mustChangePassword, isFalse);
    expect(principal.globalPrivileges, {'records.view'});
    expect(principal.roles.single.code, 'records-user');
    expect(principal.previousLoginAt, DateTime.parse('2026-09-30T08:00:00Z'));
  });

  test('principal rejects missing authorization fields', () {
    final json = _principalJson()..remove('global_privileges');

    expect(() => AuthPrincipal.fromJson(json), throwsFormatException);
  });

  test('principal rejects malformed session identity', () {
    final json = _principalJson();
    json['session'] = {'id': '19'};

    expect(() => AuthPrincipal.fromJson(json), throwsFormatException);
  });
}

Map<String, Object?> _principalJson({bool mustChangePassword = false}) => {
  'user': {
    'id': 7,
    'name': 'Records User',
    'email': 'user@example.test',
    'account_type': 'person',
    'localized': {'name': 'Records User'},
  },
  'roles': [
    {
      'id': 2,
      'code': 'records-user',
      'name': 'Records User',
      'org_unit': {'id': 1, 'code': 'root', 'name': 'Root'},
    },
  ],
  'session': {'id': 19},
  'must_change_password': mustChangePassword,
  'previous_login_at': '2026-09-30T08:00:00Z',
  'global_privileges': ['records.view'],
};
