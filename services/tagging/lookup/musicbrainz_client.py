"""Purpose: Query MusicBrainz for factual release and recording metadata candidates."""

from __future__ import annotations

from services.tagging.schema import LookupCandidate

try:
    import musicbrainzngs
except ImportError:  # pragma: no cover - handled at runtime
    musicbrainzngs = None

USER_AGENT = ("walkman-playlist-creator", "0.1.0", "local-app")


class MusicBrainzLookupClient:
    """Small wrapper around musicbrainzngs for candidate generation."""

    def __init__(self) -> None:
        if musicbrainzngs is not None:
            musicbrainzngs.set_useragent(*USER_AGENT)

    def available(self) -> bool:
        return musicbrainzngs is not None

    def lookup_by_recording_id(self, recording_id: str) -> list[LookupCandidate]:
        """Lookup a recording directly from an embedded MusicBrainz id."""
        if musicbrainzngs is None or not recording_id:
            return []

        try:
            result = musicbrainzngs.get_recording_by_id(
                recording_id,
                includes=["artists", "releases"],
            )
        except Exception:
            return []

        recording = result.get("recording", {})
        artist_credit = recording.get("artist-credit", [])
        release_list = recording.get("release-list", [])
        candidates: list[LookupCandidate] = []

        for release in release_list[:5]:
            medium_list = release.get("medium-list", [])
            track_number = None
            track_total = None
            disc_number = None
            disc_total = _safe_int(release.get("medium-count")) or (len(medium_list) if medium_list else None)
            if medium_list:
                disc_number = _safe_int(medium_list[0].get("position"))
                for medium in medium_list:
                    for track in medium.get("track-list", []):
                        recording_ref = track.get("recording", {}).get("id")
                        if recording_ref == recording.get("id"):
                            track_number = _safe_int(track.get("position") or track.get("number"))
                            disc_number = _safe_int(medium.get("position")) or disc_number
                            track_total = _safe_int(medium.get("track-count")) or track_total
                            break
                    if track_number is not None:
                        break

            candidates.append(
                LookupCandidate(
                    source="musicbrainz_recording_id",
                    title=recording.get("title"),
                    artist=[credit.get("artist", {}).get("name", "") for credit in artist_credit if isinstance(credit, dict)],
                    album=release.get("title"),
                    album_artist=[credit.get("artist", {}).get("name", "") for credit in artist_credit if isinstance(credit, dict)],
                    track_number=track_number,
                    track_total=track_total,
                    disc_number=disc_number,
                    disc_total=disc_total,
                    release_date=release.get("date"),
                    original_date=release.get("release-group", {}).get("first-release-date"),
                    musicbrainz_recording_id=recording.get("id"),
                    musicbrainz_release_id=release.get("id"),
                    musicbrainz_release_group_id=release.get("release-group", {}).get("id"),
                    confidence=1.0,
                    details={"source": "musicbrainz_recording_id"},
                )
            )

        return candidates

    def search_recordings(self, title: str, artist: str | None = None, album: str | None = None) -> list[LookupCandidate]:
        """Search MusicBrainz textually when IDs are unavailable."""
        if musicbrainzngs is None or not title:
            return []

        query = [f'recording:"{title}"']
        if artist:
            query.append(f'artist:"{artist}"')
        if album:
            query.append(f'release:"{album}"')

        try:
            result = musicbrainzngs.search_recordings(query=" AND ".join(query), limit=5)
        except Exception:
            return []

        candidates: list[LookupCandidate] = []
        for recording in result.get("recording-list", []):
            artist_credit = recording.get("artist-credit", [])
            release_list = recording.get("release-list", [])
            first_release = release_list[0] if release_list else {}
            candidates.append(
                LookupCandidate(
                    source="musicbrainz_search",
                    title=recording.get("title"),
                    artist=[credit.get("artist", {}).get("name", "") for credit in artist_credit if isinstance(credit, dict)],
                    album=first_release.get("title"),
                    album_artist=[credit.get("artist", {}).get("name", "") for credit in artist_credit if isinstance(credit, dict)],
                    disc_total=_safe_int(first_release.get("medium-count")),
                    release_date=first_release.get("date"),
                    original_date=first_release.get("release-group", {}).get("first-release-date"),
                    musicbrainz_recording_id=recording.get("id"),
                    musicbrainz_release_id=first_release.get("id"),
                    musicbrainz_release_group_id=first_release.get("release-group", {}).get("id"),
                    confidence=0.6,
                    details={"source": "musicbrainz_search"},
                )
            )
        return candidates


def _safe_int(value) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None
