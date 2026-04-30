"""Purpose: Provide simple helper functions for logging user activity events."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from services.logging_config import LOGGER_NAME, get_session_id


def log_app_started(log_file_path: Path) -> None:
    log_event("app_started", log_file_path=log_file_path)


def log_app_exited(exit_code: int) -> None:
    log_event("app_exited", exit_code=exit_code)


def log_root_selected(folder: Path) -> None:
    log_event("root_selected", folder=folder)


def log_music_locations_loaded(location_count: int, selected_folder: Path | None) -> None:
    log_event(
        "music_locations_loaded",
        location_count=location_count,
        selected_folder=selected_folder,
    )


def log_music_location_added(folder: Path, total_locations: int) -> None:
    log_event("music_location_added", folder=folder, total_locations=total_locations)


def log_music_location_removed(folder: Path, total_locations: int) -> None:
    log_event("music_location_removed", folder=folder, total_locations=total_locations)


def log_music_location_activated(folder: Path) -> None:
    log_event("music_location_activated", folder=folder)


def log_settings_save_failed(operation: str, error: Exception) -> None:
    logger = logging.getLogger(LOGGER_NAME)
    logger.exception(
        "settings_save_failed",
        extra={
            "event": "settings_save_failed",
            "details": _sanitize(
                {
                    "operation": operation,
                    "error": str(error),
                }
            ),
            "session_id": get_session_id(),
        },
    )


def log_root_selection_cancelled() -> None:
    log_event("root_selection_cancelled")


def log_scan_started(folder: Path, root_folder: Path | None) -> None:
    log_event("scan_started", folder=folder, root_folder=root_folder)


def log_scan_cancelled() -> None:
    log_event("scan_cancelled")


def log_scan_completed(folder: Path, album_count: int, track_count: int) -> None:
    log_event(
        "scan_completed",
        folder=folder,
        album_count=album_count,
        track_count=track_count,
    )


def log_album_toggled(album: str, expanded: bool) -> None:
    log_event("album_toggled", album=album, expanded=expanded)


def log_tracks_added(tracks: list[str], source: str) -> None:
    log_event(
        "tracks_added_to_playlist",
        source=source,
        track_count=len(tracks),
        tracks=tracks,
    )


def log_playlist_track_removed(track: str, index: int) -> None:
    log_event("playlist_track_removed", track=track, index=index)


def log_playlist_reordered(track: str, from_index: int, to_index: int, source: str) -> None:
    log_event(
        "playlist_reordered",
        track=track,
        from_index=from_index,
        to_index=to_index,
        source=source,
    )


def log_playlist_reordered_from_drag(tracks: list[str]) -> None:
    log_event(
        "playlist_reordered_by_drag",
        track_count=len(tracks),
        tracks=tracks,
    )


def log_playlist_cleared(track_count: int) -> None:
    log_event("playlist_cleared", track_count=track_count)


def log_playlist_save_cancelled(stage: str) -> None:
    log_event("playlist_save_cancelled", stage=stage)


def log_playlist_save_started(name: str, save_path: Path, tracks: list[str]) -> None:
    log_event(
        "playlist_save_started",
        playlist_name=name,
        save_path=save_path,
        track_count=len(tracks),
        tracks=tracks,
    )


def log_playlist_saved(name: str, save_path: Path, tracks: list[str]) -> None:
    log_event(
        "playlist_saved",
        playlist_name=name,
        save_path=save_path,
        track_count=len(tracks),
        tracks=tracks,
    )


def log_tag_preview_started(file_path: str) -> None:
    log_event("tag_preview_started", file_path=file_path)


def log_tag_preview_ready(
    file_path: str,
    score: float | None,
    review_required: bool,
    best_source: str,
    change_count: int,
) -> None:
    log_event(
        "tag_preview_ready",
        file_path=file_path,
        score=score,
        review_required=review_required,
        best_source=best_source,
        change_count=change_count,
    )


def log_tag_preview_dismissed(file_path: str) -> None:
    log_event("tag_preview_dismissed", file_path=file_path)


def log_tag_preview_failed(file_path: str, error: Exception) -> None:
    logger = logging.getLogger(LOGGER_NAME)
    logger.exception(
        "tag_preview_failed",
        extra={
            "event": "tag_preview_failed",
            "details": _sanitize(
                {
                    "file_path": file_path,
                    "error": str(error),
                }
            ),
            "session_id": get_session_id(),
        },
    )


def log_tag_apply_started(file_path: str, score: float | None) -> None:
    log_event("tag_apply_started", file_path=file_path, score=score)


def log_tag_apply_succeeded(file_path: str, change_count: int) -> None:
    log_event("tag_apply_succeeded", file_path=file_path, change_count=change_count)


def log_tag_apply_failed(file_path: str, error: Exception) -> None:
    logger = logging.getLogger(LOGGER_NAME)
    logger.exception(
        "tag_apply_failed",
        extra={
            "event": "tag_apply_failed",
            "details": _sanitize(
                {
                    "file_path": file_path,
                    "error": str(error),
                }
            ),
            "session_id": get_session_id(),
        },
    )


def log_playlist_save_failed(
    name: str,
    save_path: Path,
    tracks: list[str],
    error: Exception,
) -> None:
    logger = logging.getLogger(LOGGER_NAME)
    logger.exception(
        "playlist_save_failed",
        extra={
            "event": "playlist_save_failed",
            "details": _sanitize(
                {
                    "playlist_name": name,
                    "save_path": save_path,
                    "track_count": len(tracks),
                    "tracks": tracks,
                    "error": str(error),
                }
            ),
            "session_id": get_session_id(),
        },
    )


def log_event(event: str, *, level: int = logging.INFO, **details: Any) -> None:
    """Log one structured activity event."""
    logger = logging.getLogger(LOGGER_NAME)
    logger.log(
        level,
        event,
        extra={
            "event": event,
            "details": _sanitize(details),
            "session_id": get_session_id(),
        },
    )


def _sanitize(value: Any) -> Any:
    """Convert values into JSON-safe types for the log formatter."""
    if isinstance(value, Path):
        return str(value)

    if isinstance(value, dict):
        return {str(key): _sanitize(item) for key, item in value.items()}

    if isinstance(value, (list, tuple, set)):
        return [_sanitize(item) for item in value]

    return value
