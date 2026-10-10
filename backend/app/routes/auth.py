import re

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from ..db import get_session
from ..models import User
from ..schemas import (
    AuthResponse,
    LoginRequest,
    MeResponse,
    QuotaInfo,
    RegisterRequest,
    UserResponse,
)
from ..services.auth import create_token, get_current_user, hash_password, verify_password
from ..services.quota import get_quota_info

router = APIRouter()

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _to_user_response(user: User) -> UserResponse:
    return UserResponse(id=user.id, email=user.email, created_at=user.created_at)


@router.post("/api/auth/register", response_model=AuthResponse)
def register(req: RegisterRequest, session: Session = Depends(get_session)) -> AuthResponse:
    email = req.email.strip().lower()
    if not _EMAIL_RE.match(email):
        raise HTTPException(status_code=400, detail={"error": "邮箱格式不正确"})
    if len(req.password) < 8:
        raise HTTPException(status_code=400, detail={"error": "密码至少 8 位"})
    existing = session.exec(select(User).where(User.email == email)).first()
    if existing:
        raise HTTPException(status_code=409, detail={"error": "邮箱已注册"})
    user = User(email=email, password_hash=hash_password(req.password))
    session.add(user)
    session.commit()
    session.refresh(user)
    return AuthResponse(token=create_token(user.id), user=_to_user_response(user))


@router.post("/api/auth/login", response_model=AuthResponse)
def login(req: LoginRequest, session: Session = Depends(get_session)) -> AuthResponse:
    email = req.email.strip().lower()
    user = session.exec(select(User).where(User.email == email)).first()
    if not user or not verify_password(req.password, user.password_hash):
        raise HTTPException(status_code=401, detail={"error_type": "login_required", "error": "邮箱或密码错误"})
    return AuthResponse(token=create_token(user.id), user=_to_user_response(user))


@router.get("/api/auth/me", response_model=MeResponse)
def me(user: User = Depends(get_current_user), session: Session = Depends(get_session)) -> MeResponse:
    used, limit, date = get_quota_info(session, user.id)
    quota = QuotaInfo(
        date=date, limit=limit, used=used,
        remaining=None if limit is None else limit - used,
        unlimited=limit is None,
    )
    return MeResponse(user=_to_user_response(user), quota=quota)
