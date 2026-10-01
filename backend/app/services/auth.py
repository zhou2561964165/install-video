"""认证服务：密码哈希（stdlib pbkdf2）+ JWT 签发/校验 + 用户依赖注入。

约束：只在路由层使用，不接触 yt-dlp，不接触下载核心。
"""
import hashlib
import hmac
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlmodel import Session

from ..config import settings
from ..db import get_session
from ..models import User

# 密码哈希格式：pbkdf2_sha256$<迭代次数>$<盐hex>$<派生hex>
# 迭代次数随哈希一起存，后续调高 PASSWORD_ITERATIONS 时旧哈希仍可校验。
_ALGO = "pbkdf2_sha256"


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, settings.password_iterations)
    return f"{_ALGO}${settings.password_iterations}${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, iter_s, salt_hex, dk_hex = stored.split("$")
        if algo != _ALGO:
            return False
        salt = bytes.fromhex(salt_hex)
        iterations = int(iter_s)
        dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
        return hmac.compare_digest(dk.hex(), dk_hex)
    except (ValueError, TypeError):
        return False


def create_token(user_id: str) -> str:
    payload = {
        "sub": user_id,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def decode_token(token: str) -> Optional[str]:
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
        return payload.get("sub")
    except jwt.PyJWTError:
        return None


# auto_error=False：无/坏 Authorization 头不抛 401，交由 get_current_user 决定
bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user_optional(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    session: Session = Depends(get_session),
) -> Optional[User]:
    """可选鉴权：无/坏 token → None（匿名放行），有效 token → User。"""
    if credentials is None:
        return None
    user_id = decode_token(credentials.credentials)
    if user_id is None:
        return None
    return session.get(User, user_id)


def get_current_user(
    user: Optional[User] = Depends(get_current_user_optional),
) -> User:
    """必需鉴权：无/坏 token → 401 login_required。"""
    if user is None:
        raise HTTPException(status_code=401, detail={"error_type": "login_required", "error": "需要登录"})
    return user
