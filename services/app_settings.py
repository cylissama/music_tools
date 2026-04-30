"""Purpose: Persist application settings such as saved music locations across runs."""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

APP_NAME = "WalkmanPlaylistCreator"
SETTINGS_FILENAME = "app_settings.json"


@dataclass
class AppSettings:
    """Plain-Python settings that are safe to serialize to JSON."""

    music_directories: list[str] = field(default_factory=list)
    selected_music_directory: str | None = None


class AppSettingsStore:
    """Load and save persistent application settings to a JSON file."""

    def __init__(self, settings_path: Path | None = None) -> None:
        self.settings_path = self._resolve_settings_path(settings_path)

    def load(self) -> AppSettings:
        """Return saved settings, or defaults if nothing has been stored yet."""
        if not self.settings_path.exists():
            return AppSettings()

        try:
            payload = json.loads(self.settings_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return AppSettings()

        if not isinstance(payload, dict):
            return AppSettings()

        directories = payload.get("music_directories", [])
        selected = payload.get("selected_music_directory")

        return AppSettings(
            music_directories=[str(item) for item in directories if isinstance(item, str) and item.strip()],
            selected_music_directory=str(selected) if isinstance(selected, str) and selected.strip() else None,
        )

    def save(self, settings: AppSettings) -> None:
        """Persist the provided settings to disk."""
        payload = {
            "music_directories": settings.music_directories,
            "selected_music_directory": settings.selected_music_directory,
        }
        self.settings_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    def _resolve_settings_path(self, settings_path: Path | None) -> Path:
        candidate = settings_path or get_default_settings_path()
        try:
            candidate.parent.mkdir(parents=True, exist_ok=True)
            return candidate
        except PermissionError:
            fallback = Path.cwd() / ".app_state" / SETTINGS_FILENAME
            fallback.parent.mkdir(parents=True, exist_ok=True)
            return fallback


def get_default_settings_path() -> Path:
    """Return the persistent settings location for this app."""
    home = Path.home()
    if sys.platform == "darwin":
        return home / "Library" / "Application Support" / APP_NAME / SETTINGS_FILENAME
    return home / ".local" / "state" / APP_NAME / SETTINGS_FILENAME
