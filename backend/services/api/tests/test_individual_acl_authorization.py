import os
import uuid

import psycopg
import pytest

from backend.services.api.authentication import hash_password


@pytest.mark.parametrize('kind', ['aggregation', 'record'])
@pytest.mark.parametrize('global_grant,resource_grant', [(True, True), (False, True), (True, False)])
def test_individual_acl_does_not_require_system_administration(client, aggregation, record, kind, global_grant, resource_grant):
    resource = aggregation if kind == 'aggregation' else record
    plural = 'aggregations' if kind == 'aggregation' else 'records'
    password = 'Temporary-Test-Password-123!'
    with psycopg.connect(os.environ['DATABASE_URL']) as c:
        profile = c.execute("INSERT INTO profiles(code,name) VALUES (%s,%s) RETURNING id", ('acl-' + uuid.uuid4().hex, 'ACL manager ' + uuid.uuid4().hex)).fetchone()[0]
        codes = ['aggregation.view', 'record.view'] + ([f'{kind}.acl.manage'] if global_grant else [])
        c.execute('INSERT INTO profile_privileges(profile_id,privilege_id) SELECT %s,id FROM privileges WHERE code=ANY(%s)', (profile,codes))
        role = c.execute("INSERT INTO roles(org_unit_id,code,name,profile_id) VALUES (1,'limited-acl','Limited ACL',%s) RETURNING id", (profile,)).fetchone()[0]
        user = c.execute("INSERT INTO users(name,email) VALUES ('ACL Manager','acl@test.invalid') RETURNING id").fetchone()[0]
        c.execute('INSERT INTO user_role_assignments(user_id,role_id) VALUES (%s,%s)', (user,role))
        c.execute('INSERT INTO user_credentials(user_id,password_hash,must_change_password) VALUES (%s,%s,false)', (user,hash_password(password)))
    endpoint = f'/api/v1/{plural}/{resource["id"]}/permissions'
    original = client.get(endpoint).json()
    codes = [f'{kind}.view'] + ([f'{kind}.acl.manage'] if resource_grant else [])
    grants = [{k:v for k,v in grant.items() if k in {'principal_type','role_id','permission_codes'}} for grant in original['effective_acl']] + [{'principal_type':'role','role_id':role,'permission_codes':codes}]
    response = client.put(endpoint,json={'version':original['resource_acl_version'], 'inherit_acl_from_parent':False,'grants':grants,'reason':'Set up limited ACL manager'})
    assert response.status_code == 200, response.text
    version = response.json()['resource_acl_version']
    login = client.post('/api/v1/auth/login',json={'email':'acl@test.invalid','password':password})
    assert login.status_code == 200, login.text
    client.headers['X-CSRF-Token'] = client.cookies.get('erms_csrf')
    expected = 200 if global_grant and resource_grant else 403
    assert client.get(endpoint).status_code == expected
    response = client.put(endpoint,json={'version':version,'inherit_acl_from_parent':False,'grants':grants,'reason':'Manage individual ACL without system administration'})
    assert response.status_code == expected, response.text
    assert client.get('/api/v1/permissions',params={'resource_type':kind}).status_code == (200 if global_grant else 403)
    assert client.get(f'/api/v1/aggregations/{aggregation["id"]}/default-child-aggregation-permissions').status_code == 403
    assert client.get('/api/v1/profiles').status_code == 403
