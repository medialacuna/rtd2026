"""RTD.MUAR — SQLAlchemy models.

Mirrors the spec schema:
users, replicas, scenes, acts, plays, ai_memory, sessions
+ magic_links, fragments (RAG chunks), reactions (resonance counting).
"""
from __future__ import annotations

import enum
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean, DateTime, Enum as SAEnum, Float, ForeignKey, Integer, String, Text, JSON,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def as_utc(dt: datetime) -> datetime:
    """SQLite/Postgres drivers may hand back naive datetimes; treat them as UTC."""
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


class Base(DeclarativeBase):
    pass


class StepLevel(str, enum.Enum):
    """Ступени по Гурджиеву — оптика участника (не персонаж)."""
    ordinary_idiot = "ordinary_idiot"          # Обычный идиот: пишет факты. «Что я вижу»
    subjective = "subjective"                  # Субъективный: пишет сомнения. «Что я не понимаю»
    zigzag = "zigzag"                          # Зигзагообразный: пишет переходы. «Откуда и куда»
    enlightened = "enlightened"                # Просветлённый: пишет тосты. «За что выпьем»
    unique = "unique"                          # Уникальный: наблюдает, редко — но точно
    ai = "ai"                                  # ИИ: соединяет, показывает муар, задаёт вопросы


STEP_FUNCTIONS_RU = {
    StepLevel.ordinary_idiot: "Пишет факты. «Что я вижу»",
    StepLevel.subjective: "Пишет сомнения. «Что я не понимаю»",
    StepLevel.zigzag: "Пишет переходы. «Откуда и куда»",
    StepLevel.enlightened: "Пишет тосты. «За что выпьем»",
    StepLevel.unique: "Наблюдает. Почти не пишет. Редко — но точно",
    StepLevel.ai: "Соединяет. Показывает муар. Задаёт вопросы",
}


class UserRole(str, enum.Enum):
    participant = "participant"
    author = "author"        # может предлагать тексты на голосование
    admin = "admin"


class Section(str, enum.Enum):
    """Четыре раздела знания + пул реплик."""
    lestnica = "lestnica"    # Лестница (Гурджиев)
    genesis = "genesis"      # Генезис (7 сдвигов)
    theories = "theories"    # Фристон, Галлагер, Нортофф, Варела, Прибрам
    muar = "muar"            # Муар: давление света, изомеры, полисингулярность
    replicas = "replicas"    # пул реплик участников (для RAG по живому материалу)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(120), default="")
    role: Mapped[UserRole] = mapped_column(SAEnum(UserRole), default=UserRole.participant)
    step_level: Mapped[StepLevel] = mapped_column(SAEnum(StepLevel), default=StepLevel.ordinary_idiot)
    step_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    tokens_balance: Mapped[int] = mapped_column(Integer, default=0)  # Heartwins
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    replicas: Mapped[list["Replica"]] = relationship(back_populates="user")


class MagicLink(Base):
    """Одноразовая ссылка для входа по email (аналог OTP-токена)."""
    __tablename__ = "magic_links"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(255), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    ws_token: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    user: Mapped[User] = relationship()


class Replica(Base):
    __tablename__ = "replicas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    text: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list[float]] = mapped_column(JSON)   # prod: pgvector column
    step_level: Mapped[StepLevel] = mapped_column(SAEnum(StepLevel))
    is_tost: Mapped[bool] = mapped_column(Boolean, default=False)  # ритуальный тост такта
    intensity: Mapped[float] = mapped_column(Float, default=0.0)
    scene_id: Mapped[int | None] = mapped_column(ForeignKey("scenes.id"), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)

    user: Mapped[User] = relationship(back_populates="replicas")
    scenes_a: Mapped[list["Scene"]] = relationship(foreign_keys="Scene.replica_a_id", back_populates="replica_a")
    scenes_b: Mapped[list["Scene"]] = relationship(foreign_keys="Scene.replica_b_id", back_populates="replica_b")


