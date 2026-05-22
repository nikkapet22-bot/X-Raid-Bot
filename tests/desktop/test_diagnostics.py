from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from zipfile import ZipFile

from raidbot.desktop.models import DesktopAppConfig
from raidbot.desktop.storage import DesktopStorage


def test_diagnostics_logger_writes_structured_jsonl(tmp_path: Path) -> None:
    from raidbot.desktop.diagnostics import DiagnosticsLogger

    now = datetime(2026, 5, 22, 10, 11, 12)
    logger = DiagnosticsLogger(tmp_path, now=lambda: now)

    logger.log(
        "chrome_open_start",
        profile_directory="Profile 1",
        url="https://x.com/i/status/123",
        window={"handle": 99},
    )

    log_path = tmp_path / "logs" / "raidbot-2026-05-22.jsonl"
    record = json.loads(log_path.read_text(encoding="utf-8").strip())

    assert record["timestamp"] == "2026-05-22T10:11:12"
    assert record["event"] == "chrome_open_start"
    assert record["profile_directory"] == "Profile 1"
    assert record["window"] == {"handle": 99}


def test_export_diagnostics_redacts_config_and_excludes_session_file(
    tmp_path: Path,
) -> None:
    from raidbot.desktop.diagnostics import export_diagnostics

    base_dir = tmp_path / "RaidBot"
    storage = DesktopStorage(base_dir)
    storage.save_config(
        DesktopAppConfig(
            telegram_api_id=123456,
            telegram_api_hash="secret-api-hash",
            telegram_session_path=base_dir / "raidbot.session",
            telegram_phone_number="+40123456789",
            whitelisted_chat_ids=[-1001],
            whitelisted_chat_titles={-1001: "Rally Guard Raid"},
            allowed_sender_ids=[777],
            allowed_sender_entries=["Rally Guard Raid"],
            chrome_profile_directory="Profile 1",
        )
    )
    storage.save_state(storage.load_state())
    (base_dir / "raidbot.session").write_text("private session", encoding="utf-8")
    (base_dir / "logs").mkdir(parents=True, exist_ok=True)
    (base_dir / "logs" / "raidbot-2026-05-22.jsonl").write_text(
        '{"event":"profile_run_failed"}\n',
        encoding="utf-8",
    )

    archive_path = export_diagnostics(
        base_dir,
        now=lambda: datetime(2026, 5, 22, 10, 30, 0),
    )

    with ZipFile(archive_path) as archive:
        names = set(archive.namelist())
        sanitized_config = json.loads(
            archive.read("config.sanitized.json").decode("utf-8")
        )

    assert "logs/raidbot-2026-05-22.jsonl" in names
    assert "state.json" in names
    assert "app-info.json" in names
    assert "raidbot.session" not in names
    assert sanitized_config["telegram_api_hash"] == "<redacted>"
    assert sanitized_config["telegram_phone_number"] == "<redacted>"
    assert sanitized_config["telegram_session_path"] == "<redacted>"
    assert sanitized_config["whitelisted_chat_titles"] == {"-1001": "Rally Guard Raid"}
