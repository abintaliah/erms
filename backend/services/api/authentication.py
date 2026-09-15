from __future__ import annotations

import hashlib
import ipaddress
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from psycopg import Connection

from .config import boolean_environment, integer_environment
from .database import get_connection
from .schemas import ChangePasswordRequest, LoginRequest, LoginSessionRead, PrincipalRead


SESSION_COOKIE = "erms_session"
CSRF_COOKIE = "erms_csrf"
SYSTEM_ADMIN_ROLE = "system-administrator"
IDLE_MINUTES = integer_environment("AUTH_SESSION_IDLE_MINUTES", 30, minimum=1)
ABSOLUTE_HOURS = integer_environment("AUTH_SESSION_ABSOLUTE_HOURS", 12, minimum=1)
LOCKOUT_ATTEMPTS = integer_environment("AUTH_LOCKOUT_ATTEMPTS", 5, minimum=1)
LOCKOUT_MINUTES = integer_environment("AUTH_LOCKOUT_MINUTES", 15, minimum=1)
PASSWORD_MIN_LENGTH = integer_environment("AUTH_PASSWORD_MIN_LENGTH", 12, minimum=8)
COOKIE_SECURE = boolean_environment("AUTH_COOKIE_SECURE", False)
password_hasher = PasswordHasher()


@dataclass(frozen=True)
class Principal:
    user_id: int
    session_id: int
    name: str
    email: str
    account_type: str
    must_change_password: bool
    roles: list[dict[str, Any]]

    @property
    def is_system_administrator(self) -> bool:
        return any(role["code"].lower() == SYSTEM_ADMIN_ROLE for role in self.roles)


def hash_secret(value: str) -> bytes:
    return hashlib.sha256(value.encode("utf-8")).digest()


def hash_password(password: str) -> str:
    validate_password(password)
    return password_hasher.hash(password)


def validate_password(password: str) -> None:
    if len(password) < PASSWORD_MIN_LENGTH:
        raise ValueError(f"password must contain at least {PASSWORD_MIN_LENGTH} characters")


def _roles(connection: Connection, user_id: int) -> list[dict[str, Any]]:
    return list(connection.execute(
        """
        SELECT r.id, r.code, r.name,
               jsonb_build_object('id', ou.id, 'code', ou.code, 'name', ou.name) AS org_unit
        FROM user_role_assignments ura
        JOIN roles r ON r.id = ura.role_id AND r.status = 'active'
        JOIN org_units ou ON ou.id = r.org_unit_id
        WHERE ura.user_id = %s
          AND ura.valid_from <= CURRENT_TIMESTAMP
          AND (ura.valid_until IS NULL OR ura.valid_until > CURRENT_TIMESTAMP)
        ORDER BY r.name, r.id
        """, (user_id,)
    ).fetchall())


def resolve_principal(connection: Connection, token: str) -> Principal | None:
    row = connection.execute(
        """
        SELECT s.id AS session_id, s.user_id, u.name, u.email, u.account_type,
               c.must_change_password
        FROM login_sessions s
        JOIN users u ON u.id = s.user_id
        JOIN user_credentials c ON c.user_id = u.id
        WHERE s.session_token_hash = %s
          AND s.revoked_at IS NULL
          AND s.expires_at > CURRENT_TIMESTAMP
          AND s.absolute_expires_at > CURRENT_TIMESTAMP
          AND u.status = 'active'
          AND u.account_type = 'human'
        """, (hash_secret(token),)
    ).fetchone()
    if not row:
        return None
    connection.execute(
        """
        UPDATE login_sessions
        SET last_seen_at = CURRENT_TIMESTAMP,
            expires_at = LEAST(CURRENT_TIMESTAMP + make_interval(mins => %s), absolute_expires_at)
        WHERE id = %s AND last_seen_at < CURRENT_TIMESTAMP - interval '1 minute'
        """, (IDLE_MINUTES, row["session_id"])
    )
    return Principal(
        user_id=row["user_id"], session_id=row["session_id"], name=row["name"],
        email=row["email"], account_type=row["account_type"],
        must_change_password=row["must_change_password"], roles=_roles(connection, row["user_id"]),
    )


def principal_from_request(request: Request) -> Principal:
    principal = getattr(request.state, "principal", None)
    if principal is None:
        raise HTTPException(status_code=401, detail="authentication required")
    return principal


def require_system_administrator(principal: Principal = Depends(principal_from_request)) -> Principal:
    if not principal.is_system_administrator:
        raise HTTPException(status_code=403, detail="system administrator role required")
    return principal


def _append_event(connection: Connection, user_id: int, operation: str, metadata: dict[str, Any]) -> None:
    connection.execute(
        "SELECT append_domain_event('user', %s, %s, %s::jsonb)",
        (user_id, operation, __import__("json").dumps(metadata)),
    )


router = APIRouter(prefix="/api/v1/auth", tags=["authentication"])


