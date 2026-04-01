from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import pytest


class FakeEntity:
    def __init__(
        self,
        entity_id: int,
        *,
        username: str | None = None,
        first_name: str | None = None,
        title: str | None = None,
    ) -> None:
        self.id = entity_id
        self.username = username
        self.first_name = first_name
        self.title = title


@dataclass
class FakeDialog:
    id: int
    title: str
    is_user: bool = False


@dataclass
class FakeMessage:
    sender: FakeEntity | None

    sender_id: int | None = None

    async def get_sender(self):
        return self.sender


def _make_password_error() -> Exception:
    error_type = type("SessionPasswordNeededError", (Exception,), {})
    return error_type("password required")


class FakeClient:
    def __init__(self, session_path: str, api_id: int, api_hash: str, state: dict) -> None:
        self.session_path = session_path
        self.api_id = api_id
        self.api_hash = api_hash
        self.state = state
        self.connect_calls = 0
        self.disconnect_calls = 0
        self.send_code_requests: list[str] = []
        self.sign_in_calls: list[dict[str, str | None]] = []

    async def connect(self) -> None:
        self.connect_calls += 1
        connect_error = self.state.get("connect_error")
        if connect_error is not None:
            raise connect_error

    async def disconnect(self) -> None:
        self.disconnect_calls += 1
        self.state.setdefault("events", []).append("disconnect")

    async def is_user_authorized(self) -> bool:
        return self.state.get("authorized", False)

    async def send_code_request(self, phone_number: str) -> None:
        self.send_code_requests.append(phone_number)
        return self.state.get(
            "send_code_result",
            SimpleNamespace(phone_code_hash="test-phone-code-hash"),
        )

    async def get_entity(self, entry: str):
        entities = self.state.get("entities", {})
        if entry not in entities:
            raise ValueError(f"missing entity for {entry}")
        return entities[entry]

    async def sign_in(
        self,
        *,
        phone: str | None = None,
        code: str | None = None,
        password: str | None = None,
        phone_code_hash: str | None = None,
    ) -> None:
        self.sign_in_calls.append(
            {
                "phone": phone,
                "code": code,
                "password": password,
                "phone_code_hash": phone_code_hash,
            }
        )
        if password is not None:
            expected_password = self.state.get("expected_password")
            if expected_password is not None and password != expected_password:
                raise RuntimeError("bad password")
            self.state["authorized"] = True
            return

        if self.state.get("require_phone_code_hash") and phone_code_hash != self.state.get(
            "expected_phone_code_hash",
            "test-phone-code-hash",
        ):
            raise RuntimeError("You also need to provide a phone_code_hash.")

        sign_in_error = self.state.get("sign_in_error")
        if sign_in_error is not None:
            raise sign_in_error

        if self.state.get("require_password"):
            raise _make_password_error()

        self.state["authorized"] = True

    async def iter_dialogs(self):
        for dialog in self.state.get("dialogs", []):
            yield dialog

    async def iter_messages(self, chat_id: int, *, limit: int):
        for message in self.state.get("messages", {}).get(chat_id, [])[:limit]:
            yield message


def build_client_factory(state: dict):
    def factory(session_path: str, api_id: int, api_hash: str) -> FakeClient:
        client = FakeClient(session_path, api_id, api_hash, state)
        state.setdefault("clients", []).append(client)
        return client

    return factory


def _write_session_artifacts(session_file: Path, content: str = "session") -> None:
    session_file.write_text(content, encoding="utf-8")
    for suffix in ("-journal", "-wal", "-shm"):
        (session_file.parent / f"{session_file.name}{suffix}").write_text(content, encoding="utf-8")


