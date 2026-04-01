from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import Any

from telethon import TelegramClient, events

from raidbot.models import IncomingMessage


def event_to_incoming_message(event) -> IncomingMessage:
    return IncomingMessage(
        chat_id=event.chat_id,
        sender_id=event.sender_id,
        text=event.raw_text or "",
        has_video=bool(getattr(event, "video", None)),
    )


class TelegramRaidListener:
    def __init__(
        self,
        api_id: int,
        api_hash: str,
        session_path: str,
        on_message: Callable[[IncomingMessage], Any],
        on_connection_state_change: Callable[[str], Any] | None = None,
    ) -> None:
        self.client = TelegramClient(session_path, api_id, api_hash)
        self.on_message = on_message
        self.on_connection_state_change = on_connection_state_change

    async def _handle_new_message(self, event) -> None:
        result = self.on_message(event_to_incoming_message(event))
        if inspect.isawaitable(result):
            await result

    async def _notify_connection_state_change(self, state: str) -> None:
        if self.on_connection_state_change is None:
            return
        result = self.on_connection_state_change(state)
        if inspect.isawaitable(result):
            await result

    async def stop(self) -> None:
        await self.client.disconnect()

    async def run_forever(self) -> None:
        @self.client.on(events.NewMessage(incoming=True))
        async def _handle(event) -> None:
            await self._handle_new_message(event)

        await self._notify_connection_state_change("connecting")
        try:
            await self.client.start()
            await self._notify_connection_state_change("connected")
            await self.client.run_until_disconnected()
        finally:
            await self._notify_connection_state_change("disconnected")
