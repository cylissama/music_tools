"""Purpose: Safely write canonical metadata back to audio files with verification."""

from __future__ import annotations

from services.tagging.audit_store import TaggingAuditStore
from services.tagging.diff_report import build_diff_report
from services.tagging.mappings import MP4_FIELD_MAP, VORBIS_FIELD_MAP
from services.tagging.reader import read_canonical_metadata
from services.tagging.schema import CanonicalTrack, DiffReport

try:
    from mutagen import File as MutagenFile
    from mutagen.flac import FLAC
    from mutagen.id3 import COMM, TALB, TBPM, TCOM, TCON, TCOP, TDRC, TIT1, TIT2, TKEY, TMOO, TPE1, TPE2, TPOS, TRCK, TSRC, TXXX
    from mutagen.mp3 import MP3
    from mutagen.mp4 import MP4, MP4FreeForm
    from mutagen.oggopus import OggOpus
    from mutagen.oggvorbis import OggVorbis
except ImportError:  # pragma: no cover - handled at runtime
    MutagenFile = None
    FLAC = None
    MP3 = None
    MP4 = None
    OggVorbis = None
    OggOpus = None


def write_canonical_metadata(
    proposed_track: CanonicalTrack,
    *,
    audit_store: TaggingAuditStore,
    source: str,
    dry_run: bool = False,
) -> DiffReport:
    """Write canonical metadata with a snapshot, diff, and post-write verification."""
    before = read_canonical_metadata(proposed_track.file_path)
    diff_report = build_diff_report(before, proposed_track)

    status = "dry_run" if dry_run else "pending_write"
    audit_store.record_snapshot(
        file_path=proposed_track.file_path,
        before=before,
        after=proposed_track,
        diff_report=diff_report,
        status=status,
        source=source,
    )

    if dry_run or not diff_report.changes:
        return diff_report

    _require_mutagen()
    mutagen_file = MutagenFile(proposed_track.file_path)
    if mutagen_file is None:
        raise ValueError(f"Unsupported or unreadable audio file: {proposed_track.file_path}")

    _write_by_format(mutagen_file, proposed_track)
    mutagen_file.save()

    after = read_canonical_metadata(proposed_track.file_path)
    verification_diff = build_diff_report(proposed_track, after)
    if verification_diff.changes:
        audit_store.record_snapshot(
            file_path=proposed_track.file_path,
            before=before,
            after=after,
            diff_report=verification_diff,
            status="verification_failed",
            source=source,
        )
        raise ValueError("Post-write verification failed; file contents differ from the proposed tags.")

    audit_store.record_snapshot(
        file_path=proposed_track.file_path,
        before=before,
        after=after,
        diff_report=build_diff_report(before, after),
        status="written",
        source=source,
    )
    return build_diff_report(before, after)


def _require_mutagen() -> None:
    if MutagenFile is None:
        raise RuntimeError("Mutagen is required for tagging features. Install it with `pip install mutagen`.")


def _write_by_format(mutagen_file, track: CanonicalTrack) -> None:
    if FLAC is not None and isinstance(mutagen_file, FLAC):
        _write_vorbis_style(mutagen_file, track)
        return

    if OggVorbis is not None and isinstance(mutagen_file, OggVorbis):
        _write_vorbis_style(mutagen_file, track)
        return

    if OggOpus is not None and isinstance(mutagen_file, OggOpus):
        _write_vorbis_style(mutagen_file, track)
        return

    if MP3 is not None and isinstance(mutagen_file, MP3):
        _write_mp3(mutagen_file, track)
        return

    if MP4 is not None and isinstance(mutagen_file, MP4):
        _write_mp4(mutagen_file, track)
        return

    raise ValueError(f"Writing tags is not implemented for format {track.file_format}")


def _write_vorbis_style(mutagen_file, track: CanonicalTrack) -> None:
    fields = _canonical_field_values(track)
    for field, key in VORBIS_FIELD_MAP.items():
        value = fields.get(field)
        if value is None or value == []:
            if key in mutagen_file:
                del mutagen_file[key]
            continue

        if isinstance(value, list):
            mutagen_file[key] = [str(item) for item in value]
        else:
            mutagen_file[key] = [str(value)]

    _preserve_custom_tags(mutagen_file, track)


def _write_mp4(mutagen_file, track: CanonicalTrack) -> None:
    fields = _canonical_field_values(track)
    for field, atom in MP4_FIELD_MAP.items():
        value = fields.get(field)
        if value is None or value == []:
            if atom in mutagen_file:
                del mutagen_file[atom]
            continue

        if field == "bpm":
            mutagen_file[atom] = [int(value)]
        elif isinstance(value, list):
            mutagen_file[atom] = list(value)
        else:
            mutagen_file[atom] = [value]

    if track.metadata.track_number or track.metadata.track_total:
        mutagen_file["trkn"] = [(track.metadata.track_number or 0, track.metadata.track_total or 0)]
    if track.metadata.disc_number or track.metadata.disc_total:
        mutagen_file["disk"] = [(track.metadata.disc_number or 0, track.metadata.disc_total or 0)]

    _set_mp4_freeform(mutagen_file, "----:com.apple.iTunes:ISRC", track.metadata.isrc)
    _set_mp4_freeform(
        mutagen_file,
        "----:com.apple.iTunes:MusicBrainz Track Id",
        track.metadata.musicbrainz_recording_id,
    )
    _set_mp4_freeform(
        mutagen_file,
        "----:com.apple.iTunes:MusicBrainz Album Id",
        track.metadata.musicbrainz_release_id,
    )
    _set_mp4_freeform(
        mutagen_file,
        "----:com.apple.iTunes:MusicBrainz Release Group Id",
        track.metadata.musicbrainz_release_group_id,
    )
    _set_mp4_freeform(mutagen_file, "----:com.apple.iTunes:BARCODE", track.metadata.barcode)
    _set_mp4_freeform(
        mutagen_file,
        "----:com.apple.iTunes:MOOD",
        "; ".join(track.content_tags.mood) if track.content_tags.mood else None,
    )


