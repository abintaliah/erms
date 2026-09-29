"""Saved-search errors identify unavailability without leaking inspector markers."""
import ast
from pathlib import Path
from types import SimpleNamespace


def test_saved_search_404_is_specific_and_other_404_remains_generic():
    tree = ast.parse((Path(__file__).parents[1] / 'app.py').read_text())
    function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'error_message')
    namespace = {'ApiError': object, 'render_message_plain': lambda key, **kwargs: key}
    exec(compile(ast.Module(body=[function], type_ignores=[]), 'app.py', 'exec'), namespace)
    render = namespace['error_message']
    assert render(SimpleNamespace(status_code=404, message='saved search not found', detail='saved search not found')) == 'saved_search.error.unavailable'
    assert render(SimpleNamespace(status_code=404, message='missing', detail={'code':'saved_search_unavailable', 'message_key':'saved_search.error.unavailable'})) == 'saved_search.error.unavailable'
    assert render(SimpleNamespace(status_code=404, message='Not Found', detail='Not Found')) == 'common.error.not_found'
