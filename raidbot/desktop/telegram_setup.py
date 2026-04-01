from __future__ import annotations

from collections import Counter
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
import shutil
import tempfile
from typing import Any

from telethon import TelegramClient


@dataclass(frozen=True)
class AccessibleChat:
    chat_id: int
    title: str


@dataclass(frozen=True)
class RaidarCandidate:
    entity_id: int
    label: str


@dataclass(frozen=True)
class ResolvedSenderEntry:
    entity_id: int
    label: str


class SessionStatus(str, Enum):
    authorized = "authorized"
    authorization_required = "authorization_required"


PromptCallback = Callable[[], str | Awaitable[str]]
ClientFactory = Callable[[str, int, str], Any]
SUPPORTED_RAID_BOT_IDENTIFIERS = ("raidar", "delugeraidbot", "d.raidbot")


class TelegramSetupService:
    def __init__(
        self,
        api_id: int,
        api_hash: str,
        session_path: Path,
        client_factory: ClientFactory | None = None,
    ) -> None:
        self.api_id = api_id
        self.api_hash = api_hash
        self.session_path = session_path
        self.client_factory = client_factory or TelegramClient
        self._requested_phone_number: str | None = None
        self._phone_code_hash: str | None = None

    async def get_session_status(self) -> SessionStatus:
        client = self._create_client()
        authorized = False
        try:
            await client.connect()
            authorized = await client.is_user_authorized()
        finally:
            await _maybe_await(client.disconnect())
        if authorized:
            return SessionStatus.authorized
        return SessionStatus.authorization_required

    async def authorize(
        self,
        *,
        phone_number_callback: PromptCallback,
        code_callback: PromptCallback,
        password_callback: PromptCallback | None = None,
    ) -> SessionStatus:
        client = self._create_client()
        should_cleanup = False
        failure: Exception | None = None
        try:
            await client.connect()
            if await client.is_user_authorized():
                return SessionStatus.authorized

            should_cleanup = True
            phone_number = await _resolve_callback(phone_number_callback)
            if self._requested_phone_number != phone_number:
                code_request = await client.send_code_request(phone_number)
                self._requested_phone_number = phone_number
                self._phone_code_hash = getattr(code_request, "phone_code_hash", None)
            code = await _resolve_callback(code_callback)
            try:
                sign_in_kwargs = {
                    "phone": phone_number,
                    "code": code,
                }
                if self._requested_phone_number == phone_number and self._phone_code_hash:
                    sign_in_kwargs["phone_code_hash"] = self._phone_code_hash
                await client.sign_in(**sign_in_kwargs)
            except Exception as exc:
                if not _requires_password(exc) or password_callback is None:
                    raise
                password = await _resolve_callback(password_callback)
                await client.sign_in(password=password)

            if not await client.is_user_authorized():
                raise RuntimeError("Telegram authorization did not complete")
            self._requested_phone_number = None
            self._phone_code_hash = None
            return SessionStatus.authorized
        except Exception as exc:
            self._requested_phone_number = None
            self._phone_code_hash = None
            failure = exc
        finally:
            await _maybe_await(client.disconnect())
        if should_cleanup:
            self._remove_session_files()
        if failure is not None:
            raise failure
        return SessionStatus.authorized

    async def request_code(self, phone_number: str) -> SessionStatus:
        client = self._create_client()
        try:
            await client.connect()
            if await client.is_user_authorized():
                self._requested_phone_number = None
                self._phone_code_hash = None
                return SessionStatus.authorized
            code_request = await client.send_code_request(phone_number)
            self._requested_phone_number = phone_number
            self._phone_code_hash = getattr(code_request, "phone_code_hash", None)
            return SessionStatus.authorization_required
        finally:
            await _maybe_await(client.disconnect())

    async def reauthorize(
        self,
        *,
        phone_number_callback: PromptCallback,
        code_callback: PromptCallback,
        password_callback: PromptCallback | None = None,
    ) -> SessionStatus:
        replacement_session_path = self._replacement_session_path()
        replacement_service = TelegramSetupService(
            api_id=self.api_id,
            api_hash=self.api_hash,
            session_path=replacement_session_path,
            client_factory=self.client_factory,
        )
        try:
            status = await replacement_service.authorize(
                phone_number_callback=phone_number_callback,
                code_callback=code_callback,
                password_callback=password_callback,
            )
        except Exception:
            replacement_service._remove_session_files()
            raise

        self._replace_session_files_from(replacement_session_path)
        return status

    async def list_accessible_chats(self) -> list[AccessibleChat]:
        temp_dir, lookup_session_path = self._create_lookup_session_copy()
        client = self.client_factory(str(lookup_session_path), self.api_id, self.api_hash)
        try:
            await client.connect()
            chats = []
            async for dialog in client.iter_dialogs():
                if getattr(dialog, "is_user", False):
                    continue
                chats.append(AccessibleChat(chat_id=int(dialog.id), title=_display_name(dialog)))
            return sorted(chats, key=lambda chat: chat.title.lower())
        finally:
            await _maybe_await(client.disconnect())
            temp_dir.cleanup()

    async def infer_recent_sender_candidates(
        self,
        chat_ids: Iterable[int],
        *,
        message_limit: int = 50,
    ) -> list[RaidarCandidate]:
        temp_dir, lookup_session_path = self._create_lookup_session_copy()
        client = self.client_factory(str(lookup_session_path), self.api_id, self.api_hash)
        try:
            await client.connect()
            senders: dict[int, Any] = {}
            labels_by_sender_id: dict[int, str] = {}
            sender_counts: Counter[int] = Counter()
            for chat_id in chat_ids:
                async for message in client.iter_messages(chat_id, limit=message_limit):
                    runtime_sender_id = getattr(message, "sender_id", None)
                    sender = await _message_sender(message)
                    if runtime_sender_id is None and (
                        sender is None or not hasattr(sender, "id")
                    ):
                        continue
                    if runtime_sender_id is None:
                        runtime_sender_id = getattr(sender, "id", None)
                    if runtime_sender_id is None:
                        continue
                    runtime_sender_id = int(runtime_sender_id)
                    if sender is not None:
                        senders[runtime_sender_id] = sender
                        labels_by_sender_id[runtime_sender_id] = _label_for_entity(sender)
                    else:
                        labels_by_sender_id.setdefault(
                            runtime_sender_id, str(runtime_sender_id)
                        )
                    sender_counts[runtime_sender_id] += 1

            strict_matches = [
                RaidarCandidate(
                    entity_id=sender_id,
                    label=labels_by_sender_id[sender_id],
                )
                for sender_id, sender in senders.items()
                if _is_supported_raid_bot(sender)
            ]
            strict_match_ids = {candidate.entity_id for candidate in strict_matches}
            fallback_candidates = [
                RaidarCandidate(
                    entity_id=entity_id,
                    label=labels_by_sender_id.get(entity_id, str(entity_id)),
                )
                for entity_id, _count in sorted(
                    sender_counts.items(),
                    key=lambda item: (
                        -item[1],
                        labels_by_sender_id.get(item[0], str(item[0])).lower(),
                    ),
                )
                if entity_id not in strict_match_ids
            ]
            return [*strict_matches, *fallback_candidates]
        finally:
            await _maybe_await(client.disconnect())
            temp_dir.cleanup()

    async def resolve_sender_entry_details(self, entry: str) -> ResolvedSenderEntry:
        temp_dir, lookup_session_path = self._create_lookup_session_copy()
        client = self.client_factory(str(lookup_session_path), self.api_id, self.api_hash)
        try:
            await client.connect()
            entity = await _maybe_await(client.get_entity(entry))
        except Exception as exc:
            raise ValueError(f"Could not resolve sender '{entry}'.") from exc
        finally:
            await _maybe_await(client.disconnect())
            temp_dir.cleanup()
        entity_id = getattr(entity, "id", None)
        if entity_id is None:
            raise ValueError(f"Could not resolve sender '{entry}'.")
        return ResolvedSenderEntry(
            entity_id=int(entity_id),
            label=_label_for_entity(entity),
        )

    async def resolve_sender_entry(self, entry: str) -> int:
        return (await self.resolve_sender_entry_details(entry)).entity_id

    def _create_client(self) -> Any:
        return self.client_factory(str(self.session_path), self.api_id, self.api_hash)

    def _create_lookup_session_copy(self) -> tuple[tempfile.TemporaryDirectory[str], Path]:
        temp_dir = tempfile.TemporaryDirectory(prefix="raidbot-lookup-")
        lookup_session_path = Path(temp_dir.name) / self._session_file_path(self.session_path).name
        for source_path, destination_path in zip(
            self._session_artifact_paths(self.session_path),
            self._session_artifact_paths(lookup_session_path),
        ):
            if source_path.exists():
                shutil.copy2(source_path, destination_path)
        return temp_dir, lookup_session_path

    def _remove_session_files(self) -> None:
        for path in self._session_artifact_paths(self.session_path):
            if path.exists():
                path.unlink()

    def _replace_session_files_from(self, source_session_path: Path) -> None:
        self._remove_session_files()
        for source_path, destination_path in zip(
            self._session_artifact_paths(source_session_path),
            self._session_artifact_paths(self.session_path),
        ):
            if source_path.exists():
                source_path.replace(destination_path)

    def _replacement_session_path(self) -> Path:
        session_file_path = self._session_file_path(self.session_path)
        replacement_name = f"{session_file_path.stem}.replacement{session_file_path.suffix}"
        return session_file_path.with_name(replacement_name)

    def _session_file_path(self, session_path: Path) -> Path:
        if session_path.suffix == ".session":
            return session_path
        return session_path.with_suffix(".session")

    def _session_artifact_paths(self, session_path: Path) -> list[Path]:
        session_file_path = self._session_file_path(session_path)
        return [
            session_file_path,
            session_file_path.with_name(f"{session_file_path.name}-journal"),
            session_file_path.with_name(f"{session_file_path.name}-wal"),
            session_file_path.with_name(f"{session_file_path.name}-shm"),
        ]


