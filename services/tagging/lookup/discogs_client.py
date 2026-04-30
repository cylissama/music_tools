"""Purpose: Query Discogs for secondary release metadata candidates."""

from __future__ import annotations

import json
import urllib.parse
import urllib.request

from services.tagging.schema import LookupCandidate

USER_AGENT = "walkman-playlist-creator/0.1.0"
API_BASE_URL = "https://api.discogs.com/database/search"


class DiscogsLookupClient:
    """Small HTTP client for Discogs release search."""

    def __init__(self, user_token: str | None = None) -> None:
        self.user_token = user_token

    def available(self) -> bool:
        return bool(self.user_token)

    def search_releases(
        self,
        *,
        title: str,
        artist: str | None = None,
        album: str | None = None,
    ) -> list[LookupCandidate]:
        """Search Discogs for release candidates using parsed file context."""
        if not self.user_token or not title:
            return []

        params = {
            "type": "release",
            "track": title,
            "per_page": "5",
        }
        if artist:
            params["artist"] = artist
        if album:
            params["release_title"] = album

        request_url = f"{API_BASE_URL}?{urllib.parse.urlencode(params)}"
        request = urllib.request.Request(
            request_url,
            headers={
                "User-Agent": USER_AGENT,
                "Authorization": f"Discogs token={self.user_token}",
            },
        )

        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except Exception:
            return []

        candidates: list[LookupCandidate] = []
        for result in payload.get("results", [])[:5]:
            result_title = str(result.get("title", "")).strip()
            result_artist, result_album = _split_discogs_title(result_title)
            resolved_artist = result_artist or artist
            resolved_album = result_album or album

            candidates.append(
                LookupCandidate(
                    source="discogs_search",
                    title=title,
                    artist=[resolved_artist] if resolved_artist else [],
                    album=resolved_album,
                    album_artist=[resolved_artist] if resolved_artist else [],
                    release_date=str(result.get("year")) if result.get("year") else None,
                    discogs_release_id=str(result.get("id")) if result.get("id") else None,
                    label=_first_list_value(result.get("label")),
                    barcode=_first_list_value(result.get("barcode")),
                    catalog_number=_first_list_value(result.get("catno")),
                    confidence=0.58,
                    details={"source": "discogs_search"},
                )
            )
        return candidates


def _first_list_value(value) -> str | None:
    if isinstance(value, list):
        return str(value[0]) if value else None
    if value in (None, ""):
        return None
    return str(value)


def _split_discogs_title(title: str) -> tuple[str | None, str | None]:
    if " - " not in title:
        return None, title or None
    artist, album = title.split(" - ", 1)
    return artist.strip() or None, album.strip() or None
