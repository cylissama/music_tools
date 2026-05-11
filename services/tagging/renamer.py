"""Purpose: Build and apply configurable file rename plans from canonical tags."""

from __future__ import annotations

import re
import shutil
import string
from dataclasses import dataclass, field
from pathlib import Path

from services.app_settings import RenameConfig
from services.tagging.schema import CanonicalTrack

INVALID_PATH_CHARS = '<>:"/\\|?*'
RESERVED_NAMES = {
    ".",
    "..",
    "CON",
    "PRN",
    "AUX",
    "NUL",
    "COM1",
    "COM2",
    "COM3",
    "COM4",
    "COM5",
    "COM6",
    "COM7",
    "COM8",
    "COM9",
    "LPT1",
    "LPT2",
    "LPT3",
    "LPT4",
    "LPT5",
    "LPT6",
    "LPT7",
    "LPT8",
    "LPT9",
}


@dataclass
class RenamePlan:
    """Describe where a tagged track should be moved on disk."""

    source_path: str
    target_path: str
    rename_required: bool
    warnings: list[str] = field(default_factory=list)


def plan_track_rename(track: CanonicalTrack, config: RenameConfig) -> RenamePlan:
    """Resolve the configured folder and file naming templates for one track."""
    return plan_track_rename_with_context(track, config, album_tracks=None)


def plan_track_rename_with_context(
    track: CanonicalTrack,
    config: RenameConfig,
    album_tracks: list[CanonicalTrack] | None,
) -> RenamePlan:
    """Resolve the configured folder and file naming templates for one track."""
    source_path = Path(track.file_path)
    context = _build_template_context(track, source_path, album_tracks, config)

    warnings: list[str] = []
    folder_name = _render_template(config.folder_template, context, "Unknown Album Folder", warnings)
    file_stem = _render_template(config.file_template, context, source_path.stem, warnings)
    file_name = _build_target_filename(file_stem, source_path.suffix)

    target_dir = source_path.parent.with_name(folder_name)
    target_path = target_dir / file_name
    rename_required = target_path != source_path

    if target_path.exists() and target_path != source_path and not config.replace_existing:
        warnings.append(f"target already exists: {target_path}")

    return RenamePlan(
        source_path=str(source_path),
        target_path=str(target_path),
        rename_required=rename_required,
        warnings=warnings,
    )


def apply_track_rename(track: CanonicalTrack, config: RenameConfig) -> RenamePlan:
    """Rename a tagged track on disk and update the canonical path in place."""
    return apply_track_rename_with_context(track, config, album_tracks=None)


def apply_track_rename_with_context(
    track: CanonicalTrack,
    config: RenameConfig,
    album_tracks: list[CanonicalTrack] | None,
) -> RenamePlan:
    """Rename a tagged track on disk and update the canonical path in place."""
    plan = plan_track_rename_with_context(track, config, album_tracks)
    if not plan.rename_required:
        return plan
    if plan.warnings:
        raise ValueError("; ".join(plan.warnings))

    source_path = Path(plan.source_path)
    target_path = Path(plan.target_path)
    target_path.parent.mkdir(parents=True, exist_ok=True)

    if target_path.exists() and config.replace_existing:
        if target_path.is_dir():
            raise ValueError(f"Cannot replace directory with audio file: {target_path}")
        target_path.unlink()

    shutil.move(str(source_path), str(target_path))
    track.file_path = str(target_path)

    if album_tracks:
        _move_album_sidecar_items(
            source_dir=source_path.parent,
            target_dir=target_path.parent,
            current_source_path=source_path,
            config=config,
            album_tracks=album_tracks,
        )

    if config.cleanup_empty_source_dirs:
        _cleanup_empty_parent(source_path.parent, stop_before=target_path.parent.parent)

    return RenamePlan(
        source_path=plan.source_path,
        target_path=str(target_path),
        rename_required=True,
        warnings=[],
    )


def _build_template_context(
    track: CanonicalTrack,
    source_path: Path,
    album_tracks: list[CanonicalTrack] | None,
    config: RenameConfig,
) -> dict[str, object]:
    metadata = track.metadata
    album_context = _aggregate_album_context(track, album_tracks) if config.use_album_level_folder_naming else {}
    album_artist = str(
        album_context.get("album_artist")
        or _join_non_empty(metadata.album_artist)
        or _join_non_empty(metadata.artist)
        or "Unknown Artist"
    )
    artist = _join_non_empty(metadata.artist) or album_artist
    title = metadata.title or source_path.stem
    album = str(album_context.get("album") or metadata.album or "Unknown Album")
    release_year = str(album_context.get("release_year") or _extract_release_year(metadata.release_date))
    track_number = metadata.track_number
    disc_number = metadata.disc_number
    suffix = source_path.suffix
    file_type = str(
        album_context.get("file_type")
        or (track.file_format.upper() if track.file_format else suffix.lstrip(".").upper())
    )

    return {
        "album_artist": album_artist,
        "artist": artist,
        "album": album,
        "title": title,
        "release_year": release_year,
        "track_number": track_number if track_number is not None else 0,
        "track_number_padded": f"{track_number:02d}" if track_number is not None else "00",
        "disc_number": disc_number if disc_number is not None else 0,
        "disc_number_padded": f"{disc_number:02d}" if disc_number is not None else "00",
        "file_type": file_type,
        "file_extension": suffix.lstrip(".").lower(),
    }