def _write_mp3(mutagen_file, track: CanonicalTrack) -> None:
    tags = mutagen_file.tags
    if tags is None:
        mutagen_file.add_tags()
        tags = mutagen_file.tags

    _set_id3_text(tags, TIT2, track.metadata.title)
    _set_id3_text(tags, TPE1, track.metadata.artist)
    _set_id3_text(tags, TALB, track.metadata.album)
    _set_id3_text(tags, TPE2, track.metadata.album_artist)
    _set_id3_text(tags, TDRC, track.metadata.release_date)
    _set_id3_text(tags, TCON, track.metadata.genre)
    _set_id3_text(tags, TCOM, track.metadata.composer)
    _set_id3_text(tags, TIT1, track.metadata.grouping)
    _set_id3_text(tags, TCOP, track.metadata.copyright)
    _set_id3_text(tags, TSRC, track.metadata.isrc)
    _set_id3_text(tags, TBPM, track.content_tags.bpm)
    _set_id3_text(tags, TKEY, track.content_tags.key)
    _set_id3_text(tags, TMOO, track.content_tags.mood)

    _set_id3_comment(tags, track.metadata.comment)
    _set_id3_txxx(tags, "BARCODE", track.metadata.barcode)
    _set_id3_txxx(tags, "MusicBrainz Track Id", track.metadata.musicbrainz_recording_id)
    _set_id3_txxx(tags, "MusicBrainz Album Id", track.metadata.musicbrainz_release_id)
    _set_id3_txxx(tags, "MusicBrainz Release Group Id", track.metadata.musicbrainz_release_group_id)
    _set_id3_txxx(tags, "MusicBrainz Artist Id", track.metadata.musicbrainz_artist_id)
    _set_id3_text(tags, TRCK, _pair_value(track.metadata.track_number, track.metadata.track_total))
    _set_id3_text(tags, TPOS, _pair_value(track.metadata.disc_number, track.metadata.disc_total))


def _set_mp4_freeform(mutagen_file, key: str, value: str | None) -> None:
    if value:
        mutagen_file[key] = [MP4FreeForm(value.encode("utf-8"))]
    elif key in mutagen_file:
        del mutagen_file[key]


def _set_id3_text(tags, frame_cls, value) -> None:
    frame_name = frame_cls.__name__
    if isinstance(value, list):
        text = [str(item) for item in value if item not in (None, "")]
    elif value not in (None, ""):
        text = [str(value)]
    else:
        text = []

    if text:
        tags.delall(frame_name)
        tags.add(frame_cls(encoding=3, text=text))
    else:
        tags.delall(frame_name)


def _set_id3_comment(tags, value: str | None) -> None:
    tags.delall("COMM")
    if value:
        tags.add(COMM(encoding=3, lang="eng", desc="", text=[value]))


def _set_id3_txxx(tags, description: str, value) -> None:
    tags.delall(f"TXXX:{description}")
    if value in (None, "", []):
        return

    text = [str(item) for item in value] if isinstance(value, list) else [str(value)]
    tags.add(TXXX(encoding=3, desc=description, text=text))


def _canonical_field_values(track: CanonicalTrack) -> dict[str, object]:
    return {
        "title": track.metadata.title,
        "artist": track.metadata.artist,
        "album": track.metadata.album,
        "album_artist": track.metadata.album_artist,
        "track_number": track.metadata.track_number,
        "track_total": track.metadata.track_total,
        "disc_number": track.metadata.disc_number,
        "disc_total": track.metadata.disc_total,
        "release_date": track.metadata.release_date,
        "original_date": track.metadata.original_date,
        "genre": track.metadata.genre,
        "subgenre": track.metadata.subgenre,
        "composer": track.metadata.composer,
        "comment": track.metadata.comment,
        "grouping": track.metadata.grouping,
        "label": track.metadata.label,
        "copyright": track.metadata.copyright,
        "isrc": track.metadata.isrc,
        "musicbrainz_recording_id": track.metadata.musicbrainz_recording_id,
        "musicbrainz_release_id": track.metadata.musicbrainz_release_id,
        "musicbrainz_release_group_id": track.metadata.musicbrainz_release_group_id,
        "musicbrainz_artist_id": track.metadata.musicbrainz_artist_id,
        "barcode": track.metadata.barcode,
        "bpm": track.content_tags.bpm,
        "key": track.content_tags.key,
        "mood": track.content_tags.mood,
        "energy": track.content_tags.energy,
        "vocal_presence": track.content_tags.vocal_presence,
        "instruments": track.content_tags.instruments,
        "language": track.content_tags.language,
    }


def _preserve_custom_tags(mutagen_file, track: CanonicalTrack) -> None:
    for key, values in track.custom_tags.items():
        if key in mutagen_file:
            continue
        mutagen_file[key] = [str(value) for value in values]


def _pair_value(number: int | None, total: int | None) -> str | None:
    if number is None and total is None:
        return None
    if total is None:
        return str(number)
    return f"{number or 0}/{total}"
