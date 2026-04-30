"""Purpose: Normalize tag values into controlled vocabularies and stable aliases."""

from __future__ import annotations

from services.tagging.schema import CanonicalTrack

CONTROLLED_VOCABULARY = {
    "genre": {
        "hip hop": "Hip-Hop",
        "hip-hop": "Hip-Hop",
        "hiphop": "Hip-Hop",
        "rnb": "R&B",
        "rhythm and blues": "R&B",
        "r & b": "R&B",
        "electronic": "Electronic",
        "rock": "Rock",
        "pop": "Pop",
        "jazz": "Jazz",
        "classical": "Classical",
        "metal": "Metal",
        "soundtrack": "Soundtrack",
    },
    "mood": {
        "upbeat": "Energetic",
        "high energy": "Energetic",
        "energetic": "Energetic",
        "sad": "Melancholic",
        "somber": "Melancholic",
        "melancholic": "Melancholic",
        "calm": "Calm",
        "dark": "Dark",
        "uplifting": "Uplifting",
    },
    "energy": {
        "low": "Low",
        "medium": "Medium",
        "high": "High",
    },
    "vocal_presence": {
        "instrumental": "Instrumental",
        "vocal": "Vocal",
        "spoken word": "Spoken Word",
        "choir": "Choir",
        "unknown": "Unknown",
    },
}


def normalize_track_tags(track: CanonicalTrack) -> CanonicalTrack:
    """Return a cloned track with controlled vocabulary applied."""
    normalized = track.clone()
    normalized.metadata.genre = normalize_values("genre", normalized.metadata.genre)
    normalized.content_tags.mood = normalize_values("mood", normalized.content_tags.mood)
    normalized.content_tags.energy = normalize_scalar("energy", normalized.content_tags.energy)
    normalized.content_tags.vocal_presence = normalize_scalar(
        "vocal_presence",
        normalized.content_tags.vocal_presence,
    )
    normalized.content_tags.instruments = _title_case_list(normalized.content_tags.instruments)
    normalized.content_tags.language = _title_case_list(normalized.content_tags.language)
    return normalized


def normalize_values(category: str, values: list[str]) -> list[str]:
    """Normalize a list of values through the chosen controlled vocabulary."""
    seen: set[str] = set()
    normalized: list[str] = []
    for value in values:
        mapped = _normalize_value(category, value)
        if mapped and mapped not in seen:
            seen.add(mapped)
            normalized.append(mapped)
    return normalized


def normalize_scalar(category: str, value: str | None) -> str | None:
    """Normalize a single tag value."""
    if value is None:
        return None
    return _normalize_value(category, value)


def _normalize_value(category: str, value: str) -> str:
    aliases = CONTROLLED_VOCABULARY.get(category, {})
    key = value.strip().lower()
    if key in aliases:
        return aliases[key]
    return value.strip().title()


def _title_case_list(values: list[str]) -> list[str]:
    return [value.strip().title() for value in values if value.strip()]
