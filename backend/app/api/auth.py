"""Signing in and out, and (admin only) the user accounts."""
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .. import config
from ..auth import COOKIE_NAME, TOKEN_TTL, admin, audit, check_hash, current_user, digest, make_hash, new_token
from ..db import get_session
from ..models import LoginToken, User
from ..schemas import LoginIn, UserActiveIn, UserCreateIn

router = APIRouter(prefix="/api/auth", tags=["sign-in"])

# Compared against when the username is unknown, so both failures take the same time.
_DECOY = make_hash("decoy-password")


def user_out(u: User) -> dict:
    return {"username": u.username, "name": u.name, "role": u.role, "active": u.active, "client_name": u.client_name}


@router.post("/login")
def login(body: LoginIn, response: Response, session: Session = Depends(get_session)):
    # shortcut: no lockout after repeated failures (each is in the audit log); add one before going live
    user = session.get(User, body.username)
    ok = check_hash(body.password, user.password_hash if user else _DECOY)
    if not ok or user is None or not user.active:
        audit(session, None, "login.failed", username=body.username[:64])
        session.commit()
        raise HTTPException(401, "Username or password is wrong, or the account is switched off.")
    token = new_token(session, user)
    audit(session, user, "login")
    session.commit()
    response.set_cookie(COOKIE_NAME, token, max_age=int(TOKEN_TTL.total_seconds()), httponly=True, samesite="strict", secure=config.COOKIE_SECURE)
    return user_out(user)


@router.post("/logout", status_code=204)
def logout(request: Request, response: Response, user: User = Depends(current_user), session: Session = Depends(get_session)):
    session.execute(delete(LoginToken).where(LoginToken.digest == digest(request.cookies.get(COOKIE_NAME, ""))))
    audit(session, user, "logout")
    session.commit()
    response.delete_cookie(COOKIE_NAME)


@router.get("/me")
def me(user: User = Depends(current_user)):
    return user_out(user)


users = APIRouter(prefix="/api/users", tags=["users"])


@users.get("", dependencies=[Depends(admin)])
def list_users(session: Session = Depends(get_session)):
    return [user_out(u) for u in session.scalars(select(User).order_by(User.role, User.username))]


@users.post("", status_code=201)
def create_user(body: UserCreateIn, me: User = Depends(admin), session: Session = Depends(get_session)):
    if session.get(User, body.username):
        raise HTTPException(409, f"The username {body.username} is taken.")
    user = User(username=body.username, name=body.name.strip(), role=body.role, password_hash=make_hash(body.password), active=True,
                client_name=body.client_name.strip() if body.role == "client" and body.client_name else None)
    session.add(user)
    audit(session, me, "user.created", f"user {user.username}", user.role)
    session.commit()
    return user_out(user)


@users.post("/{username}/active")
def set_active(username: str, body: UserActiveIn, me: User = Depends(admin), session: Session = Depends(get_session)):
    user = session.get(User, username)
    if user is None:
        raise HTTPException(404, "No such user.")
    if user.username == me.username:
        raise HTTPException(409, "You cannot switch off your own account.")
    user.active = body.active
    if not body.active:  # signed-in sessions stop working at once
        session.execute(delete(LoginToken).where(LoginToken.username == username))
    audit(session, me, "user.switched_on" if body.active else "user.switched_off", f"user {username}")
    session.commit()
    return user_out(user)
