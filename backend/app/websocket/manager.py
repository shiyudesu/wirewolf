"""WebSocket 连接管理器 — 支持多游戏房间广播."""

from __future__ import annotations

import json
import asyncio
from typing import Dict, List

from fastapi import WebSocket


class GameWatchManager:
    """管理观战 WebSocket 连接，按游戏房间分组."""

    def __init__(self) -> None:
        # game_id -> list[WebSocket]
        self.active_connections: Dict[str, List[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket, game_id: str) -> None:
        await websocket.accept()
        async with self._lock:
            if game_id not in self.active_connections:
                self.active_connections[game_id] = []
            self.active_connections[game_id].append(websocket)

    async def disconnect(self, websocket: WebSocket, game_id: str) -> None:
        async with self._lock:
            if game_id in self.active_connections:
                if websocket in self.active_connections[game_id]:
                    self.active_connections[game_id].remove(websocket)
                if not self.active_connections[game_id]:
                    del self.active_connections[game_id]

    async def broadcast(self, game_id: str, message: dict) -> None:
        """向指定游戏的所有观战者广播消息."""
        async with self._lock:
            connections = self.active_connections.get(game_id, []).copy()

        if not connections:
            return

        payload = json.dumps(message, ensure_ascii=False)
        dead: List[WebSocket] = []

        for ws in connections:
            try:
                await ws.send_text(payload)
            except Exception:
                dead.append(ws)

        # 清理断开的连接
        if dead:
            async with self._lock:
                for ws in dead:
                    if ws in self.active_connections.get(game_id, []):
                        self.active_connections[game_id].remove(ws)

    async def broadcast_to_all(self, message: dict) -> None:
        """向所有观战者广播（用于全局事件）."""
        async with self._lock:
            all_connections = [
                ws for conns in self.active_connections.values() for ws in conns
            ]

        payload = json.dumps(message, ensure_ascii=False)
        dead: List[WebSocket] = []

        for ws in all_connections:
            try:
                await ws.send_text(payload)
            except Exception:
                dead.append(ws)

        # 清理（简化：从所有房间中移除）
        if dead:
            async with self._lock:
                for game_id, conns in self.active_connections.items():
                    for ws in dead:
                        if ws in conns:
                            conns.remove(ws)


# 全局单例
watch_manager = GameWatchManager()
