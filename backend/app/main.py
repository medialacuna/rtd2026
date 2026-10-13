"""RTD.MUAR backend entrypoint — FastAPI + WebSocket realtime.

Run dev:   uvicorn app.main:app --reload --port 8000
Run prod:  docker compose up (see docker-compose.yml)
"""
from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import acts, admin, ai, auth, plays, replicas, scenes, stage
from app.auth import get_user_by_ws_token
from app.config import get_settings
from app.db import get_db, init_db
from app.import_komarovo import import_komarovo
from app.seed import seed_knowledge
from app.ws.hub import hub

log = logging.getLogger("rtd.main")
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    from app.db import SessionLocal
    async with SessionLocal() as db:
        n = await seed_knowledge(db)
        if n:
            log.info("knowledge base seeded: %d fragments", n)
        try:
            k = await import_komarovo(db)
            if k["plays"]:
                log.info("komarovo plays imported: %s", k)
        except Exception:  # noqa: BLE001
            log.exception("komarovo import failed")
    yield


app = FastAPI(title="RTD.MUAR — Real Time Drama", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.base_url, "http://localhost:5173", "http://localhost:3000", "*"],
    allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(replicas.router)
app.include_router(scenes.router)
app.include_router(acts.router)
app.include_router(admin.router)
app.include_router(plays.router)
app.include_router(stage.router)
app.include_router(ai.router)


@app.get("/api/health")
async def health(db: AsyncSession = Depends(get_db)):
    from app.ai.llama_client import get_client
    from app.ai.maturity import compute_maturity
    alive = await (await get_client()).is_alive()
    m = await compute_maturity(db)
    return {"ok": True, "ollama": alive, "model": settings.ollama_model,
            "online_ws": hub.online, "maturity_score": m["maturity_score"]}


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket, token: str = "", db: AsyncSession = Depends(get_db)):
    """Realtime поток: replica:new / scene:new / scene:update / scene:day / stage:event.

    Подключение: ws://host/ws?token=<session token>. Без токена — read-only наблюдение
    (пул открыт всем вошедшим; сцена — тоже публична).
    """
    await ws.accept()
    user = None
    if token:
        res = await get_user_by_ws_token(db, token)
        if res:
            user = res[0]
    await hub.join(ws)
    await ws.send_text(json.dumps({"event": "hello", "data": {
        "authenticated": user is not None,
        "user_id": user.id if user else None,
        "step_level": user.step_level.value if user else None,
        "online": hub.online,
    }}, ensure_ascii=False))
    try:
        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue
            etype = msg.get("type")
            if etype == "ping":
                await ws.send_text(json.dumps({"event": "pong"}))
            elif etype == "replica:new" and user is not None:
                # WS-native path (Module 5): same pipeline as REST POST
                from app.api.replicas import create_replica, ReplicaIn
                try:
                    result = await create_replica(
                        ReplicaIn(text=msg.get("text", ""), is_tost=bool(msg.get("is_tost"))),
                        user=user, db=db,
                    )
                    await ws.send_text(json.dumps({"event": "replica:accepted", "data": result},
                                                  default=str, ensure_ascii=False))
                except Exception as e:  # noqa: BLE001
                    detail = getattr(e, "detail", str(e))
                    await ws.send_text(json.dumps({"event": "error", "data": {"detail": detail}}, ensure_ascii=False))
            else:
                await ws.send_text(json.dumps({"event": "error", "data": {"detail": f"неизвестный тип: {etype}"}}))
    except WebSocketDisconnect:
        pass
    finally:
        await hub.leave(ws)