def detect_raidar_candidates(entities: Iterable[Any]) -> list[RaidarCandidate]:
    candidates: list[RaidarCandidate] = []
    seen_entity_ids: set[int] = set()
    for entity in entities:
        entity_id = int(entity.id)
        if entity_id in seen_entity_ids or not _is_supported_raid_bot(entity):
            continue
        seen_entity_ids.add(entity_id)
        candidates.append(RaidarCandidate(entity_id=entity_id, label=_label_for_entity(entity)))
    return candidates


def _display_name(entity: Any) -> str:
    return (
        getattr(entity, "title", None)
        or getattr(entity, "first_name", None)
        or getattr(entity, "username", None)
        or str(getattr(entity, "id", ""))
    )


def _label_for_entity(entity: Any) -> str:
    username = getattr(entity, "username", None)
    if username:
        return f"@{username}"
    return _display_name(entity)


def _is_supported_raid_bot(entity: Any) -> bool:
    username = (getattr(entity, "username", None) or "").strip().lower()
    display_name = _display_name(entity).strip().lower()
    return (
        username in SUPPORTED_RAID_BOT_IDENTIFIERS
        or display_name in SUPPORTED_RAID_BOT_IDENTIFIERS
    )


async def _resolve_callback(callback: PromptCallback) -> str:
    return str(await _maybe_await(callback()))


async def _maybe_await(value: Any) -> Any:
    if isinstance(value, Awaitable):
        return await value
    return value


def _requires_password(exc: Exception) -> bool:
    return exc.__class__.__name__ == "SessionPasswordNeededError"


async def _message_sender(message: Any) -> Any:
    sender = getattr(message, "sender", None)
    if sender is not None:
        return sender
    getter = getattr(message, "get_sender", None)
    if getter is None:
        return None
    return await _maybe_await(getter())
