"""WebSocket connection manager for real-time intraday push."""

from __future__ import annotations

import json
from typing import Any

from fastapi import WebSocket


class ConnectionManager:
    """Manages WebSocket connections and symbol subscriptions.

    Each connected client can subscribe to a set of symbols.  When new intraday
    data or scan results are available, the manager broadcasts updates to all
    clients subscribed to that symbol.
    """

    def __init__(self) -> None:
        self._connections: list[WebSocket] = []
        self._subscriptions: dict[WebSocket, set[str]] = {}

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self._connections.append(websocket)
        self._subscriptions[websocket] = set()

    def disconnect(self, websocket: WebSocket) -> None:
        if websocket in self._connections:
            self._connections.remove(websocket)
        self._subscriptions.pop(websocket, None)

    def subscribe(self, websocket: WebSocket, symbols: list[str]) -> None:
        if websocket in self._subscriptions:
            self._subscriptions[websocket].update(s.upper() for s in symbols)

    def unsubscribe(self, websocket: WebSocket, symbols: list[str]) -> None:
        if websocket in self._subscriptions:
            for s in symbols:
                self._subscriptions[websocket].discard(s.upper())

    def get_subscribers(self, symbol: str) -> list[WebSocket]:
        """Return all WebSocket connections subscribed to a given symbol."""
        upper = symbol.upper()
        return [ws for ws, subs in self._subscriptions.items() if upper in subs]

    async def broadcast_to_symbol(self, symbol: str, data: dict[str, Any]) -> None:
        """Send a message to all clients subscribed to a symbol."""
        message = json.dumps({"type": "intraday_update", "symbol": symbol.upper(), "data": data}, default=str)
        dead: list[WebSocket] = []
        for ws in self.get_subscribers(symbol):
            try:
                await ws.send_text(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)

    async def broadcast_all(self, data: dict[str, Any]) -> None:
        """Send a message to all connected clients."""
        message = json.dumps(data, default=str)
        dead: list[WebSocket] = []
        for ws in self._connections:
            try:
                await ws.send_text(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)

    @property
    def active_connections(self) -> int:
        return len(self._connections)
