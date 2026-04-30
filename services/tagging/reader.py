"""Purpose: Read audio file tags into the canonical tagging schema."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from services.tagging.schema import CanonicalTrack

try:
    from mutagen import File as MutagenFile
    from mutagen.mp3 import MP3
    from mutagen.mp4 import MP4
except ImportError:  # pragma: no cover - handled at runtime
    MutagenFile = None
    MP3 = None
    MP4 = None


def read_canonical_metadata(path: str | Path) -> CanonicalTrack:
    """Read one audio file into the canonical track structure."""
    _require_mutagen()

    file_path = Path(path)
    mutagen_file = MutagenFile(file_path)
    if mutagen_file is None:
        raise ValueError(f"Unsupported or unreadable audio file: {file_path}")

    track = CanonicalTrack(
        file_path=str(file_path),
        file_format=_detect_format(mutagen_file, file_path),
    )
    track.technical.file_size_bytes = file_path.stat().st_size
    track.technical.duration_sec = _safe_float(getattr(mutagen_file.info, "length", None))
    track.technical.sample_rate = _safe_int(getattr(mutagen_file.info, "sample_rate", None))
    track.technical.channels = _safe_int(getattr(mutagen_file.info, "channels", None))
    track.technical.bitrate_kbps = _read_bitrate(mutagen_file)
    track.technical.codec = track.file_format

    raw_tags = _extract_raw_tags(mutagen_file)
    track.raw_tags = raw_tags

    metadata = track.metadata
    content = track.content_tags

    metadata.title = _first(raw_tags, "title", "TITLE", "\xa9nam", "TIT2")
    metadata.artist = _multi(raw_tags, "artist", "ARTIST", "\xa9ART", "TPE1")
    metadata.album = _first(raw_tags, "album", "ALBUM", "\xa9alb", "TALB")
    metadata.album_artist = _multi(raw_tags, "albumartist", "album artist", "ALBUMARTIST", "aART", "TPE2")
    metadata.track_number, metadata.track_total = _split_pair(
        _first(raw_tags, "tracknumber", "TRACKNUMBER", "trkn", "TRCK")
    )
    metadata.disc_number, metadata.disc_total = _split_pair(
        _first(raw_tags, "discnumber", "DISCNUMBER", "disk", "TPOS")
    )
    metadata.release_date = _first(raw_tags, "date", "DATE", "\xa9day", "TDRC")
    metadata.original_date = _first(raw_tags, "originaldate", "ORIGINALDATE", "TDOR")
    metadata.genre = _multi(raw_tags, "genre", "GENRE", "\xa9gen", "TCON")
    metadata.subgenre = _multi(raw_tags, "style", "STYLE", "SUBGENRE")
    metadata.composer = _multi(raw_tags, "composer", "COMPOSER", "\xa9wrt", "TCOM")
    metadata.comment = _first(raw_tags, "comment", "COMMENT", "\xa9cmt", "COMM")
    metadata.grouping = _first(raw_tags, "grouping", "GROUPING", "\xa9grp", "TIT1")
    metadata.label = _first(raw_tags, "label", "LABEL")
    metadata.copyright = _first(raw_tags, "copyright", "COPYRIGHT", "cprt", "TCOP")
    metadata.isrc = _first(raw_tags, "isrc", "ISRC", "TSRC")
    metadata.musicbrainz_recording_id = _first(
        raw_tags,
        "musicbrainz_trackid",
        "MUSICBRAINZ_TRACKID",
        "TXXX:MusicBrainz Track Id",
        "----:com.apple.iTunes:MusicBrainz Track Id",
    )
    metadata.musicbrainz_release_id = _first(
        raw_tags,
        "musicbrainz_albumid",
        "MUSICBRAINZ_ALBUMID",
        "TXXX:MusicBrainz Album Id",
        "----:com.apple.iTunes:MusicBrainz Album Id",
    )
    metadata.musicbrainz_release_group_id = _first(
        raw_tags,
        "musicbrainz_releasegroupid",
        "MUSICBRAINZ_RELEASEGROUPID",
        "TXXX:MusicBrainz Release Group Id",
        "----:com.apple.iTunes:MusicBrainz Release Group Id",
    )
    metadata.musicbrainz_artist_id = _multi(
        raw_tags,
        "musicbrainz_artistid",
        "MUSICBRAINZ_ARTISTID",
        "TXXX:MusicBrainz Artist Id",
    )
    metadata.discogs_release_id = _first(
        raw_tags,
        "discogs_release_id",
        "DISCOGS_RELEASE_ID",
        "TXXX:Discogs Release Id",
        "----:com.apple.iTunes:Discogs Release Id",
    )
    metadata.barcode = _first(
        raw_tags,
        "barcode",
        "BARCODE",
        "TXXX:BARCODE",
        "----:com.apple.iTunes:BARCODE",
    )
    metadata.catalog_number = _first(
        raw_tags,
        "catalognumber",
        "catalog_number",
        "CATALOGNUMBER",
        "TXXX:Catalog Number",
        "----:com.apple.iTunes:Catalog Number",
    )

    content.mood = _multi(raw_tags, "mood", "MOOD", "TMOO")
    content.energy = _first(raw_tags, "energy", "ENERGY")
    content.bpm = _safe_int(_first(raw_tags, "bpm", "BPM", "tmpo", "TBPM"))
    content.key = _first(raw_tags, "initialkey", "INITIALKEY", "TKEY")
    content.vocal_presence = _first(raw_tags, "vocalpresence", "VOCALPRESENCE")
    content.instruments = _multi(raw_tags, "instruments", "INSTRUMENTS")
    content.language = _multi(raw_tags, "language", "LANGUAGE")

    track.custom_tags = _extract_custom_tags(raw_tags)
    return track


def _require_mutagen() -> None:
    if MutagenFile is None:
        raise RuntimeError("Mutagen is required for tagging features. Install it with `pip install mutagen`.")


def _detect_format(mutagen_file: Any, path: Path) -> str:
    if MP3 is not None and isinstance(mutagen_file, MP3):
        return "MP3"
    if MP4 is not None and isinstance(mutagen_file, MP4):
        return "MP4"
    return path.suffix.lstrip(".").upper() or "UNKNOWN"


def _extract_raw_tags(mutagen_file: Any) -> dict[str, list[str]]:
    if not getattr(mutagen_file, "tags", None):
        return {}

    raw: dict[str, list[str]] = {}
    for key in mutagen_file.tags.keys():
        values = _normalize_tag_values(mutagen_file.tags[key])
        if values:
            raw[str(key)] = values
    return raw


def _normalize_tag_values(value: Any) -> list[str]:
    if isinstance(value, list):
        normalized: list[str] = []
        for item in value:
            normalized.extend(_normalize_tag_values(item))
        return normalized

    if hasattr(value, "text"):
        return [str(item) for item in getattr(value, "text", [])]

    if isinstance(value, tuple):
        return ["/".join(str(item) for item in value)]

    if isinstance(value, bytes):
        return [value.decode("utf-8", errors="replace")]

    return [str(value)]


def _extract_custom_tags(raw_tags: dict[str, list[str]]) -> dict[str, Any]:
    canonical_keys = {
        "title",
        "artist",
        "album",
        "albumartist",
        "album artist",
        "tracknumber",
        "discnumber",
        "date",
        "genre",
        "composer",
        "comment",
        "grouping",
        "copyright",
        "isrc",
        "musicbrainz_trackid",
        "musicbrainz_albumid",
        "musicbrainz_releasegroupid",
        "musicbrainz_artistid",
        "discogs_release_id",
        "barcode",
        "catalognumber",
        "catalog_number",
        "style",
        "bpm",
        "initialkey",
        "mood",
        "energy",
        "language",
        "instruments",
        "\xa9nam",
        "\xa9ART",
        "\xa9alb",
        "\xa9day",
        "\xa9gen",
        "\xa9wrt",
        "\xa9cmt",
        "\xa9grp",
        "aART",
        "cprt",
        "trkn",
        "disk",
        "tmpo",
        "TIT2",
        "TPE1",
        "TALB",
        "TPE2",
        "TDRC",
        "TCON",
        "TCOM",
        "COMM",
        "TIT1",
        "TCOP",
        "TSRC",
        "TBPM",
        "TKEY",
        "TMOO",
        "TXXX:Discogs Release Id",
        "TXXX:Catalog Number",
        "----:com.apple.iTunes:MusicBrainz Track Id",
        "----:com.apple.iTunes:MusicBrainz Album Id",
        "----:com.apple.iTunes:MusicBrainz Release Group Id",
        "----:com.apple.iTunes:Discogs Release Id",
        "----:com.apple.iTunes:BARCODE",
        "----:com.apple.iTunes:Catalog Number",
    }
    return {key: value for key, value in raw_tags.items() if key not in canonical_keys}


def _first(raw_tags: dict[str, list[str]], *keys: str) -> str | None:
    for key in _matching_keys(raw_tags, *keys):
        if raw_tags[key]:
            return raw_tags[key][0]
    return None


def _multi(raw_tags: dict[str, list[str]], *keys: str) -> list[str]:
    values: list[str] = []
    for key in _matching_keys(raw_tags, *keys):
        values.extend(raw_tags.get(key, []))
    return _dedupe(values)


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            deduped.append(value)
    return deduped


def _split_pair(value: str | None) -> tuple[int | None, int | None]:
    if not value:
        return None, None

    if "/" in value:
        left, right = value.split("/", 1)
        return _safe_int(left), _safe_int(right)

    return _safe_int(value), None


def _read_bitrate(mutagen_file: Any) -> int | None:
    bitrate = getattr(mutagen_file.info, "bitrate", None)
    if bitrate is None:
        return None
    return int(round(float(bitrate) / 1000))


def _safe_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, tuple):
        value = value[0]
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None


def _safe_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _matching_keys(raw_tags: dict[str, list[str]], *keys: str) -> list[str]:
    matched: list[str] = []
    lowered = {raw_key.lower(): raw_key for raw_key in raw_tags}
    for key in keys:
        direct = lowered.get(key.lower())
        if direct is not None:
            matched.append(direct)
            continue

        for raw_key in raw_tags:
            raw_lower = raw_key.lower()
            if raw_lower.startswith(f"{key.lower()}:") or raw_lower.startswith(f"{key.lower()}::"):
                matched.append(raw_key)
    return _dedupe(matched)
