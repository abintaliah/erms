"""Audience browsing shares typeahead eligibility and pages after filtering."""
import os

import psycopg

from backend.services.api.authentication import hash_password


def test_saved_audience_tree_retains_only_eligible_paths_and_admin_scope(client):
    with psycopg.connect(os.environ['DATABASE_URL']) as db:
        root = db.execute("INSERT INTO org_units(code,name) VALUES ('AUD-ROOT','Audience root') RETURNING id").fetchone()[0]
        mine = db.execute("INSERT INTO org_units(code,name,parent_org_unit_id) VALUES ('AUD-MINE','Audience mine',%s) RETURNING id", (root,)).fetchone()[0]
        other = db.execute("INSERT INTO org_units(code,name,parent_org_unit_id) VALUES ('AUD-OTHER','Audience other',%s) RETURNING id", (root,)).fetchone()[0]
        profile = db.execute("INSERT INTO profiles(code,name) VALUES ('AUD-BROWSER','Audience browser') RETURNING id").fetchone()[0]
        db.execute("INSERT INTO profile_privileges(profile_id,privilege_id) SELECT %s,id FROM privileges WHERE code IN ('organization.browse','search.saved_search.save','record.view')", (profile,))
        user = db.execute("INSERT INTO users(name,email) VALUES ('Audience user','audience@test.invalid') RETURNING id").fetchone()[0]
        roles = []
        for code, unit in [('AUD-A', mine), ('AUD-B', mine), ('AUD-X', other)]:
            roles.append(db.execute("INSERT INTO roles(code,name,org_unit_id,profile_id) VALUES (%s,%s,%s,%s) RETURNING id", (code, code, unit, profile)).fetchone()[0])
        for role in roles[:2]:
            db.execute("INSERT INTO user_role_assignments(user_id,role_id) VALUES (%s,%s)", (user,role))
        db.execute("INSERT INTO user_credentials(user_id,password_hash,must_change_password) VALUES (%s,%s,false)", (user,hash_password('Audience-Test-123!')))

    # An administrator may browse outside their memberships.
    path = f'/api/v1/browse/organization/org-units/{other}/children'
    admin = client.get(path, params={'audience':'roles'}).json()
    assert [r['id'] for r in admin['roles']] == [roles[2]]
    assert admin['roles'][0]['audience_selectable']
    login = client.post('/api/v1/auth/login', json={'email':'audience@test.invalid','password':'Audience-Test-123!'})
    assert login.status_code == 200, login.text
    client.headers['X-CSRF-Token'] = client.cookies.get('erms_csrf')

    roots = client.get('/api/v1/browse/organization/roots', params={'audience':'org-units'}).json()
    assert [r['id'] for r in roots] == [root]
    assert roots[0]['audience_selectable'] is False
    children_path = f'/api/v1/browse/organization/org-units/{root}/children'
    children = client.get(children_path, params={'audience':'org-units'}).json()
    assert [r['id'] for r in children['org_units']] == [mine]
    assert children['org_units'][0]['audience_selectable'] is True
    assert children['roles'] == []
    # General organization browsing is unchanged.
    assert len(client.get(children_path).json()['org_units']) == 2
    assert client.get(path, params={'audience':'roles'}).json()['roles'] == []

    mine_path = f'/api/v1/browse/organization/org-units/{mine}/children'
    first = client.get(mine_path, params={'audience':'roles','limit':1}).json()
    second = client.get(mine_path, params={'audience':'roles','limit':1,'role_offset':1}).json()
    assert [r['id'] for r in first['roles']] == roles[:1]
    assert [r['id'] for r in second['roles']] == roles[1:2]
    assert first['more_roles'] and not second['more_roles']
    for kind, expected in [('roles',roles[:2]),('org-units',[mine])]:
        searched = client.get('/api/v1/browse/organization/search', params={'query':'AUD','audience':kind}).json()
        assert sorted(r['id'] for r in searched) == sorted(expected)
        assert all(r['audience_selectable'] for r in searched)
        options = client.get(f'/api/v1/saved-searches/audience-options/{kind}', params={'q':'AUD'}).json()
        assert sorted(r['id'] for r in options['items']) == sorted(expected)
    # Fresh membership changes immediately remove choices; no identity-wide cache.
    with psycopg.connect(os.environ['DATABASE_URL']) as db:
        db.execute('DELETE FROM user_role_assignments WHERE user_id=%s AND role_id=%s',(user,roles[1]))
    assert [r['id'] for r in client.get(mine_path,params={'audience':'roles'}).json()['roles']] == roles[:1]
