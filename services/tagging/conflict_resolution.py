"""Purpose: Score lookup candidates, merge proposals, and validate album consistency."""

from __future__ import annotations

from copy import deepcopy
from difflib import SequenceMatcher

from services.tagging.schema import CanonicalTrack, LookupCandidate

AUTO_APPLY_THRESHOLD = 0.90
REVIEW_THRESHOLD = 0.75


def score_candidate(
    candidate: LookupCandidate,
    track: CanonicalTrack,
    parsed_context: dict[str, object] | None = None,
) -> float:
    """Apply weighted scoring using the strongest available signals."""
    context = parsed_context or {}
    title_similarity = _similarity(candidate.title, track.metadata.title or context.get("title"))
    artist_similarity = _similarity(_join(candidate.artist), _join(track.metadata.artist or context.get("artist")))
    album_similarity = _similarity(candidate.album, track.metadata.album or context.get("album"))
    duration_similarity = _duration_similarity(
        candidate.details.get("duration_sec"),
        track.technical.duration_sec,
    )
    track_number_match = _exact_match(candidate.track_number, track.metadata.track_number or context.get("track_number"))
    directory_context_match = _directory_context_match(candidate, context)

    base_confidence = candidate.confidence
    score = (
        0.40 * base_confidence
        + 0.20 * title_similarity
        + 0.15 * artist_similarity
        + 0.10 * album_similarity
        + 0.05 * duration_similarity
        + 0.05 * track_number_match
        + 0.05 * directory_context_match
    )
    return round(score, 4)


def choose_best_candidate(
    candidates: list[LookupCandidate],
    track: CanonicalTrack,
    parsed_context: dict[str, object] | None = None,
) -> tuple[LookupCandidate | None, float]:
    """Return the highest-scoring candidate and its weighted score."""
    best_candidate: LookupCandidate | None = None
    best_score = 0.0
    for candidate in candidates:
        score = score_candidate(candidate, track, parsed_context)
        if score > best_score:
            best_candidate = deepcopy(candidate)
            best_candidate.confidence = score
            best_score = score
    return best_candidate, best_score


def merge_candidate_into_track(track: CanonicalTrack, candidate: LookupCandidate) -> CanonicalTrack:
    """Merge factual candidate metadata into a cloned canonical track."""
    merged = track.clone()
    metadata = merged.metadata

    if candidate.title:
        metadata.title = candidate.title
    if candidate.artist:
        metadata.artist = list(candidate.artist)
    if candidate.album:
        metadata.album = candidate.album
    if candidate.album_artist:
        metadata.album_artist = list(candidate.album_artist)
    if candidate.track_number is not None:
        metadata.track_number = candidate.track_number
    if candidate.disc_number is not None:
        metadata.disc_number = candidate.disc_number
    if candidate.release_date:
        metadata.release_date = candidate.release_date
    if candidate.isrc:
        metadata.isrc = candidate.isrc
    if candidate.musicbrainz_recording_id:
        metadata.musicbrainz_recording_id = candidate.musicbrainz_recording_id
    if candidate.musicbrainz_release_id:
        metadata.musicbrainz_release_id = candidate.musicbrainz_release_id
    if candidate.musicbrainz_release_group_id:
        metadata.musicbrainz_release_group_id = candidate.musicbrainz_release_group_id
    if candidate.musicbrainz_artist_id:
        metadata.musicbrainz_artist_id = list(candidate.musicbrainz_artist_id)

    merged.workflow.tag_confidence = candidate.confidence
    merged.workflow.last_tagged_at = merged.workflow.last_tagged_at or candidate.details.get("timestamp")
    return merged


def review_required_for_score(score: float) -> tuple[bool, list[str]]:
    """Decide whether a candidate should be auto-applied or reviewed."""
    if score >= AUTO_APPLY_THRESHOLD:
        return False, []
    if score >= REVIEW_THRESHOLD:
        return True, ["candidate_confidence_requires_review"]
    return True, ["candidate_confidence_too_low"]


def validate_album_consistency(tracks: list[CanonicalTrack]) -> list[dict[str, object]]:
    """Check album-level fields for mismatches across a set of tracks."""
    album_fields = ["album", "album_artist", "release_date", "disc_total"]
    issues: list[dict[str, object]] = []
    for field_name in album_fields:
        values = {str(getattr(track.metadata, field_name)) for track in tracks if getattr(track.metadata, field_name)}
        if len(values) > 1:
            issues.append(
                {
                    "field": field_name,
                    "values": sorted(values),
                    "severity": "warning",
                }
            )
    return issues


