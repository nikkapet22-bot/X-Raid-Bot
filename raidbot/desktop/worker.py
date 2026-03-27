from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any

from raidbot.chrome import ChromeOpener
from raidbot.dedupe import InMemoryOpenedUrlStore
from raidbot.desktop.chrome_profiles import detect_chrome_environment
from raidbot.desktop.models import (
    ActivityEntry,
    BotRuntimeState,
    DesktopAppConfig,
    DesktopAppState,
    TelegramConnectionState,
)
from raidbot.models import MessageOutcome
from raidbot.desktop.storage import DesktopStorage
from raidbot.service import RaidService
from raidbot.telegram_client import TelegramRaidListener


EmitEvent = Callable[[dict[str, Any]], None]
NowFactory = Callable[[], datetime]


class DesktopBotWorker:
    def __init__(
        self,
        config: DesktopAppConfig,
        storage: DesktopStorage,
        emit_event: EmitEvent,
        service_factory: Callable[[DesktopAppConfig], Any] | None = None,
        listener_factory: Callable[..., Any] | None = None,
        chrome_environment_factory: Callable[[], Any] = detect_chrome_environment,
        now: NowFactory = datetime.utcnow,
    ) -> None:
        self.config = config
        self.storage = storage
        self.emit_event = emit_event
        self.service_factory = service_factory
        self.listener_factory = listener_factory or TelegramRaidListener
        self.chrome_environment_factory = chrome_environment_factory
        self.now = now

        self.state = self.storage.load_state()
        self._dedupe_store = InMemoryOpenedUrlStore()
        self._service: Any | None = None
        self._listener: Any | None = None
        self._restart_requested = False
        self._stop_requested = False

    async def run(self) -> None:
        self._stop_requested = False

        while True:
            self._restart_requested = False
            try:
                self._service = self._build_service(self.config)
                self._listener = self._build_listener(self.config)
                self._set_bot_state(BotRuntimeState.starting)
                await self._listener.run_forever()
            except Exception as exc:
                self._handle_run_failure(exc)
                raise

            if self._restart_requested and not self._stop_requested:
                self._set_connection_state(TelegramConnectionState.reconnecting)
                continue

            self._set_connection_state(TelegramConnectionState.disconnected)
            if self.state.bot_state is not BotRuntimeState.stopped:
                self._set_bot_state(BotRuntimeState.stopped)
            break

    async def stop(self) -> None:
        self._stop_requested = True
        if self._listener is None:
            self._set_bot_state(BotRuntimeState.stopped)
            return

        self._set_bot_state(BotRuntimeState.stopping)
        await self._listener.stop()
        self._set_bot_state(BotRuntimeState.stopped)

    async def apply_config(self, config: DesktopAppConfig) -> None:
        telegram_changed = self._telegram_config_changed(config)
        self.config = config

        if telegram_changed:
            self._restart_requested = True
            if self._listener is not None:
                await self._listener.stop()
            return

        if self._service is not None:
            self._service.allowed_chat_ids = set(config.whitelisted_chat_ids)
            self._service.allowed_sender_id = config.raidar_sender_id
            if hasattr(self._service.opener, "profile_directory"):
                self._service.opener.profile_directory = config.chrome_profile_directory

    def _handle_message(self, message) -> Any:
        if self._stop_requested or self._restart_requested or self.state.bot_state is BotRuntimeState.stopping:
            return MessageOutcome(action="ignored", reason="bot_inactive")

        if self._service is None:
            raise RuntimeError("DesktopBotWorker service is not initialized")

        outcome = self._service.handle_message(message)
        self._record_service_outcome(
            outcome.action,
            outcome.reason,
            outcome.normalized_url,
        )
        return outcome

    def _handle_connection_state_change(self, state: str) -> None:
        connection_state = TelegramConnectionState(state)
        self._set_connection_state(connection_state)
        if (
            connection_state is TelegramConnectionState.connected
            and self.state.bot_state is BotRuntimeState.starting
        ):
            self._set_bot_state(BotRuntimeState.running)

    def _record_service_outcome(
        self,
        action: str,
        reason: str,
        normalized_url: str | None,
    ) -> None:
        timestamp = self.now()
        if action == "opened":
            self.state.raids_opened += 1
            self.state.last_successful_raid_open_at = timestamp.isoformat()
        elif reason == "duplicate":
            self.state.duplicates_skipped += 1
        elif reason in {"not_a_raid", "chat_not_whitelisted", "sender_not_allowed"}:
            self.state.non_matching_skipped += 1
        elif reason == "open_failed":
            self.state.open_failures += 1
            self.state.last_error = reason

        entry = ActivityEntry(
            timestamp=timestamp,
            action=action,
            url=normalized_url,
            reason=reason,
        )
        self.state.activity = [*self.state.activity, entry][-200:]
        self.storage.save_state(self.state)
        self._emit("stats_changed", state=self.state)
        self._emit("activity_added", entry=entry)
        if reason == "open_failed":
            self._emit("error", message=reason)

    def _build_service(self, config: DesktopAppConfig) -> Any:
        if self.service_factory is not None:
            return self.service_factory(config)

        if config.raidar_sender_id is None:
            raise ValueError("Raidar sender ID is required before starting the bot")

        chrome_environment = self.chrome_environment_factory()
        opener = ChromeOpener(
            chrome_path=chrome_environment.chrome_path,
            user_data_dir=chrome_environment.user_data_dir,
            profile_directory=config.chrome_profile_directory,
        )
        return RaidService(
            allowed_chat_ids=set(config.whitelisted_chat_ids),
            allowed_sender_id=config.raidar_sender_id,
            opener=opener,
            dedupe_store=self._dedupe_store,
        )

    def _build_listener(self, config: DesktopAppConfig) -> Any:
        listener = self.listener_factory(
            api_id=config.telegram_api_id,
            api_hash=config.telegram_api_hash,
            session_path=str(config.telegram_session_path),
            on_message=self._handle_message,
            on_connection_state_change=self._handle_connection_state_change,
        )
        if hasattr(listener, "on_message"):
            listener.on_message = self._handle_message
        if hasattr(listener, "on_connection_state_change"):
            listener.on_connection_state_change = self._handle_connection_state_change
        return listener

    def _telegram_config_changed(self, config: DesktopAppConfig) -> bool:
        return (
            self.config.telegram_api_id != config.telegram_api_id
            or self.config.telegram_api_hash != config.telegram_api_hash
            or self.config.telegram_session_path != config.telegram_session_path
        )

    def _set_bot_state(self, state: BotRuntimeState) -> None:
        self.state.bot_state = state
        self.storage.save_state(self.state)
        self._emit("bot_state_changed", state=state.value)

    def _set_connection_state(self, state: TelegramConnectionState) -> None:
        self.state.connection_state = state
        self.storage.save_state(self.state)
        self._emit("connection_state_changed", state=state.value)

    def _emit(self, event_type: str, **payload: Any) -> None:
        self.emit_event({"type": event_type, **payload})

    def _handle_run_failure(self, exc: Exception) -> None:
        self.state.last_error = str(exc)
        self._set_bot_state(BotRuntimeState.error)
        self._emit("error", message=self.state.last_error)
