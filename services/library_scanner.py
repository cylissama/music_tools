"""Purpose: Scan music folders and return album-folder data for the application."""

import os
from pathlib import Path

from models import LibraryAlbum, TrackScanMetadata

try:
    from services.tagging.reader import read_canonical_metadata
except ImportError:  # pragma: no cover - handled at runtime
    read_canonical_metadata = None

AUDIO_EXTS = (".mp3", ".flac", ".wav", ".m4a", ".aac", ".ogg")


def scan_music_files(start: Path, root_folder: Path | None = None) -> list[LibraryAlbum]:
    """Scan a folder recursively and return folders that contain audio files."""
    albums: list[LibraryAlbum] = []

    for current_root, _, files in os.walk(start):
        folder_tracks: list[str] = []
        track_metadata: dict[str, TrackScanMetadata] = {}

        for filename in files:
            if not filename.lower().endswith(AUDIO_EXTS):
                continue

            full_path = Path(current_root) / filename

            if root_folder and full_path.is_relative_to(root_folder):
                track_path = full_path.relative_to(root_folder)
            else:
                track_path = full_path.relative_to(start)

            folder_tracks.append(str(track_path))
            track_metadata[str(track_path)] = _build_track_scan_metadata(full_path, track_path)

        if not folder_tracks:
            continue

        folder_tracks.sort(key=str.lower)
        folder_label = _build_folder_label(Path(current_root), start, root_folder)
        albums.append(
            LibraryAlbum(
                folder_path=folder_label,
                track_count=len(folder_tracks),
                tracks=folder_tracks,
                track_metadata=track_metadata,
            )
        )

    return sorted(albums, key=lambda album: album.folder_path.lower())


def _build_folder_label(
    current_root: Path,
    start: Path,
    root_folder: Path | None,
) -> str:
    """Return the folder path to show in the UI."""
    if root_folder and current_root.is_relative_to(root_folder):
        relative_folder = current_root.relative_to(root_folder)
    else:
        relative_folder = current_root.relative_to(start)

    folder_label = str(relative_folder)
    return folder_label if folder_label != "." else current_root.name


def _build_track_scan_metadata(full_path: Path, track_path: Path) -> TrackScanMetadata:
    metadata = TrackScanMetadata(relative_path=str(track_path), file_name=track_path.name)
    if read_canonical_metadata is None:
        return metadata

    try:
        track = read_canonical_metadata(full_path)
    except Exception:
        return metadata

    metadata.title = track.metadata.title
    metadata.artist = list(track.metadata.artist)
    metadata.album = track.metadata.album
    metadata.genre = list(track.metadata.genre)
    metadata.track_number = track.metadata.track_number
    metadata.release_date = track.metadata.release_date
    return metadata