def test_detect_raidar_candidates_recognizes_supported_exact_usernames_and_names() -> None:
    from raidbot.desktop.telegram_setup import detect_raidar_candidates

    candidates = detect_raidar_candidates(
        [
            FakeEntity(10, username="DelugeRaidBot"),
            FakeEntity(20, first_name="d.raidbot"),
            FakeEntity(30, title="raidar"),
            FakeEntity(40, username="not-raidar", first_name="Raidar Alt"),
        ]
    )

    assert [candidate.entity_id for candidate in candidates] == [10, 20, 30]
    assert [candidate.label for candidate in candidates] == ["@DelugeRaidBot", "d.raidbot", "raidar"]


def test_detect_raidar_candidates_falls_back_to_display_name() -> None:
    from raidbot.desktop.telegram_setup import detect_raidar_candidates

    candidates = detect_raidar_candidates([FakeEntity(20, first_name="Raidar")])

    assert [candidate.entity_id for candidate in candidates] == [20]
    assert candidates[0].label == "Raidar"


@pytest.mark.asyncio
async def test_authorize_reuses_existing_session_without_prompting(tmp_path: Path) -> None:
    from raidbot.desktop.telegram_setup import SessionStatus, TelegramSetupService

    state = {"authorized": True}
    service = TelegramSetupService(
        api_id=123456,
        api_hash="hash-value",
        session_path=tmp_path / "raidbot.session",
        client_factory=build_client_factory(state),
    )

    async def fail_callback() -> str:
        raise AssertionError("callback should not run")

    status = await service.authorize(
        phone_number_callback=fail_callback,
        code_callback=fail_callback,
        password_callback=fail_callback,
    )

    assert status is SessionStatus.authorized
    assert len(state["clients"]) == 1
    assert state["clients"][0].connect_calls == 1
    assert state["clients"][0].disconnect_calls == 1
    assert state["clients"][0].send_code_requests == []


@pytest.mark.asyncio
async def test_request_code_sends_telegram_code_without_sign_in(tmp_path: Path) -> None:
    from raidbot.desktop.telegram_setup import SessionStatus, TelegramSetupService

    state = {"authorized": False}
    service = TelegramSetupService(
        api_id=123456,
        api_hash="hash-value",
        session_path=tmp_path / "raidbot.session",
        client_factory=build_client_factory(state),
    )

    status = await service.request_code("+15555550123")

    assert status is SessionStatus.authorization_required
    client = state["clients"][0]
    assert client.send_code_requests == ["+15555550123"]
    assert client.sign_in_calls == []


@pytest.mark.asyncio
async def test_authorize_reuses_phone_code_hash_from_request_code(tmp_path: Path) -> None:
    from raidbot.desktop.telegram_setup import SessionStatus, TelegramSetupService

    state = {
        "authorized": False,
        "require_phone_code_hash": True,
        "expected_phone_code_hash": "hash-123",
        "send_code_result": SimpleNamespace(phone_code_hash="hash-123"),
    }
    service = TelegramSetupService(
        api_id=123456,
        api_hash="hash-value",
        session_path=tmp_path / "raidbot.session",
        client_factory=build_client_factory(state),
    )

    request_status = await service.request_code("+15555550123")

    async def phone_number_callback() -> str:
        return "+15555550123"

    async def code_callback() -> str:
        return "12345"

    authorize_status = await service.authorize(
        phone_number_callback=phone_number_callback,
        code_callback=code_callback,
    )

    assert request_status is SessionStatus.authorization_required
    assert authorize_status is SessionStatus.authorized
    assert state["clients"][-1].sign_in_calls == [
        {
            "phone": "+15555550123",
            "code": "12345",
            "password": None,
            "phone_code_hash": "hash-123",
        }
    ]


@pytest.mark.asyncio
async def test_resolve_sender_entry_returns_entity_id(tmp_path: Path) -> None:
    from raidbot.desktop.telegram_setup import TelegramSetupService

    session_path = tmp_path / "raidbot.session"
    _write_session_artifacts(session_path)
    state = {
        "authorized": True,
        "entities": {
            "@raidar": FakeEntity(77, username="raidar"),
        },
    }
    service = TelegramSetupService(
        api_id=123456,
        api_hash="hash-value",
        session_path=session_path,
        client_factory=build_client_factory(state),
    )

    entity_id = await service.resolve_sender_entry("@raidar")

    assert entity_id == 77
    assert state["clients"][0].session_path != str(session_path)


