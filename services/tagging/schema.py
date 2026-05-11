"""Purpose: Define canonical tagging models that stay stable across file formats."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


def utc_now_iso() -> str:
    """Return a UTC timestamp string suitable for audit and provenance records."""
    return datetime.now(timezone.utc).isoformat()


@dataclass
class TrackMetadata:
    """Canonical track and release identity fields."""

    title: str | None = None
    artist: list[str] = field(default_factory=list)
    album: str | None = None
    album_artist: list[str] = field(default_factory=list)
    track_number: int | None = None
    track_total: int | None = None
    disc_number: int | None = None
    disc_total: int | None = None
    release_date: str | None = None
    original_date: str | None = None
    genre: list[str] = field(default_factory=list)
    subgenre: list[str] = field(default_factory=list)
    composer: list[str] = field(default_factory=list)
    comment: str | None = None
    grouping: str | None = None
    label: str | None = None
    copyright: str | None = None
    isrc: str | None = None
    musicbrainz_recording_id: str | None = None
    musicbrainz_release_id: str | None = None
    musicbrainz_release_group_id: str | None = None
    musicbrainz_artist_id: list[str] = field(default_factory=list)
    discogs_release_id: str | None = None
    barcode: str | None = None
    catalog_number: str | None = None


@dataclass
class ContentTags:
    """Canonical descriptive tags that describe how the audio sounds."""

    mood: list[str] = field(default_factory=list)
    energy: str | None = None
    bpm: int | None = None
    key: str | None = None
    vocal_presence: str | None = None
    vocal_type: list[str] = field(default_factory=list)
    instruments: list[str] = field(default_factory=list)
    language: list[str] = field(default_factory=list)
    era: list[str] = field(default_factory=list)
    use_case: list[str] = field(default_factory=list)
    texture: list[str] = field(default_factory=list)
    explicitness: str | None = None


@dataclass
class TechnicalMetadata:
    """Technical audio properties read from the file container."""

    duration_sec: float | None = None
    bitrate_kbps: int | None = None
    sample_rate: int | None = None
    channels: int | None = None
    file_size_bytes: int | None = None
    codec: str | None = None


@dataclass
class WorkflowMetadata:
    """Application-level workflow metadata that should not blindly overwrite tags."""

    rating: int | None = None
    favorite: bool | None = None
    review_status: str = "untagged"
    source: str | None = None
    quality_status: str | None = None
    duplicate_group_id: str | None = None
    last_tagged_at: str | None = None
    tag_confidence: float | None = None
    needs_review: bool = False


@dataclass
class CanonicalTrack:
    """A complete canonical representation of one audio file and its tags."""

    file_path: str
    file_format: str
    metadata: TrackMetadata = field(default_factory=TrackMetadata)
    content_tags: ContentTags = field(default_factory=ContentTags)
    technical: TechnicalMetadata = field(default_factory=TechnicalMetadata)
    workflow: WorkflowMetadata = field(default_factory=WorkflowMetadata)
    raw_tags: dict[str, list[str]] = field(default_factory=dict)
    custom_tags: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialize the track into JSON-safe primitives."""
        return asdict(self)

    def clone(self) -> "CanonicalTrack":
        """Return a deep-ish copy that is safe to mutate."""
        return CanonicalTrack.from_dict(self.to_dict())

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "CanonicalTrack":
        """Build a canonical track from serialized data."""
        return cls(
            file_path=payload["file_path"],
            file_format=payload["file_format"],
            metadata=TrackMetadata(**payload.get("metadata", {})),
            content_tags=ContentTags(**payload.get("content_tags", {})),
            technical=TechnicalMetadata(**payload.get("technical", {})),
            workflow=WorkflowMetadata(**payload.get("workflow", {})),
            raw_tags=payload.get("raw_tags", {}),
            custom_tags=payload.get("custom_tags", {}),
            warnings=payload.get("warnings", []),
        )


@dataclass
class LookupCandidate:
    """A possible factual metadata match from a parser or external source."""

    source: str
    title: str | None = None
    artist: list[str] = field(default_factory=list)
    album: str | None = None
    album_artist: list[str] = field(default_factory=list)
    track_number: int | None = None
    track_total: int | None = None
    disc_number: int | None = None
    disc_total: int | None = None
    release_date: str | None = None
    original_date: str | None = None
    isrc: str | None = None
    musicbrainz_recording_id: str | None = None
    musicbrainz_release_id: str | None = None
    musicbrainz_release_group_id: str | None = None
    musicbrainz_artist_id: list[str] = field(default_factory=list)
    discogs_release_id: str | None = None
    label: str | None = None
    barcode: str | None = None
    catalog_number: str | None = None
    confidence: float = 0.0
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class FieldDiff:
    """One field change in a dry-run or applied tagging diff."""

    field_path: str
    before: Any
    after: Any

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class DiffReport:
    """A report describing what would change and whether review is needed."""

    file_path: str
    result_file_path: str | None = None
    created_at: str = field(default_factory=utc_now_iso)
    changes: list[FieldDiff] = field(default_factory=list)
    review_required: bool = False
    reasons: list[str] = field(default_factory=list)
    auto_apply_confidence: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "file_path": self.file_path,
            "result_file_path": self.result_file_path,
            "created_at": self.created_at,
            "changes": [change.to_dict() for change in self.changes],
            "review_required": self.review_required,
            "reasons": self.reasons,
            "auto_apply_confidence": self.auto_apply_confidence,
        }
