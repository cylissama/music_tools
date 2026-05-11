"""Purpose: Store the application's plain-Python state and simple data helpers."""

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class TrackScanMetadata:
    """Lightweight metadata captured during a library scan for fast UI display."""

    relative_path: str
    file_name: str
    title: str | None = None
    artist: list[str] = field(default_factory=list)
    album: str | None = None
    genre: list[str] = field(default_factory=list)
    track_number: int | None = None
    release_date: str | None = None

    @property
    def display_name(self) -> str:
        if not self.title:
            return self.file_name

        prefix = f"{self.track_number:02d} " if self.track_number is not None else ""
        artist_suffix = f" - {', '.join(self.artist)}" if self.artist else ""
        return f"{prefix}{self.title}{artist_suffix}"

    @property
    def tooltip_text(self) -> str:
        lines = [f"Path: {self.relative_path}"]
        lines.append(f"Title: {self.title or '(missing)'}")
        lines.append(f"Artist: {', '.join(self.artist) if self.artist else '(missing)'}")
        lines.append(f"Album: {self.album or '(missing)'}")
        lines.append(f"Genre: {', '.join(self.genre) if self.genre else '(missing)'}")
        lines.append(f"Release date: {self.release_date or '(missing)'}")
        return "\n".join(lines)


@dataclass
class LibraryAlbum:
    """A scanned folder that contains audio files and acts like one library item."""

    folder_path: str
    track_count: int
    tracks: list[str]
    track_metadata: dict[str, TrackScanMetadata] = field(default_factory=dict)

    @property
    def display_name(self) -> str:
        """Return the text shown in the library list."""
        suffix = "file" if self.track_count == 1 else "files"
        return f"{self.folder_path} ({self.track_count} {suffix})"


@dataclass
class PlaylistState:
    """Application state that the UI reads from and writes to."""

    music_directories: list[Path] = field(default_factory=list)
    root_folder: Path | None = None
    library_base_folder: Path | None = None
    library_albums: list[LibraryAlbum] = field(default_factory=list)
    playlist_tracks: list[str] = field(default_factory=list)

    def set_music_directories(self, folders: list[Path]) -> None:
        self.music_directories = folders

    def set_root_folder(self, folder: Path | None) -> None:
        self.root_folder = folder

    def add_music_directory(self, folder: Path) -> bool:
        if folder in self.music_directories:
            return False
        self.music_directories.append(folder)
        return True

    def remove_music_directory(self, folder: Path) -> bool:
        if folder not in self.music_directories:
            return False
        self.music_directories.remove(folder)
        if self.root_folder == folder:
            self.root_folder = None
        return True

    def set_library(self, albums: list[LibraryAlbum], base_folder: Path) -> None:
        self.library_albums = albums
        self.library_base_folder = base_folder

    def clear_library(self) -> None:
        self.library_albums.clear()
        self.library_base_folder = None

    def add_tracks_to_playlist(self, tracks: list[str]) -> None:
        self.playlist_tracks.extend(tracks)

    def remove_playlist_track(self, index: int) -> None:
        if 0 <= index < len(self.playlist_tracks):
            self.playlist_tracks.pop(index)

    def move_playlist_track(self, old_index: int, new_index: int) -> None:
        if not 0 <= old_index < len(self.playlist_tracks):
            return
        if not 0 <= new_index < len(self.playlist_tracks):
            return

        track = self.playlist_tracks.pop(old_index)
        self.playlist_tracks.insert(new_index, track)

    def clear_playlist(self) -> None:
        self.playlist_tracks.clear()
