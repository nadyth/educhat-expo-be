import hashlib
import uuid
from datetime import datetime, timedelta, timezone

import httpx
import jwt as pyjwt

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.dependencies.db import get_db
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.schemas.auth import (
    LogoutRequest,
    RefreshRequest,
    RefreshResponse,
    TokenRequest,
    TokenResponse,
)
from app.services.google import verify_google_token
from app.services.jwt import create_access_token, create_refresh_token, decode_token

router = APIRouter()


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


@router.post("/login", response_model=TokenResponse)
async def login(body: TokenRequest, db: AsyncSession = Depends(get_db)):
    if body.provider != "google":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Provider '{body.provider}' is not supported",
        )

    try:
        idinfo = await verify_google_token(body.token)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Google token",
        )

    google_id = idinfo["sub"]
    email = idinfo["email"]
    name = idinfo.get("name")
    picture = idinfo.get("picture")

    stmt = insert(User).values(
        google_id=google_id,
        email=email,
        name=name,
        picture_url=picture,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["google_id"],
        set_={
            "email": email,
            "name": name,
            "picture_url": picture,
            "updated_at": datetime.now(timezone.utc),
        },
    )
    result = await db.execute(stmt)
    await db.commit()

    user_result = await db.execute(select(User).where(User.google_id == google_id))
    user = user_result.scalar_one()

    access_token = create_access_token(user.id)
    refresh_token, _ = create_refresh_token(user.id)
    refresh_expire = datetime.now(timezone.utc) + timedelta(
        days=settings.refresh_token_expire_days
    )

    db_token = RefreshToken(
        token_hash=hash_token(refresh_token),
        user_id=user.id,
        expires_at=refresh_expire,
    )
    db.add(db_token)
    await db.commit()

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.access_token_expire_minutes * 60,
        user=user,
    )


@router.post("/refresh", response_model=RefreshResponse)
async def refresh(body: RefreshRequest, db: AsyncSession = Depends(get_db)):
    try:
        payload = decode_token(body.refresh_token)
    except pyjwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        )

    if payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not a refresh token",
        )

    token_hash = hash_token(body.refresh_token)
    result = await db.execute(
        select(RefreshToken).where(RefreshToken.token_hash == token_hash)
    )
    db_token = result.scalar_one_or_none()

    if db_token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token not found",
        )

    if db_token.revoked:
        # Reuse detection: revoke all tokens for this user
        all_tokens = await db.execute(
            select(RefreshToken).where(RefreshToken.user_id == db_token.user_id)
        )
        for t in all_tokens.scalars():
            t.revoked = True
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token has been revoked",
        )

    if db_token.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token expired",
        )

    # Rotate: revoke old, issue new
    db_token.revoked = True

    user_id = uuid.UUID(payload["sub"])
    access_token = create_access_token(user_id)
    new_refresh_token, _ = create_refresh_token(user_id)
    refresh_expire = datetime.now(timezone.utc) + timedelta(
        days=settings.refresh_token_expire_days
    )

    new_db_token = RefreshToken(
        token_hash=hash_token(new_refresh_token),
        user_id=user_id,
        expires_at=refresh_expire,
    )
    db.add(new_db_token)
    await db.commit()

    return RefreshResponse(
        access_token=access_token,
        refresh_token=new_refresh_token,
        expires_in=settings.access_token_expire_minutes * 60,
    )


@router.post("/logout")
async def logout(body: LogoutRequest, db: AsyncSession = Depends(get_db)):
    token_hash = hash_token(body.refresh_token)
    result = await db.execute(
        select(RefreshToken).where(RefreshToken.token_hash == token_hash)
    )
    db_token = result.scalar_one_or_none()

    if db_token is not None:
        db_token.revoked = True
        await db.commit()

    return {"message": "Logged out successfully"}


@router.get("/gen-google-auth", include_in_schema=False)
async def gen_google_auth(request: Request):
    if not settings.debug:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    redirect_uri = str(request.base_url) + "auth/gen-google-auth/callback"
    google_auth_url = (
        "https://accounts.google.com/o/oauth2/v2/auth?"
        + f"client_id={settings.google_client_id}"
        + f"&redirect_uri={redirect_uri}"
        + "&response_type=code"
        + "&scope=openid email profile"
        + "&access_type=offline"
        + "&prompt=consent"
    )
    return RedirectResponse(google_auth_url)


@router.get("/gen-google-auth/callback", include_in_schema=False)
async def gen_google_auth_callback(request: Request, code: str):
    if not settings.debug:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    redirect_uri = str(request.base_url) + "auth/gen-google-auth/callback"

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": code,
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            },
        )
    if resp.status_code != 200:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Failed to exchange authorization code: {resp.text}",
        )

    tokens = resp.json()
    id_token = tokens.get("id_token", "")

    html = f"""<!DOCTYPE html>
<html><head><title>Google ID Token</title>
<style>
  body {{ font-family: monospace; max-width: 700px; margin: 40px auto; padding: 0 20px; }}
  label {{ display: block; margin-top: 16px; font-weight: bold; }}
  textarea {{ width: 100%; height: 200px; font-family: monospace; font-size: 12px; }}
  .hint {{ background: #fff3cd; padding: 12px; border-radius: 6px; margin-top: 16px; }}
</style>
</head><body>
<h1>Google ID Token</h1>
<label>ID Token (copy this)</label>
<textarea id="it">{id_token}</textarea>
<div class="hint">
  <p><strong>Use this token to test POST /auth/login:</strong></p>
  <pre>curl -X POST http://localhost:8000/auth/login \\
  -H "Content-Type: application/json" \\
  -d '{{"provider": "google", "token": "&lt;paste above&gt;"}}'</pre>
</div>
</body></html>"""
    return HTMLResponse(html)


@router.get("/gen-token", include_in_schema=False)
async def gen_test_token(db: AsyncSession = Depends(get_db)):
    if not settings.debug:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    test_google_id = "test-local-user"
    test_email = "test@local.dev"
    test_name = "Test User"

    stmt = insert(User).values(
        google_id=test_google_id,
        email=test_email,
        name=test_name,
        picture_url=None,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["google_id"],
        set_={
            "email": test_email,
            "name": test_name,
            "updated_at": datetime.now(timezone.utc),
        },
    )
    await db.execute(stmt)
    await db.commit()

    result = await db.execute(select(User).where(User.google_id == test_google_id))
    user = result.scalar_one()

    access_token = create_access_token(user.id)
    refresh_token, _ = create_refresh_token(user.id)
    refresh_expire = datetime.now(timezone.utc) + timedelta(
        days=settings.refresh_token_expire_days
    )

    db_token = RefreshToken(
        token_hash=hash_token(refresh_token),
        user_id=user.id,
        expires_at=refresh_expire,
    )
    db.add(db_token)
    await db.commit()

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.access_token_expire_minutes * 60,
        user=user,
    )