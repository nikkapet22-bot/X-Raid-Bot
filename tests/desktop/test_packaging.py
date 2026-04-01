from __future__ import annotations

from pathlib import Path


def test_beta_zip_name_uses_versioned_windows_artifact() -> None:
    from raidbot.desktop.packaging import beta_zip_name

    assert beta_zip_name("2.1.6", "beta2") == "L8N-Raid-Bot-v2.1.6-beta2-win64.zip"


def test_bundled_folder_name_matches_executable_brand() -> None:
    from raidbot.desktop.packaging import bundled_folder_name

    assert bundled_folder_name() == "L8N Raid Bot"


def test_build_beta_readme_mentions_appdata_and_exe_name() -> None:
    from raidbot.desktop.packaging import build_beta_readme

    text = build_beta_readme(version="2.1.6", channel="beta2")

    assert "L8N Raid Bot.exe" in text
    assert "%APPDATA%\\RaidBot" in text


def test_pyproject_declares_pyinstaller_build_dependency() -> None:
    content = Path("pyproject.toml").read_text(encoding="utf-8")

    assert "pyinstaller" in content.lower()


def test_windows_spec_exists_for_l8n_raid_bot() -> None:
    spec_path = Path("packaging/windows/L8N Raid Bot.spec")

    assert spec_path.exists()


def test_build_script_references_spec_and_versioned_zip_name() -> None:
    content = Path("scripts/build_windows_beta.py").read_text(encoding="utf-8")

    assert "L8N Raid Bot.spec" in content
    assert "beta_zip_name" in content


def test_beta_readme_template_mentions_unzip_and_appdata() -> None:
    content = Path("packaging/windows/README-beta.txt").read_text(encoding="utf-8")

    assert "unzip" in content.lower()
    assert "%APPDATA%\\RaidBot" in content


def test_smoke_script_supports_fresh_and_configured_startup_modes() -> None:
    content = Path("scripts/smoke_test_packaged.py").read_text(encoding="utf-8")

    assert "--fresh-appdata" in content
    assert "--configured-appdata" in content


def test_smoke_script_cleanup_retries_locked_temp_dir(tmp_path, monkeypatch) -> None:
    from scripts.smoke_test_packaged import _cleanup_temp_dir

    target = tmp_path / "smoke"
    target.mkdir()
    calls = {"count": 0}

    def fake_rmtree(path: Path) -> None:
        calls["count"] += 1
        if calls["count"] == 1:
            raise PermissionError("locked")

    monkeypatch.setattr("scripts.smoke_test_packaged.shutil.rmtree", fake_rmtree)
    monkeypatch.setattr("scripts.smoke_test_packaged.time.sleep", lambda _seconds: None)

    assert _cleanup_temp_dir(target, retries=2, delay_seconds=0.0) is True

    assert calls["count"] == 2


def test_smoke_script_cleanup_returns_false_when_lock_persists(
    tmp_path, monkeypatch
) -> None:
    from scripts.smoke_test_packaged import _cleanup_temp_dir

    target = tmp_path / "smoke"
    target.mkdir()

    monkeypatch.setattr(
        "scripts.smoke_test_packaged.shutil.rmtree",
        lambda _path: (_ for _ in ()).throw(PermissionError("locked")),
    )
    monkeypatch.setattr("scripts.smoke_test_packaged.time.sleep", lambda _seconds: None)

    assert _cleanup_temp_dir(target, retries=2, delay_seconds=0.0) is False
