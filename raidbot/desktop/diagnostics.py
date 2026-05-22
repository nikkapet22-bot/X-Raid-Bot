from __future__ import annotations

import json
import threading
from dataclasses import asdict, is_dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable
from zipfile import ZIP_DEFLATED, ZipFile

from raidbot import __version__

NowFactory = Callable[[], datetime]

_REDACTED = "<redacted>"
_REDACTED_CONFIG_KEYS = {
    "telegram_api_hash",
    "telegram_phone_number",
    "telegram_session_path",
}


class DiagnosticsLogger:
    """Append-only beta diagnostics log that must never break runtime flow."""

    def __init__(self, base_dir: Path, *, now: NowFactory = datetime.now) -> None:
        self.base_dir = Path(base_dir)
        self.logs_dir = self.base_dir / "logs"
        self.now = now
        self._lock = threading.Lock()

    def log(self, event: str, **fields: Any) -> None:
        try:
            timestamp = self.now()
            record = {
                "timestamp": timestamp.isoformat(),
                "event": str(event),
                **{key: self._json_safe(value) for key, value in fields.items()},
            }
            self.logs_dir.mkdir(parents=True, exist_ok=True)
            log_path = self.logs_dir / f"raidbot-{timestamp.date().isoformat()}.jsonl"
            line = json.dumps(record, ensure_ascii=True, sort_keys=True)
            with self._lock:
                with log_path.open("a", encoding="utf-8") as log_file:
                    log_file.write(f"{line}\n")
        except Exception:
            return

    def _json_safe(self, value: Any) -> Any:
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, Path):
            return str(value)
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, BaseException):
            return {
                "type": type(value).__name__,
                "message": str(value),
            }
        if is_dataclass(value) and not isinstance(value, type):
            return self._json_safe(asdict(value))
        if isinstance(value, dict):
            return {str(key): self._json_safe(item) for key, item in value.items()}
        if isinstance(value, (list, tuple, set)):
            return [self._json_safe(item) for item in value]
        return repr(value)


def export_diagnostics(
    base_dir: Path,
    *,
    destination: Path | None = None,
    now: NowFactory = datetime.now,
) -> Path:
    base_dir = Path(base_dir)
    timestamp = now()
    if destination is None:
        destination_dir = base_dir / "diagnostics"
        destination_dir.mkdir(parents=True, exist_ok=True)
        archive_path = (
            destination_dir
            / f"raidbot-diagnostics-{timestamp.strftime('%Y%m%d-%H%M%S')}.zip"
        )
    else:
        destination = Path(destination)
        if destination.suffix.lower() == ".zip":
            destination.parent.mkdir(parents=True, exist_ok=True)
            archive_path = destination
        else:
            destination.mkdir(parents=True, exist_ok=True)
            archive_path = (
                destination
                / f"raidbot-diagnostics-{timestamp.strftime('%Y%m%d-%H%M%S')}.zip"
            )

    with ZipFile(archive_path, "w", compression=ZIP_DEFLATED) as archive:
        _write_json_entry(
            archive,
            "app-info.json",
            {
                "app": "L8N Raid Bot",
                "version": __version__,
                "exported_at": timestamp.isoformat(),
            },
        )
        _write_json_entry(
            archive,
            "config.sanitized.json",
            _load_sanitized_config(base_dir / "config.json"),
        )
        _write_file_if_exists(archive, base_dir / "state.json", "state.json")
        _write_file_if_exists(
            archive,
            base_dir / "automation_sequences.json",
            "automation_sequences.json",
        )
        logs_dir = base_dir / "logs"
        if logs_dir.exists():
            for log_path in sorted(logs_dir.glob("*.jsonl")):
                if log_path.is_file():
                    _write_file_if_exists(
                        archive,
                        log_path,
                        f"logs/{log_path.name}",
                    )
    return archive_path


def _load_sanitized_config(config_path: Path) -> dict[str, Any]:
    if not config_path.exists():
        return {}
    try:
        raw_config = json.loads(config_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {
            "error": "config_unreadable",
            "reason": f"{type(exc).__name__}: {exc}",
        }
    if not isinstance(raw_config, dict):
        return {"error": "config_not_object"}
    return _sanitize_config(raw_config)


def _sanitize_config(value: Any, *, key: str | None = None) -> Any:
    if key in _REDACTED_CONFIG_KEYS:
        return _REDACTED
    if isinstance(value, dict):
        return {
            str(item_key): _sanitize_config(item_value, key=str(item_key))
            for item_key, item_value in value.items()
        }
    if isinstance(value, list):
        return [_sanitize_config(item) for item in value]
    return value


def _write_json_entry(archive: ZipFile, name: str, data: dict[str, Any]) -> None:
    archive.writestr(
        name,
        json.dumps(data, ensure_ascii=True, indent=2, sort_keys=True),
    )


def _write_file_if_exists(archive: ZipFile, path: Path, name: str) -> None:
    if not path.exists() or not path.is_file():
        return
    try:
        archive.write(path, arcname=name)
    except OSError:
        return