def parse_filename_context(file_path: str) -> dict[str, object]:
    """Infer title, album, artist, and track number from the path layout."""
    path_parts = [part for part in file_path.replace("\\", "/").split("/") if part]
    filename = path_parts[-1]
    stem = filename.rsplit(".", 1)[0]

    parsed = _parse_stem_pattern(stem)
    artist = parsed["artist"]
    album = parsed["album"]
    track_number = parsed["track_number"]
    title = parsed["title"]

    if not album and len(path_parts) >= 2:
        folder_parsed = _parse_album_folder(path_parts[-2])
        album = folder_parsed["album"]
        if not artist:
            artist = folder_parsed["artist"]

    if not album and len(path_parts) >= 2:
        album = path_parts[-2].strip()

    if not artist:
        artist = _infer_artist_from_path(path_parts)

    return {
        "title": title.strip(),
        "album": album.strip() if album else None,
        "artist": artist,
        "track_number": track_number,
    }


def _similarity(left: object, right: object) -> float:
    if not left or not right:
        return 0.0
    return SequenceMatcher(None, str(left).lower(), str(right).lower()).ratio()


def _exact_match(left: object, right: object) -> float:
    return 1.0 if left and right and left == right else 0.0


def _duration_similarity(left: object, right: object) -> float:
    if left is None or right is None:
        return 0.0
    try:
        delta = abs(float(left) - float(right))
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, 1.0 - min(delta / 10.0, 1.0))


def _directory_context_match(candidate: LookupCandidate, context: dict[str, object]) -> float:
    score = 0.0
    if candidate.album and context.get("album") and str(candidate.album).lower() == str(context["album"]).lower():
        score += 0.5
    if candidate.artist and context.get("artist") and _join(candidate.artist).lower() == _join(context["artist"]).lower():
        score += 0.5
    return score


def _join(value: object) -> str:
    if isinstance(value, list):
        return "; ".join(str(item) for item in value)
    return str(value or "")


def _parse_stem_pattern(stem: str) -> dict[str, object]:
    """Handle common filename layouts such as '01 - Title' and 'Artist - Album - 01 Title'."""
    parts = [part.strip() for part in stem.split(" - ")]

    if len(parts) >= 3:
        artist_name = parts[0]
        album_name = parts[1]
        tail = " - ".join(parts[2:])
        tail_track_number, tail_title = _parse_track_prefix(tail)
        return {
            "artist": [artist_name] if artist_name else [],
            "album": album_name or None,
            "track_number": tail_track_number,
            "title": tail_title,
        }

    if len(parts) == 2:
        track_number, title = _parse_track_prefix(stem)
        if track_number is not None:
            return {
                "artist": [],
                "album": None,
                "track_number": track_number,
                "title": title,
            }

    track_number, title = _parse_track_prefix(stem)
    return {
        "artist": [],
        "album": None,
        "track_number": track_number,
        "title": title,
    }


def _parse_album_folder(folder_name: str) -> dict[str, object]:
    """Parse folder names such as 'Artist - Album'."""
    parts = [part.strip() for part in folder_name.split(" - ")]
    if len(parts) >= 2:
        return {
            "artist": [parts[0]] if parts[0] else [],
            "album": parts[1] or None,
        }
    return {
        "artist": [],
        "album": folder_name.strip() or None,
    }


def _infer_artist_from_path(path_parts: list[str]) -> list[str]:
    """Choose the nearest useful parent folder and ignore common source folders."""
    ignored = {"Bandcamp", "Digital", "Music", "Downloads", "Audio", "Lossless", "Lossy"}
    for part in reversed(path_parts[:-2]):
        cleaned = part.strip()
        if cleaned and cleaned not in ignored:
            return [cleaned]
    return []


def _parse_track_prefix(value: str) -> tuple[int | None, str]:
    """Extract leading track numbers from strings like '01 title' or '01 - title'."""
    stripped = value.strip()
    if not stripped:
        return None, value

    if " - " in stripped:
        prefix, suffix = stripped.split(" - ", 1)
        if prefix.isdigit():
            return int(prefix), suffix.strip()

    if " " in stripped:
        prefix, suffix = stripped.split(" ", 1)
        if prefix.isdigit():
            return int(prefix), suffix.strip()

    if stripped.isdigit():
        return int(stripped), stripped

    return None, stripped