@router.post("/login", response_model=PrincipalRead)
def login(payload: LoginRequest, request: Request, response: Response, connection: Connection = Depends(get_connection)):
    generic = HTTPException(status_code=401, detail="invalid email or password")
    row = connection.execute(
        """
        SELECT u.id, u.name, u.email, u.account_type, u.status,
               c.password_hash, c.must_change_password, c.temporary_expires_at,
               c.failed_attempt_count, c.locked_until
        FROM users u JOIN user_credentials c ON c.user_id = u.id
        WHERE lower(u.email) = lower(%s)
        FOR UPDATE OF c
        """, (payload.email,)
    ).fetchone()
    now = datetime.now(timezone.utc)
    if not row or row["status"] != "active" or row["account_type"] != "human":
        raise generic
    if row["locked_until"] and row["locked_until"] > now:
        raise generic
    try:
        valid = password_hasher.verify(row["password_hash"], payload.password)
    except (VerifyMismatchError, InvalidHashError):
        valid = False
    if not valid:
        attempts = row["failed_attempt_count"] + 1
        locked_until = now + timedelta(minutes=LOCKOUT_MINUTES) if attempts >= LOCKOUT_ATTEMPTS else None
        connection.execute(
            "UPDATE user_credentials SET failed_attempt_count=%s, last_failed_at=%s, locked_until=%s, date_updated=%s WHERE user_id=%s",
            (attempts, now, locked_until, now, row["id"]),
        )
        _append_event(connection, row["id"], "AUTHENTICATION_FAILED", {"locked": bool(locked_until)})
        # The request intentionally ends with an HTTP error. Persist the failure
        # before raising so the dependency cleanup cannot roll back lockout state.
        connection.commit()
        raise generic
    if row["temporary_expires_at"] and row["temporary_expires_at"] <= now:
        raise HTTPException(status_code=401, detail="temporary password has expired")
    token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    expires_at = now + timedelta(minutes=IDLE_MINUTES)
    absolute_at = now + timedelta(hours=ABSOLUTE_HOURS)
    client_ip = request.client.host if request.client else None
    try:
        client_ip = str(ipaddress.ip_address(client_ip)) if client_ip else None
    except ValueError:
        client_ip = None
    session = connection.execute(
        """
        INSERT INTO login_sessions
            (user_id, session_token_hash, csrf_token_hash, expires_at, absolute_expires_at, client_ip, user_agent)
        VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id
        """,
        (row["id"], hash_secret(token), hash_secret(csrf), expires_at, absolute_at,
         client_ip, request.headers.get("user-agent")),
    ).fetchone()
    connection.execute(
        "UPDATE user_credentials SET failed_attempt_count=0, locked_until=NULL, last_authenticated_at=%s, date_updated=%s WHERE user_id=%s",
        (now, now, row["id"]),
    )
    connection.execute(
        "SELECT set_config('app.user_id', %s, true), set_config('app.actor_type', 'user', true)",
        (str(row["id"]),),
    )
    _append_event(connection, row["id"], "AUTHENTICATION_SUCCEEDED", {"session_id": session["id"]})
    response.set_cookie(SESSION_COOKIE, token, httponly=True, secure=COOKIE_SECURE, samesite="lax", path="/")
    response.set_cookie(CSRF_COOKIE, csrf, httponly=False, secure=COOKIE_SECURE, samesite="lax", path="/")
    principal = Principal(row["id"], session["id"], row["name"], row["email"], row["account_type"], row["must_change_password"], _roles(connection, row["id"]))
    return principal_response(principal)


def principal_response(principal: Principal) -> dict[str, Any]:
    return {
        "user": {"id": principal.user_id, "name": principal.name, "email": principal.email, "account_type": principal.account_type},
        "roles": principal.roles,
        "session": {"id": principal.session_id},
        "must_change_password": principal.must_change_password,
    }


@router.get("/me", response_model=PrincipalRead)
def me(principal: Principal = Depends(principal_from_request)):
    return principal_response(principal)


@router.post("/logout", status_code=204)
def logout(response: Response, principal: Principal = Depends(principal_from_request), connection: Connection = Depends(get_connection)):
    connection.execute("UPDATE login_sessions SET revoked_at=CURRENT_TIMESTAMP, revoked_by=%s WHERE id=%s", (principal.user_id, principal.session_id))
    _append_event(connection, principal.user_id, "SESSION_REVOKED", {"session_id": principal.session_id, "scope": "current"})
    response.delete_cookie(SESSION_COOKIE, path="/")
    response.delete_cookie(CSRF_COOKIE, path="/")
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.post("/change-password", status_code=204)
def change_password(payload: ChangePasswordRequest, principal: Principal = Depends(principal_from_request), connection: Connection = Depends(get_connection)):
    credential = connection.execute("SELECT password_hash FROM user_credentials WHERE user_id=%s", (principal.user_id,)).fetchone()
    try:
        valid = password_hasher.verify(credential["password_hash"], payload.current_password)
    except (VerifyMismatchError, InvalidHashError):
        valid = False
    if not valid:
        raise HTTPException(status_code=400, detail="current password is incorrect")
    try:
        new_hash = hash_password(payload.new_password)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    connection.execute(
        "UPDATE user_credentials SET password_hash=%s, must_change_password=false, temporary_expires_at=NULL, password_changed_at=CURRENT_TIMESTAMP, date_updated=CURRENT_TIMESTAMP WHERE user_id=%s",
        (new_hash, principal.user_id),
    )
    connection.execute("UPDATE login_sessions SET revoked_at=CURRENT_TIMESTAMP, revoked_by=%s WHERE user_id=%s AND id<>%s AND revoked_at IS NULL", (principal.user_id, principal.user_id, principal.session_id))
    _append_event(connection, principal.user_id, "PASSWORD_CHANGED", {"other_sessions_revoked": True})
    return Response(status_code=204)


