"""Default ACL actions require both the endpoint privilege and resource capability."""
import ast
from pathlib import Path

import pytest


@pytest.mark.parametrize('manage_acl,admin,expected', [
    (False, False, False), (True, False, False),
    (False, True, False), (True, True, True),
])
def test_acl_defaults_visibility_matches_endpoint_gates(manage_acl, admin, expected):
    source = ast.parse((Path(__file__).parents[1] / 'app.py').read_text())
    assignment = next(n for n in ast.walk(source) if isinstance(n, ast.Assign)
                      and any(isinstance(t, ast.Name) and t.id == 'show_acl_defaults'
                              for t in n.targets))
    result = eval(compile(ast.Expression(assignment.value), 'app.py', 'eval'), {
        'capabilities': {'manage_acl': manage_acl},
        'auth_state': {'principal': {'global_privileges': ['authorization.administer'] if admin else []}},
    })
    assert result is expected
