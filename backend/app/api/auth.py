"""Auth API — magic link (join by invitation email) + session me."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import create_magic_link, get_user_by_ws_token, redeem_magic_link, send_magic_email
from app.config import get_settings
from app.db import get_db
from app.models.db import STEP_FUNCTIONS_RU, StepLevel, User, as_utc

router = APIRouter(prefix="/api/auth", tags=["auth"])
settings = get_settings()


class RequestLinkIn(BaseModel):
    email: str = Field(min_length=5, max_length=255)


class VerifyIn(BaseModel):
    token: str = Field(min_length=10)


class PatchMe(BaseModel):
    display_name: str | None = None
    step_level: StepLevel | None = None


def user_dict(u: User) -> dict:
    return {
        "id": u.id, "email": u.email, "display_name": u.display_name,
        "role": u.role.value, "step_level": u.step_level.value,
        "step_function": STEP_FUNCTIONS_RU.get(u.step_level, ""),
        "tokens_balance": u.tokens_balance, "created_at": u.created_at,
    }


@router.get("/steps")
async def steps():
    """Ступени Гурджиева — оптика участника. Менять можно раз в сутки."""
    return [{"level": s.value, "function": f} for s, f in STEP_FUNCTIONS_RU.items() if s != StepLevel.ai]


@router.post("/request-link")
async def request_link(body: RequestLinkIn, db: AsyncSession = Depends(get_db)):
    try:
        token, exists = await create_magic_link(db, body.email)
    except ValueError as e:
        raise HTTPException(400, str(e))
    link = f"{settings.base_url}/verify?token={token}"
    sent = send_magic_email(body.email, link)
    resp = {"sent": sent, "new_user": not exists}
    if not sent:  # dev mode: no SMTP configured — surface the link instead of hiding it
        resp["dev_link"] = link
    return resp


@router.post("/verify")
async def verify(body: VerifyIn, db: AsyncSession = Depends(get_db)):
    res = await redeem_magic_link(db, body.token)
    if res is None:
        raise HTTPException(401, "Ссылка недействительна или истекла. Запроси новую.")
    user, sess = res
    return {"token": sess.ws_token, "user": user_dict(user)}


async def current_user(x_session_token: str = Header(default=""), db: AsyncSession = Depends(get_db)) -> User:
    if not x_session_token:
        raise HTTPException(401, "Нет сессии. Войди по ссылке.")
    res = await get_user_by_ws_token(db, x_session_token)
    if res is None:
        raise HTTPException(401, "Сессия истекла. Запроси новую ссылку.")
    return res[0]


@router.get("/me")
async def me(user: User = Depends(current_user)):
    return user_dict(user)


@router.patch("/me")
async def patch_me(body: PatchMe, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    from datetime import timedelta
    from app.models.db import utcnow
    if body.display_name is not None:
        user.display_name = body.display_name[:120]
    if body.step_level is not None and body.step_level != user.step_level:
        if body.step_level == StepLevel.ai:
            raise HTTPException(403, "Ступень ИИ занята. Он соединяет — не пишет.")
        if user.step_changed_at and as_utc(user.step_changed_at) > utcnow() - timedelta(hours=24):
            raise HTTPException(429, "Ступень меняется раз в сутки. Иначе — хаос.")
        user.step_level = body.step_level
        user.step_changed_at = utcnow()
    await db.commit()
    return user_dict(user)
