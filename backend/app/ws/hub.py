"""In-process realtime hub (WebSocket fan-out).

Prod note: with multiple backend replicas put this behind Redis pub/sub
(docker-compose already ships redis; set REDIS_URL and swap Hub.publish
for an rpubsub broadcast — interface stays identical).
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone

from fastapi import WebSocket

log = logging.getLogger("rtd.ws")


def _default(o):
    if isinstance(o, datetime):
        return o.isoformat()
    raise TypeError(f"not serializable: {type(o)}")


class Hub:
    def __init__(self) -> None:
        self._clients: set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def join(self, ws: WebSocket) -> None:
        async with self._lock:
            self._clients.add(ws)

    async def leave(self, ws: WebSocket) -> None:
        async with self._lock:
            self._clients.discard(ws)

    @property
    def online(self) -> int:
        return len(self._clients)

    async def broadcast(self, event: str, data: dict | list) -> None:
        msg = json.dumps(
            {"event": event, "data": data, "ts": datetime.now(timezone.utc).isoformat()},
            default=_default, ensure_ascii=False,
        )
        dead = []
        for ws in list(self._clients):
            try:
                await ws.send_text(msg)
            except Exception:  # noqa: BLE001
                dead.append(ws)
        if dead:
            async with self._lock:
                for ws in dead:
                    self._clients.discard(ws)


hub = Hub()
