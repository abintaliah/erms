import hashlib
import os
from dataclasses import dataclass
from typing import BinaryIO, Protocol

from fastapi import HTTPException, UploadFile, status
from psycopg import Connection

from .config import integer_environment

CHUNK_SIZE = 1024 * 1024


@dataclass(frozen=True)
class UploadedContent:
    content: bytes
    size_in_bytes: int
    checksum_value: str


class ContentStorage(Protocol):
    def store(self, connection: Connection, component_id: int, content: bytes) -> None: ...
    def read(self, connection: Connection, component_id: int) -> bytes | None: ...
    def delete(self, connection: Connection, component_id: int) -> bool: ...


class PostgreSQLContentStorage:
    def store(self, connection: Connection, component_id: int, content: bytes) -> None:
        connection.execute(
            """INSERT INTO digital_component_blobs (digital_component_id, content)
               VALUES (%s, %s)
               ON CONFLICT (digital_component_id) DO UPDATE
               SET content = EXCLUDED.content, date_stored = CURRENT_TIMESTAMP""",
            (component_id, content),
        )

    def read(self, connection: Connection, component_id: int) -> bytes | None:
        row = connection.execute(
            "SELECT content FROM digital_component_blobs WHERE digital_component_id = %s",
            (component_id,),
        ).fetchone()
        return None if row is None else bytes(row["content"])

    def delete(self, connection: Connection, component_id: int) -> bool:
        return connection.execute(
            "DELETE FROM digital_component_blobs WHERE digital_component_id = %s RETURNING digital_component_id",
            (component_id,),
        ).fetchone() is not None


def configured_storage() -> ContentStorage:
    backend = os.getenv("CONTENT_STORAGE_BACKEND", "postgresql").strip().lower()
    if backend != "postgresql":
        raise RuntimeError(f"unsupported CONTENT_STORAGE_BACKEND: {backend}")
    return PostgreSQLContentStorage()


def read_upload(upload: UploadFile) -> UploadedContent:
    maximum = integer_environment("MAX_UPLOAD_SIZE_BYTES", 50 * 1024 * 1024, minimum=1)
    digest = hashlib.sha256()
    chunks: list[bytes] = []
    size = 0
    source: BinaryIO = upload.file
    while chunk := source.read(CHUNK_SIZE):
        size += len(chunk)
        if size > maximum:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail=f"file exceeds the configured {maximum}-byte upload limit",
            )
        digest.update(chunk)
        chunks.append(chunk)
    return UploadedContent(b"".join(chunks), size, digest.hexdigest())
