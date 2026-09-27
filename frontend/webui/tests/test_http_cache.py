from fastapi import Request, Response

from backend.services.api.http_cache import apply_collection_etag


def _request(if_none_match: str | None = None) -> Request:
    headers = []
    if if_none_match is not None:
        headers.append((b"if-none-match", if_none_match.encode("ascii")))
    return Request({"type": "http", "method": "GET", "path": "/", "headers": headers})


def test_collection_etag_is_deterministic_and_private():
    first_response = Response()
    assert apply_collection_etag(
        _request(), first_response, [{"name": "A", "id": 1}],
    ) is None
    second_response = Response()
    assert apply_collection_etag(
        _request(), second_response, [{"id": 1, "name": "A"}],
    ) is None
    assert first_response.headers["etag"] == second_response.headers["etag"]
    assert first_response.headers["cache-control"] == "private, no-cache"


def test_collection_etag_returns_not_modified_for_matching_validator():
    response = Response()
    apply_collection_etag(_request(), response, [{"id": 1}])
    not_modified = apply_collection_etag(
        _request(response.headers["etag"]), Response(), [{"id": 1}],
    )
    assert not_modified is not None
    assert not_modified.status_code == 304
    assert not_modified.headers["etag"] == response.headers["etag"]
