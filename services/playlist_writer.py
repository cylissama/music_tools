"""Purpose: Convert playlist tracks into M3U8 text and write playlist files."""

import os
from pathlib import Path


def build_m3u8_lines(
    tracks: list[str],
    save_path: Path,
    base_folder: Path | None = None,
) -> list[str]:
    """Build the text lines that will be written to the playlist file."""
    lines = ["#EXTM3U"]

    for track in tracks:
        lines.append("#EXTINF:,")
        lines.append(_resolve_playlist_entry(track, save_path, base_folder))

    return lines


def write_m3u8_playlist(
    tracks: list[str],
    save_path: Path,
    base_folder: Path | None = None,
) -> None:
    """Write a UTF-8 M3U8 playlist to disk."""
    lines = build_m3u8_lines(tracks, save_path, base_folder)
    save_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _resolve_playlist_entry(
    track: str,
    save_path: Path,
    base_folder: Path | None,
) -> str:
    """Return the path entry that should be written for a single track."""
    if base_folder is None:
        return track

    if save_path.parent.resolve() == base_folder.resolve():
        return track

    track_abs = base_folder / track

    try:
        return os.path.relpath(track_abs, save_path.parent)
    except Exception:
        return track