def _aggregate_album_context(
    track: CanonicalTrack,
    album_tracks: list[CanonicalTrack] | None,
) -> dict[str, str]:
    if not album_tracks:
        return {}

    same_directory_tracks = [
        item for item in album_tracks if Path(item.file_path).parent == Path(track.file_path).parent
    ]
    if not same_directory_tracks:
        same_directory_tracks = album_tracks

    return {
        "album_artist": _first_consistent(
            [_join_non_empty(item.metadata.album_artist) or _join_non_empty(item.metadata.artist) for item in same_directory_tracks]
        )
        or "",
        "album": _first_consistent([item.metadata.album for item in same_directory_tracks]) or "",
        "release_year": _first_consistent(
            [_extract_release_year(item.metadata.release_date) for item in same_directory_tracks]
        )
        or "",
        "file_type": _first_consistent([item.file_format.upper() for item in same_directory_tracks if item.file_format]) or "",
    }


def _render_template(
    template: str,
    context: dict[str, object],
    fallback: str,
    warnings: list[str],
) -> str:
    formatter = string.Formatter()
    parts: list[str] = []
    missing_fields: list[str] = []

    for literal_text, field_name, format_spec, conversion in formatter.parse(template):
        parts.append(literal_text)
        if field_name is None:
            continue

        if field_name not in context:
            missing_fields.append(field_name)
            continue

        value = context[field_name]
        if conversion:
            value = formatter.convert_field(value, conversion)
        parts.append(formatter.format_field(value, format_spec))

    if missing_fields:
        warnings.append(f"unknown rename template fields: {', '.join(sorted(set(missing_fields)))}")

    sanitized = _sanitize_path_component("".join(parts))
    return sanitized or _sanitize_path_component(fallback)


def _build_target_filename(file_stem: str, suffix: str) -> str:
    suffix_value = suffix if suffix.startswith(".") else f".{suffix}" if suffix else ""
    sanitized_stem = _sanitize_path_component(file_stem)
    return f"{sanitized_stem or 'untitled'}{suffix_value.lower()}"


def _sanitize_path_component(value: str) -> str:
    cleaned = "".join("_" if char in INVALID_PATH_CHARS else char for char in value)
    cleaned = re.sub(r"\s+", " ", cleaned).strip().rstrip(".")
    cleaned = re.sub(r"^\.+$", "", cleaned)
    if not cleaned:
        return ""
    if cleaned.upper() in RESERVED_NAMES:
        return f"_{cleaned}"
    return cleaned


def _extract_release_year(release_date: str | None) -> str:
    if not release_date:
        return "Unknown Year"
    match = re.match(r"(\d{4})", release_date)
    return match.group(1) if match else "Unknown Year"


def _join_non_empty(values: list[str]) -> str | None:
    cleaned = [value.strip() for value in values if value.strip()]
    return ", ".join(cleaned) if cleaned else None


def _first_consistent(values: list[str | None]) -> str | None:
    cleaned = [value.strip() for value in values if isinstance(value, str) and value.strip() and value.strip() != "Unknown Year"]
    if not cleaned:
        return None
    counts: dict[str, int] = {}
    for value in cleaned:
        counts[value] = counts.get(value, 0) + 1
    return sorted(counts.items(), key=lambda item: (-item[1], item[0].lower()))[0][0]


def _cleanup_empty_parent(directory: Path, *, stop_before: Path | None) -> None:
    current = directory
    stop_target = stop_before.resolve() if stop_before is not None and stop_before.exists() else stop_before

    while current.exists() and current.is_dir():
        if stop_target is not None and current.resolve() == stop_target:
            return
        try:
            current.rmdir()
        except OSError:
            return
        current = current.parent


def _move_album_sidecar_items(
    *,
    source_dir: Path,
    target_dir: Path,
    current_source_path: Path,
    config: RenameConfig,
    album_tracks: list[CanonicalTrack],
) -> None:
    """Move non-track album items like cover art into the new album directory."""
    if source_dir == target_dir or not source_dir.exists() or not source_dir.is_dir():
        return

    album_source_paths = {
        Path(item.file_path).resolve()
        for item in album_tracks
        if Path(item.file_path).parent == source_dir
    }
    album_source_paths.add(current_source_path.resolve())

    for sibling in source_dir.iterdir():
        try:
            resolved_sibling = sibling.resolve()
        except OSError:
            resolved_sibling = sibling

        if resolved_sibling in album_source_paths:
            continue

        destination = target_dir / sibling.name
        if destination.exists():
            if not config.replace_existing:
                raise ValueError(f"target already exists: {destination}")
            _remove_existing_path(destination)

        shutil.move(str(sibling), str(destination))


def _remove_existing_path(path: Path) -> None:
    if path.is_dir():
        shutil.rmtree(path)
        return
    path.unlink()