@router.get("/sessions", response_model=list[LoginSessionRead])
def list_sessions(principal: Principal = Depends(principal_from_request), connection: Connection = Depends(get_connection)):
    admin = principal.is_system_administrator
    return list(connection.execute(
        """
        SELECT s.id, s.user_id, u.name AS user_name, u.email AS user_email, u.account_type,
               s.date_created, s.last_seen_at, s.expires_at, s.absolute_expires_at,
               s.revoked_at, host(s.client_ip) AS client_ip, s.user_agent,
               (s.id=%s) AS is_current,
               CASE WHEN s.revoked_at IS NOT NULL THEN 'revoked'
                    WHEN s.expires_at <= CURRENT_TIMESTAMP OR s.absolute_expires_at <= CURRENT_TIMESTAMP THEN 'expired'
                    ELSE 'active' END AS status
        FROM login_sessions s JOIN users u ON u.id=s.user_id
        WHERE (%s OR s.user_id=%s) ORDER BY s.date_created DESC
        """, (principal.session_id, admin, principal.user_id)
    ).fetchall())


@router.delete("/sessions/{session_id}", status_code=204)
def revoke_session(session_id: int, principal: Principal = Depends(principal_from_request), connection: Connection = Depends(get_connection)):
    target = connection.execute("SELECT user_id FROM login_sessions WHERE id=%s", (session_id,)).fetchone()
    if not target:
        raise HTTPException(status_code=404, detail="session not found")
    if target["user_id"] != principal.user_id and not principal.is_system_administrator:
        raise HTTPException(status_code=403, detail="system administrator role required")
    connection.execute("UPDATE login_sessions SET revoked_at=COALESCE(revoked_at,CURRENT_TIMESTAMP), revoked_by=%s WHERE id=%s", (principal.user_id, session_id))
    _append_event(connection, target["user_id"], "SESSION_REVOKED", {"session_id": session_id, "revoked_by": principal.user_id})
    return Response(status_code=204)


@router.delete("/users/{user_id}/sessions", status_code=204, dependencies=[Depends(require_system_administrator)])
def revoke_user_sessions(user_id: int, principal: Principal = Depends(principal_from_request), connection: Connection = Depends(get_connection)):
    connection.execute("UPDATE login_sessions SET revoked_at=CURRENT_TIMESTAMP, revoked_by=%s WHERE user_id=%s AND revoked_at IS NULL", (principal.user_id, user_id))
    _append_event(connection, user_id, "SESSION_REVOKED", {"scope": "all", "revoked_by": principal.user_id})
    return Response(status_code=204)


@router.post("/users/{user_id}/temporary-password", dependencies=[Depends(require_system_administrator)])
def issue_temporary_password(user_id: int, principal: Principal = Depends(principal_from_request), connection: Connection = Depends(get_connection)):
    user = connection.execute("SELECT id, email, account_type FROM users WHERE id=%s", (user_id,)).fetchone()
    if not user:
        raise HTTPException(status_code=404, detail="user not found")
    if user["account_type"] != "human" or not user["email"]:
        raise HTTPException(status_code=422, detail="local passwords require a human user with an email address")
    password = secrets.token_urlsafe(15)
    password_hash = hash_password(password)
    temporary_expires_at = datetime.now(timezone.utc) + timedelta(hours=24)
    connection.execute(
        """
        INSERT INTO user_credentials (user_id,password_hash,must_change_password,temporary_expires_at)
        VALUES (%s,%s,true,%s)
        ON CONFLICT (user_id) DO UPDATE SET
          password_hash=EXCLUDED.password_hash, must_change_password=true,
          temporary_expires_at=EXCLUDED.temporary_expires_at,
          password_changed_at=CURRENT_TIMESTAMP, failed_attempt_count=0,
          locked_until=NULL, date_updated=CURRENT_TIMESTAMP
        """, (user_id, password_hash, temporary_expires_at)
    )
    connection.execute(
        "UPDATE login_sessions SET revoked_at=CURRENT_TIMESTAMP, revoked_by=%s WHERE user_id=%s AND revoked_at IS NULL",
        (principal.user_id, user_id),
    )
    _append_event(connection, user_id, "PASSWORD_RESET", {"temporary": True, "expires_at": temporary_expires_at.isoformat()})
    return {"temporary_password": password, "expires_at": temporary_expires_at}