@pytest.mark.asyncio
async def test_resolve_sender_entry_details_returns_id_and_canonical_label(tmp_path: Path) -> None:
    from raidbot.desktop.telegram_setup import TelegramSetupService

    session_path = tmp_path / "raidbot.session"
    _write_session_artifacts(session_path)
    state = {
        "authorized": True,
        "entities": {
            "5349287105": FakeEntity(5349287105, username="RallyGuard_Raid_Bot"),
        },
    }
    service = TelegramSetupService(
        api_id=123456,
        api_hash="hash-value",
        session_path=session_path,
        client_factory=build_client_factory(state),
    )

    resolved = await service.resolve_sender_entry_details("5349287105")

    assert resolved.entity_id == 5349287105
    assert resolved.label == "@RallyGuard_Raid_Bot"
    assert state["clients"][0].session_path != str(session_path)


@pytest.mark.asyncio
async def test_authorize_handles_code_and_password_flow(tmp_path: Path) -> None:
    from raidbot.desktop.telegram_setup import SessionStatus, TelegramSetupService

    state = {
        "authorized": False,
        "require_password": True,
        "expected_password": "hunter2",
    }
    service = TelegramSetupService(
        api_id=123456,
        api_hash="hash-value",
        session_path=tmp_path / "raidbot.session",
        client_factory=build_client_factory(state),
    )

    async def phone_number_callback() -> str:
        return "+15555550123"

    async def code_callback() -> str:
        return "12345"

    async def password_callback() -> str:
        return "hunter2"

    status = await service.authorize(
        phone_number_callback=phone_number_callback,
        code_callback=code_callback,
        password_callback=password_callback,
    )

    assert status is SessionStatus.authorized
    client = state["clients"][0]
    assert client.send_code_requests == ["+15555550123"]
    assert client.sign_in_calls == [
        {
            "phone": "+15555550123",
            "code": "12345",
            "password": None,
            "phone_code_hash": "test-phone-code-hash",
        },
        {
            "phone": None,
            "code": None,
            "password": "hunter2",
            "phone_code_hash": None,
        },
    ]


@pytest.mark.asyncio
async def test_authorize_cleans_up_incomplete_session_on_failure(tmp_path: Path) -> None:
    from raidbot.desktop.telegram_setup import TelegramSetupService

    session_path = tmp_path / "raidbot.session"
    _write_session_artifacts(session_path, content="stale")
    state = {
        "authorized": False,
        "sign_in_error": RuntimeError("bad code"),
    }
    service = TelegramSetupService(
        api_id=123456,
        api_hash="hash-value",
        session_path=session_path,
        client_factory=build_client_factory(state),
    )

    async def phone_number_callback() -> str:
        return "+15555550123"

    async def code_callback() -> str:
        return "99999"

    with pytest.raises(RuntimeError, match="bad code"):
        await service.authorize(
            phone_number_callback=phone_number_callback,
            code_callback=code_callback,
        )

    assert session_path.exists() is False
    assert (tmp_path / "raidbot.session-journal").exists() is False


@pytest.mark.asyncio
async def test_authorize_disconnects_before_cleanup_on_failure(tmp_path: Path) -> None:
    from raidbot.desktop.telegram_setup import TelegramSetupService

    state = {
        "authorized": False,
        "sign_in_error": RuntimeError("bad code"),
    }
    service = TelegramSetupService(
        api_id=123456,
        api_hash="hash-value",
        session_path=tmp_path / "raidbot.session",
        client_factory=build_client_factory(state),
    )
    event_log: list[str] = state.setdefault("events", [])
    service._remove_session_files = lambda: event_log.append("cleanup")

    async def phone_number_callback() -> str:
        return "+15555550123"

    async def code_callback() -> str:
        return "99999"

    with pytest.raises(RuntimeError, match="bad code"):
        await service.authorize(
            phone_number_callback=phone_number_callback,
            code_callback=code_callback,
        )

    assert event_log == ["disconnect", "cleanup"]


