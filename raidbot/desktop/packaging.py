from __future__ import annotations

from .branding import APP_NAME, APP_VERSION

DEFAULT_BETA_CHANNEL = "beta2"
WINDOWS_ARCH_LABEL = "win64"


def bundled_folder_name() -> str:
    return APP_NAME


def beta_zip_name(version: str | None = None, channel: str = DEFAULT_BETA_CHANNEL) -> str:
    resolved_version = version or APP_VERSION
    return f"L8N-Raid-Bot-v{resolved_version}-{channel}-{WINDOWS_ARCH_LABEL}.zip"


def build_beta_readme(
    *,
    version: str | None = None,
    channel: str = DEFAULT_BETA_CHANNEL,
) -> str:
    resolved_version = version or APP_VERSION
    return (
        f"{APP_NAME} v{resolved_version} {channel}\n"
        "\n"
        "1. Unzip this folder anywhere on your PC.\n"
        f"2. Run {APP_NAME}.exe.\n"
        "3. App data lives in %APPDATA%\\RaidBot.\n"
        "4. Report startup, tray, setup, and automation issues.\n"
    )