class Scene(Base):
    """Пара реплик + комментарий-вопрос ИИ. Рождается из муара."""
    __tablename__ = "scenes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    replica_a_id: Mapped[int] = mapped_column(ForeignKey("replicas.id"))
    replica_b_id: Mapped[int] = mapped_column(ForeignKey("replicas.id"))
    ai_comment: Mapped[str] = mapped_column(Text, default="")     # всегда вопрос, не ответ
    semantic_distance: Mapped[float] = mapped_column(Float, default=0.0)
    coherence: Mapped[float] = mapped_column(Float, default=0.0)
    weight: Mapped[float] = mapped_column(Float, default=0.0, index=True)
    resonance: Mapped[int] = mapped_column(Integer, default=0)    # реакции участников рядом
    is_scene_of_day: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    hidden_for_step: Mapped[StepLevel | None] = mapped_column(SAEnum(StepLevel), nullable=True)  # таинство
    act_id: Mapped[int | None] = mapped_column(ForeignKey("acts.id"), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)

    replica_a: Mapped[Replica] = relationship(foreign_keys=[replica_a_id], back_populates="scenes_a")
    replica_b: Mapped[Replica] = relationship(foreign_keys=[replica_b_id], back_populates="scenes_b")
    act: Mapped["Act | None"] = relationship(back_populates="scenes")


class Act(Base):
    __tablename__ = "acts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(255))
    theme: Mapped[str] = mapped_column(String(120), default="")   # сезон: Свет/Кровь/Лестница/Вода
    season: Mapped[str] = mapped_column(String(40), default="")
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    scenes: Mapped[list[Scene]] = relationship(back_populates="act")


class Play(Base):
    """Загруженная пьеса/текст. После обработки фрагменты уходят в ChromaDB/коллекции."""
    __tablename__ = "plays"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(255))
    author: Mapped[str] = mapped_column(String(255), default="")
    section: Mapped[Section] = mapped_column(SAEnum(Section))
    content: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default="pending")  # pending|ingested|failed
    ingested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    uploaded_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    approved: Mapped[bool] = mapped_column(Boolean, default=True)  # автор-предложение -> DAO-голосование
    votes_for: Mapped[int] = mapped_column(Integer, default=0)
    votes_against: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Fragment(Base):
    """Чанк знания для RAG (локальная векторная база; в prod — ChromaDB/pgvector)."""
    __tablename__ = "fragments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    section: Mapped[Section] = mapped_column(SAEnum(Section), index=True)
    source: Mapped[str] = mapped_column(String(255))       # файл/пьеса/реплика
    chunk_index: Mapped[int] = mapped_column(Integer, default=0)
    content: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list[float]] = mapped_column(JSON)
    learned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AIMemory(Base):
    __tablename__ = "ai_memory"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    type: Mapped[str] = mapped_column(String(32), index=True)  # interaction|understood|not_understood|asked|digest
    content: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(255), default="")
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    learned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class Reaction(Base):
    """Не лайк. Участник отреагировал на сцену СВОЕЙ репликой рядом — это резонанс."""
    __tablename__ = "reactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    scene_id: Mapped[int] = mapped_column(ForeignKey("scenes.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    replica_id: Mapped[int | None] = mapped_column(ForeignKey("replicas.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Royalty(Base):
    """РоялтиHeartwins при постановке сцены: поровну между авторами реплик."""
    __tablename__ = "royalties"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    scene_id: Mapped[int] = mapped_column(ForeignKey("scenes.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    amount: Mapped[int] = mapped_column(Integer)
    note: Mapped[str] = mapped_column(String(255), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class StageEvent(Base):
    """Журнал Stage Mode: разделы, вопросы ИИ, данные зала (EEG/пульс)."""
    __tablename__ = "stage_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_key: Mapped[str] = mapped_column(String(64), index=True)
    kind: Mapped[str] = mapped_column(String(32))  # start|section|ai_line|audience|question|end
    section: Mapped[Section | None] = mapped_column(SAEnum(Section), nullable=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
