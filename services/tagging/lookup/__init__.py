"""Purpose: Expose factual metadata lookup clients for the tagging package."""

from services.tagging.lookup.acoustid_client import AcoustIdLookupClient
from services.tagging.lookup.discogs_client import DiscogsLookupClient
from services.tagging.lookup.musicbrainz_client import MusicBrainzLookupClient

__all__ = ["AcoustIdLookupClient", "DiscogsLookupClient", "MusicBrainzLookupClient"]