@pytest.mark.asyncio
async def test_authorize_cleans_up_bare_session_name_artifacts_on_failure(tmp_path: Path) -> None:
    from raidbot.desktop.telegram_setup import TelegramSetupService

    session_path = tmp_path / "raidbot"
    real_session_file = tmp_path / "raidbot.session"
    _write_session_artifacts(real_session_file, content="stale")
    state = {
        "authorized": False,
        "sign_in_error": RuntimeError("bad code"),
    }
    service = TelegramSetupService(
        api_id=123456,
        api_hash="hash-value",
        session_path=session_path,
        client_factory=build_client_factory(state),
    )

    async def phone_number_callback() -> str:
        return "+15555550123"

    async def code_callback() -> str:
        return "99999"

    with pytest.raises(RuntimeError, match="bad code"):
        await service.authorize(
            phone_number_callback=phone_number_callback,
            code_callback=code_callback,
        )

    assert real_session_file.exists() is False
    assert (tmp_path / "raidbot.session-journal").exists() is False
    assert (tmp_path / "raidbot.session-wal").exists() is False
    assert (tmp_path / "raidbot.session-shm").exists() is False


@pytest.mark.asyncio
async def test_authorize_keeps_existing_session_when_connect_fails(tmp_path: Path) -> None:
    from raidbot.desktop.telegram_setup import TelegramSetupService

    session_path = tmp_path / "raidbot.session"
    session_path.write_text("valid-session", encoding="utf-8")
    state = {
        "connect_error": RuntimeError("offline"),
    }
    service = TelegramSetupService(
        api_id=123456,
        api_hash="hash-value",
        session_path=session_path,
        client_factory=build_client_factory(state),
    )

    async def phone_number_callback() -> str:
        return "+15555550123"

    async def code_callback() -> str:
        return "11111"

    with pytest.raises(RuntimeError, match="offline"):
        await service.authorize(
            phone_number_callback=phone_number_callback,
            code_callback=code_callback,
        )

    assert session_path.exists() is True


@pytest.mark.asyncio
async def test_reauthorize_replaces_session_and_reports_status(tmp_path: Path) -> None:
    from raidbot.desktop.telegram_setup import SessionStatus, TelegramSetupService

    session_path = tmp_path / "raidbot.session"
    _write_session_artifacts(session_path, content="old-session")
    state = {"authorized": False}
    service = TelegramSetupService(
        api_id=123456,
        api_hash="hash-value",
        session_path=session_path,
        client_factory=build_client_factory(state),
    )

    async def phone_number_callback() -> str:
        return "+15555550123"

    async def code_callback() -> str:
        return "11111"

    assert await service.get_session_status() is SessionStatus.authorization_required
    status = await service.reauthorize(
        phone_number_callback=phone_number_callback,
        code_callback=code_callback,
    )

    assert status is SessionStatus.authorized
    assert session_path.exists() is False


@pytest.mark.asyncio
async def test_reauthorize_restores_existing_session_when_replacement_fails(tmp_path: Path) -> None:
    from raidbot.desktop.telegram_setup import TelegramSetupService

    session_path = tmp_path / "raidbot"
    real_session_file = tmp_path / "raidbot.session"
    _write_session_artifacts(real_session_file, content="old-session")
    state = {
        "authorized": False,
        "sign_in_error": RuntimeError("replacement failed"),
    }
    service = TelegramSetupService(
        api_id=123456,
        api_hash="hash-value",
        session_path=session_path,
        client_factory=build_client_factory(state),
    )

    async def phone_number_callback() -> str:
        return "+15555550123"

    async def code_callback() -> str:
        return "11111"

    with pytest.raises(RuntimeError, match="replacement failed"):
        await service.reauthorize(
            phone_number_callback=phone_number_callback,
            code_callback=code_callback,
        )

    assert real_session_file.exists() is True
    assert real_session_file.read_text(encoding="utf-8") == "old-session"
    assert (tmp_path / "raidbot.session-journal").exists() is True
    assert (tmp_path / "raidbot.session-wal").exists() is True
    assert (tmp_path / "raidbot.session-shm").exists() is True


