"""Purpose: Query AcoustID for fingerprint-based track identification candidates."""

from __future__ import annotations

from pathlib import Path

from services.tagging.schema import LookupCandidate

try:
    import acoustid
except ImportError:  # pragma: no cover - handled at runtime
    acoustid = None


class AcoustIdLookupClient:
    """Wrapper around pyacoustid with safe no-op behavior when unavailable."""

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key

    def available(self) -> bool:
        return acoustid is not None and bool(self.api_key)

    def lookup_file(self, file_path: str | Path) -> list[LookupCandidate]:
        """Fingerprint a file and convert results into canonical lookup candidates."""
        if acoustid is None or not self.api_key:
            return []

        try:
            results = acoustid.match(self.api_key, str(file_path))
        except Exception:
            return []

        candidates: list[LookupCandidate] = []
        for index, match in enumerate(results):
            if index >= 5:
                break

            if isinstance(match, tuple) and len(match) >= 4:
                score, recording_id, title, artist = match[:4]
            else:
                continue

            candidates.append(
                LookupCandidate(
                    source="acoustid",
                    title=title,
                    artist=[artist] if artist else [],
                    musicbrainz_recording_id=recording_id,
                    confidence=float(score),
                    details={"source": "acoustid"},
                )
            )
        return candidates
