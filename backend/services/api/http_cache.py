from __future__ import annotations

import hashlib
import json
from typing import Any

from fastapi import Request, Response
from fastapi.encoders import jsonable_encoder


def apply_collection_etag(
    request: Request, response: Response, rows: Any,
) -> Response | None:
    """Attach a deterministic ETag and return a 304 response when unchanged."""
    encoded = json.dumps(
        jsonable_encoder(rows), ensure_ascii=False, sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    etag = f'"sha256-{hashlib.sha256(encoded).hexdigest()}"'
    response.headers["ETag"] = etag
    response.headers["Cache-Control"] = "private, no-cache"
    if request.headers.get("If-None-Match") == etag:
        return Response(
            status_code=304,
            headers={"ETag": etag, "Cache-Control": "private, no-cache"},
        )
    return None
