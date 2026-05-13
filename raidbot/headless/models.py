from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class HeadlessActionToggles:
    reply: bool = True
    like: bool = True
    repost: bool = True
    bookmark: bool = True


@dataclass(frozen=True)
class HeadlessSettings:
    enabled_actions: HeadlessActionToggles = field(
        default_factory=HeadlessActionToggles
    )
    chrome_profile_directory: str | None = None


@dataclass(frozen=True)
class HeadlessAuthState:
    status: str
    detail: str | None = None


@dataclass(frozen=True)
class HeadlessRunResult:
    url: str | None
    success: bool
    reason: str
    completed_actions: tuple[str, ...] = ()


@dataclass(frozen=True)
class HeadlessAppState:
    auth_state: HeadlessAuthState = field(
        default_factory=lambda: HeadlessAuthState(status="needs_login")
    )
    last_detected_raid: str | None = None
    last_result: HeadlessRunResult | None = None
    running: bool = False
    log_lines: tuple[str, ...] = ()
