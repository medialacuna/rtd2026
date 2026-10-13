"""Magic-link auth + session tokens. No passwords: email is the key, invitation is the gate."""
from __future__ import annotations

import hashlib
import logging
import re
import smtplib
import secrets
from datetime import timedelta
from email.message import EmailMessage

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.db import MagicLink, Session, User, as_utc, utcnow

log = logging.getLogger("rtd.auth")
settings = get_settings()

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


async def create_magic_link(db: AsyncSession, email: str) -> tuple[str, bool]:
    """Returns (raw_token, user_exists). Token is single-use, TTL-bound."""
    email = email.strip().lower()
    if not EMAIL_RE.match(email):
        raise ValueError("Некорректный email")
    token = secrets.token_urlsafe(32)
    db.add(MagicLink(
        token_hash=_hash_token(token),
        email=email,
        expires_at=utcnow() + timedelta(hours=settings.magic_link_ttl_hours),
    ))
    await db.commit()
    exists = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none() is not None
    return token, exists


def send_magic_email(email: str, link: str) -> bool:
    """Send via SMTP if configured; otherwise log it (dev mode). Returns True if sent."""
    if not settings.smtp_host:
        log.info("MAGIC LINK (smtp not configured, dev mode): to=%s link=%s", email, link)
        return False
    msg = EmailMessage()
    msg["Subject"] = "RTD.MUAR — вход по ссылке"
    msg["From"] = settings.smtp_from
    msg["To"] = email
    msg.set_content(
        "Тебя приглашают в реальную драму в реальном времени.\n\n"
        f"Войти: {link}\n\n"
        "Ссылка одноразовая. Если ты не ждал это письмо — просто удали его.\n"
        "-- RTD.MUAR\n"
    )
    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as s:
            if settings.smtp_use_tls:
                s.starttls()
            if settings.smtp_user:
                s.login(settings.smtp_user, settings.smtp_password)
            s.send_message(msg)
        return True
    except Exception as e:  # noqa: BLE001
        log.error("smtp send failed: %s", e)
        return False


async def redeem_magic_link(db: AsyncSession, token: str) -> tuple[User, Session] | None:
    """Validate single-use token; create user on first login; open a session."""
    th = _hash_token(token)
    ml = (await db.execute(
        select(MagicLink).where(MagicLink.token_hash == th, MagicLink.used == False)  # noqa: E712
    )).scalar_one_or_none()
    if ml is None or as_utc(ml.expires_at) < utcnow():
        return None
    ml.used = True
    user = (await db.execute(select(User).where(User.email == ml.email))).scalar_one_or_none()
    if user is None:
        user = User(email=ml.email, display_name=ml.email.split("@")[0])
        db.add(user)
        await db.flush()
    ws_token = secrets.token_urlsafe(32)
    sess = Session(
        user_id=user.id,
        ws_token=ws_token,
        expires_at=utcnow() + timedelta(days=settings.session_ttl_days),
    )
    db.add(sess)
    await db.commit()
    return user, sess


async def get_user_by_ws_token(db: AsyncSession, ws_token: str) -> tuple[User, Session] | None:
    sess = (await db.execute(select(Session).where(Session.ws_token == ws_token))).scalar_one_or_none()
    if sess is None or as_utc(sess.expires_at) < utcnow():
        return None
    user = await db.get(User, sess.user_id)
    return user, sess
