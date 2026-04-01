from __future__ import annotations

import asyncio
import importlib
import inspect
import sys
from types import ModuleType, SimpleNamespace


def load_telegram_client_module(monkeypatch):
    sys.modules.pop("raidbot.telegram_client", None)

    telethon_module = ModuleType("telethon")
    events_module = ModuleType("telethon.events")

    class FakeNewMessage:
        def __init__(self, *, incoming: bool) -> None:
            self.incoming = incoming

    class FakeTelegramClient:
        def __init__(self, session_path: str, api_id: int, api_hash: str) -> None:
            self.session_path = session_path
            self.api_id = api_id
            self.api_hash = api_hash
            self.registered_event = None
            self.handler = None
            self.start_calls = 0
            self.run_until_disconnected_calls = 0
            self.disconnect_calls = 0

        def on(self, event):
            self.registered_event = event

            def decorator(handler):
                self.handler = handler
                return handler

            return decorator

        async def start(self) -> None:
            self.start_calls += 1

        async def run_until_disconnected(self) -> None:
            self.run_until_disconnected_calls += 1

        async def disconnect(self) -> None:
            self.disconnect_calls += 1

    telethon_module.TelegramClient = FakeTelegramClient
    events_module.NewMessage = FakeNewMessage
    telethon_module.events = events_module

    monkeypatch.setitem(sys.modules, "telethon", telethon_module)
    monkeypatch.setitem(sys.modules, "telethon.events", events_module)

    return importlib.import_module("raidbot.telegram_client")


def test_event_to_incoming_message_extracts_chat_sender_and_text(monkeypatch):
    telegram_client = load_telegram_client_module(monkeypatch)
    event = SimpleNamespace(
        chat_id=-1001,
        sender_id=42,
        raw_text="Likes\nhttps://x.com/i/status/123",
        video=None,
    )

    message = telegram_client.event_to_incoming_message(event)

    assert message.chat_id == -1001
    assert message.sender_id == 42
    assert message.text == "Likes\nhttps://x.com/i/status/123"
    assert message.has_video is False


def test_event_to_incoming_message_defaults_missing_text_to_empty_string(monkeypatch):
    telegram_client = load_telegram_client_module(monkeypatch)
    event = SimpleNamespace(chat_id=-1001, sender_id=42, raw_text=None, video=None)

    message = telegram_client.event_to_incoming_message(event)

    assert message.text == ""
    assert message.has_video is False


def test_event_to_incoming_message_marks_video_posts(monkeypatch):
    telegram_client = load_telegram_client_module(monkeypatch)
    event = SimpleNamespace(
        chat_id=-1001,
        sender_id=42,
        raw_text="raid text",
        video=object(),
    )

    message = telegram_client.event_to_incoming_message(event)

    assert message.has_video is True


def test_run_forever_registers_new_message_handler_and_awaits_async_callback(monkeypatch):
    async def scenario() -> None:
        telegram_client = load_telegram_client_module(monkeypatch)
        received_messages = []

        async def on_message(message) -> None:
            received_messages.append(message)

        listener = telegram_client.TelegramRaidListener(
            api_id=123456,
            api_hash="hash-value",
            session_path="raidbot.session",
            on_message=on_message,
        )

        await listener.run_forever()

        assert listener.client.session_path == "raidbot.session"
        assert listener.client.api_id == 123456
        assert listener.client.api_hash == "hash-value"
        assert listener.client.registered_event.incoming is True
        assert listener.client.start_calls == 1
        assert listener.client.run_until_disconnected_calls == 1
        assert inspect.iscoroutinefunction(listener.client.handler)

        event = SimpleNamespace(
            chat_id=-1001,
            sender_id=42,
            raw_text="raid text",
            video=object(),
        )
        await listener.client.handler(event)

        assert len(received_messages) == 1
        assert received_messages[0].chat_id == -1001
        assert received_messages[0].sender_id == 42
        assert received_messages[0].text == "raid text"
        assert received_messages[0].has_video is True

    asyncio.run(scenario())


def test_listener_stop_disconnects_client(monkeypatch):
    async def scenario() -> None:
        telegram_client = load_telegram_client_module(monkeypatch)
        listener = telegram_client.TelegramRaidListener(
            api_id=123456,
            api_hash="hash-value",
            session_path="raidbot.session",
            on_message=lambda _message: None,
        )

        await listener.stop()

        assert listener.client.disconnect_calls == 1

    asyncio.run(scenario())


def test_run_forever_reports_connection_state_changes(monkeypatch):
    async def scenario() -> None:
        telegram_client = load_telegram_client_module(monkeypatch)
        states = []
        listener = telegram_client.TelegramRaidListener(
            api_id=123456,
            api_hash="hash-value",
            session_path="raidbot.session",
            on_message=lambda _message: None,
            on_connection_state_change=states.append,
        )

        await listener.run_forever()

        assert states == ["connecting", "connected", "disconnected"]

    asyncio.run(scenario())
