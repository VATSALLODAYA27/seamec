"""Who is signed in, and what they may do.

Roles: "ops" files daily reports; "manager" approves reports, invoices and renewals; "admin" can do everything,
including contracts and user accounts; "client" is a charterer's representative who only sees the client portal.

Sign-in sets a random token in an HttpOnly, SameSite=Strict cookie; the server keeps only the token's SHA-256.
"""
import hashlib
import hmac
import os
from datetime import timedelta

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from .db import get_session
from .models import AuditEntry, LoginToken, User, now

COOKIE_NAME = "maris_session"
TOKEN_TTL = timedelta(hours=10)
PBKDF2_ROUNDS = 240_000


def make_hash(password: str) -> str:
    salt = os.urandom(16)
    key = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PBKDF2_ROUNDS)
    return f"pbkdf2${PBKDF2_ROUNDS}${salt.hex()}${key.hex()}"


def check_hash(password: str, stored: str) -> bool:
    _, rounds, salt, key = stored.split("$")
    candidate = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), int(rounds))
    return hmac.compare_digest(candidate.hex(), key)


def digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def new_token(session: Session, user: User) -> str:
    token = os.urandom(32).hex()
    session.add(LoginToken(digest=digest(token), username=user.username, expires_at=now() + TOKEN_TTL.total_seconds()))
    return token


def current_user(request: Request, session: Session = Depends(get_session)) -> User:
    token = request.cookies.get(COOKIE_NAME, "")
    row = session.get(LoginToken, digest(token)) if token else None
    if row is None or row.expires_at < now():
        raise HTTPException(401, "Please sign in.")
    user = session.get(User, row.username)
    if user is None or not user.active:
        raise HTTPException(401, "This account is switched off.")
    return user


def role_in(*roles: str):
    """Let through only these roles. Admin always gets through."""

    def check(user: User = Depends(current_user)) -> User:
        if user.role != "admin" and user.role not in roles:
            raise HTTPException(403, "Your role cannot do this.")
        return user

    return check


manager = role_in("manager")
admin = role_in()
# Everyone who works for SEAMEC. A client account is kept to the client portal.
staff = role_in("ops", "manager")


def audit(session: Session, user: User | None, action: str, target: str = "", detail: str = "", username: str = "") -> None:
    session.add(AuditEntry(username=user.username if user else username, role=user.role if user else "", action=action, target=target, detail=detail))