@pytest.mark.asyncio
async def test_list_accessible_chats_and_infer_recent_sender_candidates(tmp_path: Path) -> None:
    from raidbot.desktop.telegram_setup import SessionStatus, TelegramSetupService

    raidar = FakeEntity(10, username="raidar")
    someone_else = FakeEntity(20, first_name="Alice")
    state = {
        "authorized": True,
        "dialogs": [
            FakeDialog(id=2002, title="Beta Room"),
            FakeDialog(id=1001, title="Alpha Room"),
            FakeDialog(id=9000, title="Direct DM", is_user=True),
        ],
        "messages": {
            1001: [FakeMessage(sender=someone_else), FakeMessage(sender=raidar)],
            2002: [FakeMessage(sender=someone_else)],
        },
    }
    service = TelegramSetupService(
        api_id=123456,
        api_hash="hash-value",
        session_path=tmp_path / "raidbot.session",
        client_factory=build_client_factory(state),
    )

    assert await service.get_session_status() is SessionStatus.authorized

    chats = await service.list_accessible_chats()
    candidates = await service.infer_recent_sender_candidates([1001, 2002])

    assert [(chat.chat_id, chat.title) for chat in chats] == [
        (1001, "Alpha Room"),
        (2002, "Beta Room"),
    ]
    assert [candidate.entity_id for candidate in candidates] == [10, 20]
    assert [candidate.label for candidate in candidates] == ["@raidar", "Alice"]


@pytest.mark.asyncio
async def test_infer_recent_sender_candidates_prefers_supported_exact_bot_matches(tmp_path: Path) -> None:
    from raidbot.desktop.telegram_setup import TelegramSetupService

    supported_bot = FakeEntity(10, username="delugeraidbot")
    other_supported_bot = FakeEntity(30, first_name="d.raidbot")
    frequent_sender = FakeEntity(20, first_name="Alice")
    state = {
        "authorized": True,
        "messages": {
            1001: [
                FakeMessage(sender=frequent_sender),
                FakeMessage(sender=frequent_sender),
                FakeMessage(sender=supported_bot),
                FakeMessage(sender=frequent_sender),
                FakeMessage(sender=other_supported_bot),
            ],
        },
    }
    service = TelegramSetupService(
        api_id=123456,
        api_hash="hash-value",
        session_path=tmp_path / "raidbot.session",
        client_factory=build_client_factory(state),
    )

    candidates = await service.infer_recent_sender_candidates([1001])

    assert [candidate.entity_id for candidate in candidates] == [10, 30, 20]
    assert [candidate.label for candidate in candidates] == ["@delugeraidbot", "d.raidbot", "Alice"]


@pytest.mark.asyncio
async def test_infer_recent_sender_candidates_uses_runtime_sender_id_with_resolved_label(
    tmp_path: Path,
) -> None:
    from raidbot.desktop.telegram_setup import TelegramSetupService

    resolved_sender = FakeEntity(7022354529, username="RallyGuard_Raid_Bot")
    state = {
        "authorized": True,
        "messages": {
            1001: [
                FakeMessage(sender=resolved_sender, sender_id=5349287105),
            ],
        },
    }
    service = TelegramSetupService(
        api_id=123456,
        api_hash="hash-value",
        session_path=tmp_path / "raidbot.session",
        client_factory=build_client_factory(state),
    )

    candidates = await service.infer_recent_sender_candidates([1001])

    assert [candidate.entity_id for candidate in candidates] == [5349287105]
    assert [candidate.label for candidate in candidates] == ["@RallyGuard_Raid_Bot"]
