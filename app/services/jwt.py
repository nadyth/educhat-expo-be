import uuid

import jwt
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from app.config import settings

ALGORITHM = "HS256"


def create_access_token(user_id: uuid.UUID) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
    payload = {
        "sub": str(user_id),
        "type": "access",
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def create_refresh_token(user_id: uuid.UUID) -> tuple[str, str]:
    jti = str(uuid4())
    expire = datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_expire_days)
    payload = {
        "sub": str(user_id),
        "type": "refresh",
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "jti": jti,
    }
    token = jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)
    return token, jti


def decode_token(token: str) -> dict:
    return jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])