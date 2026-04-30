"""Purpose: Run a readable tagging evaluation for one local audio file."""

from __future__ import annotations

import argparse
import csv
import os
from pathlib import Path
from time import strftime

from services.tagging import TaggingService

AUDIO_EXTENSIONS = {".mp3", ".flac", ".ogg", ".opus", ".m4a", ".mp4", ".wav", ".aiff", ".aif"}
CSV_HEADERS = [
    "file_path",
    "file_format",
    "current_title",
    "current_artist",
    "current_album",
    "current_album_artist",
    "current_track_number",
    "current_release_date",
    "current_label",
    "current_barcode",
    "current_catalog_number",
    "current_discogs_release_id",
    "proposed_title",
    "proposed_artist",
    "proposed_album",
    "proposed_album_artist",
    "proposed_track_number",
    "proposed_release_date",
    "proposed_label",
    "proposed_barcode",
    "proposed_catalog_number",
    "proposed_discogs_release_id",
    "best_source",
    "best_candidate_confidence",
    "score",
    "review_required",
    "change_count",
    "reasons",
    "changed_fields",
    "proposed_musicbrainz_recording_id",
    "proposed_musicbrainz_release_id",
]


def main() -> int:
    """Evaluate one file or a folder and print concise tagging reports."""
    parser = argparse.ArgumentParser(description="Inspect tagging proposals for local audio files.")
    parser.add_argument("path", help="Path to one audio file or a folder of audio files.")
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum number of files to inspect when a folder is provided.",
    )
    parser.add_argument(
        "--csv",
        type=str,
        default=None,
        help="Optional path for the CSV review report. Defaults to reports/tagging-review-<timestamp>.csv",
    )
    args = parser.parse_args()

    api_key = os.environ.get("ACOUSTID_API_KEY")
    service = TaggingService(acoustid_api_key=api_key)

    target_path = Path(args.path).expanduser().resolve()
    file_paths = collect_audio_files(target_path, args.limit)
    if not file_paths:
        print("No supported audio files found.")
        return 1

    csv_path = resolve_csv_path(args.csv)
    rows: list[dict[str, str]] = []

    if len(file_paths) == 1:
        file_path = file_paths[0]
        track = service.read_track(file_path)
        proposed, diff_report, candidates = service.propose_tags(file_path)
        print_summary(track, proposed, diff_report, candidates)
        rows.append(build_csv_row(track, proposed, diff_report, candidates))
        write_csv_report(csv_path, rows)
        print()
        print(f"CSV report written to: {csv_path}")
        return 0

    print_batch_summary(service, file_paths, rows)
    write_csv_report(csv_path, rows)
    print()
    print(f"CSV report written to: {csv_path}")
    return 0


def print_summary(track, proposed, diff_report, candidates) -> None:
    """Print a compact, human-readable evaluation summary."""
    print("Track")
    print(f"  File: {track.file_path}")
    print(f"  Format: {track.file_format}")
    print(f"  Title: {track.metadata.title or '(missing)'}")
    print(f"  Artist: {join_values(track.metadata.artist)}")
    print(f"  Album: {track.metadata.album or '(missing)'}")
    print(f"  Track #: {track.metadata.track_number or '(missing)'}")
    print(f"  Date: {track.metadata.release_date or '(missing)'}")
    print()

    best_source = candidates[0].source if candidates else "none"
    best_candidate = max(candidates, key=lambda candidate: candidate.confidence, default=None)
    best_source = best_candidate.source if best_candidate else "none"
    best_confidence = f"{best_candidate.confidence:.4f}" if best_candidate else "0.0000"

    print("Proposal")
    print(f"  Review required: {diff_report.review_required}")
    print(f"  Auto-apply confidence: {format_confidence(diff_report.auto_apply_confidence)}")
    print(f"  Best candidate source: {best_source}")
    print(f"  Best candidate confidence: {best_confidence}")
    print(f"  Reasons: {', '.join(diff_report.reasons) if diff_report.reasons else '(none)'}")
    print()

    print("Changes")
    if not diff_report.changes:
        print("  No changes proposed.")
    else:
        for change in diff_report.changes:
            print(f"  {change.field_path}:")
            print(f"    before: {format_value(change.before)}")
            print(f"    after:  {format_value(change.after)}")
    print()

    print("Candidates")
    if not candidates:
        print("  No candidates returned.")
        return

    for index, candidate in enumerate(sorted(candidates, key=lambda item: item.confidence, reverse=True), start=1):
        print(f"  {index}. {candidate.source} ({candidate.confidence:.4f})")
        print(f"     title: {candidate.title or '(missing)'}")
        print(f"     artist: {join_values(candidate.artist)}")
        print(f"     album: {candidate.album or '(missing)'}")
        print(f"     track #: {candidate.track_number or '(missing)'}")
        print(f"     date: {candidate.release_date or '(missing)'}")
        print(f"     recording id: {candidate.musicbrainz_recording_id or '(missing)'}")
        print(f"     release id: {candidate.musicbrainz_release_id or '(missing)'}")


def print_batch_summary(service: TaggingService, file_paths: list[Path], rows: list[dict[str, str]]) -> None:
    """Print a compact report for multiple files."""
    print(f"Evaluating {len(file_paths)} files")
    print()

    review_count = 0
    auto_apply_count = 0

    for index, file_path in enumerate(file_paths, start=1):
        try:
            track = service.read_track(file_path)
            proposed, diff_report, candidates = service.propose_tags(file_path)
        except Exception as exc:
            print(f"{index}. ERROR")
            print(f"   file: {file_path}")
            print(f"   reason: {exc}")
            rows.append(
                {
                    "file_path": str(file_path),
                    "file_format": "",
                    "current_title": "",
                    "current_artist": "",
                    "current_album": "",
                    "current_album_artist": "",
                    "current_track_number": "",
                    "current_release_date": "",
                    "current_label": "",
                    "current_barcode": "",
                    "current_catalog_number": "",
                    "current_discogs_release_id": "",
                    "proposed_title": "",
                    "proposed_artist": "",
                    "proposed_album": "",
                    "proposed_album_artist": "",
                    "proposed_track_number": "",
                    "proposed_release_date": "",
                    "proposed_label": "",
                    "proposed_barcode": "",
                    "proposed_catalog_number": "",
                    "proposed_discogs_release_id": "",
                    "best_source": "error",
                    "best_candidate_confidence": "",
                    "score": "",
                    "review_required": "error",
                    "change_count": "0",
                    "reasons": str(exc),
                    "changed_fields": "",
                    "proposed_musicbrainz_recording_id": "",
                    "proposed_musicbrainz_release_id": "",
                }
            )
            print()
            continue

        best_candidate = max(candidates, key=lambda candidate: candidate.confidence, default=None)
        best_source = best_candidate.source if best_candidate else "none"
        best_confidence = f"{best_candidate.confidence:.4f}" if best_candidate else "0.0000"
        change_count = len(diff_report.changes)

        if diff_report.review_required:
            review_count += 1
        else:
            auto_apply_count += 1

        print(f"{index}. {track.metadata.artist[0] if track.metadata.artist else '(missing artist)'} - {track.metadata.title or file_path.name}")
        print(f"   file: {file_path}")
        print(f"   best source: {best_source}")
        print(f"   score: {format_confidence(diff_report.auto_apply_confidence)}")
        print(f"   best candidate confidence: {best_confidence}")
        print(f"   review required: {diff_report.review_required}")
        print(f"   changes: {change_count}")
        print(f"   reasons: {', '.join(diff_report.reasons) if diff_report.reasons else '(none)'}")
        print()
        rows.append(build_csv_row(track, proposed, diff_report, candidates))

    print("Batch Totals")
    print(f"  Auto-apply eligible: {auto_apply_count}")
    print(f"  Review required: {review_count}")


def collect_audio_files(target_path: Path, limit: int | None) -> list[Path]:
    """Return one file or a sorted recursive list of supported audio files."""
    if target_path.is_file():
        return [target_path] if target_path.suffix.lower() in AUDIO_EXTENSIONS else []

    if not target_path.is_dir():
        return []

    files = sorted(
        [
            path
            for path in target_path.rglob("*")
            if path.is_file() and path.suffix.lower() in AUDIO_EXTENSIONS
        ],
        key=lambda path: str(path).lower(),
    )

    if limit is not None:
        return files[:limit]
    return files


def resolve_csv_path(csv_arg: str | None) -> Path:
    """Return the report path for the current evaluation run."""
    if csv_arg:
        csv_path = Path(csv_arg).expanduser().resolve()
    else:
        reports_dir = Path.cwd() / "reports"
        csv_path = reports_dir / f"tagging-review-{strftime('%Y%m%d-%H%M%S')}.csv"

    csv_path.parent.mkdir(parents=True, exist_ok=True)
    return csv_path


def write_csv_report(csv_path: Path, rows: list[dict[str, str]]) -> None:
    """Write the review rows to a CSV file for spreadsheet-style inspection."""
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_HEADERS)
        writer.writeheader()
        writer.writerows(rows)


def build_csv_row(track, proposed, diff_report, candidates) -> dict[str, str]:
    """Create one CSV row that summarizes the current and proposed tags."""
    best_candidate = max(candidates, key=lambda candidate: candidate.confidence, default=None)
    changed_fields = "; ".join(change.field_path for change in diff_report.changes)

    return {
        "file_path": track.file_path,
        "file_format": track.file_format,
        "current_title": track.metadata.title or "",
        "current_artist": join_values(track.metadata.artist),
        "current_album": track.metadata.album or "",
        "current_album_artist": join_values(track.metadata.album_artist),
        "current_track_number": str(track.metadata.track_number or ""),
        "current_release_date": track.metadata.release_date or "",
        "current_label": track.metadata.label or "",
        "current_barcode": track.metadata.barcode or "",
        "current_catalog_number": track.metadata.catalog_number or "",
        "current_discogs_release_id": track.metadata.discogs_release_id or "",
        "proposed_title": proposed.metadata.title or "",
        "proposed_artist": join_values(proposed.metadata.artist),
        "proposed_album": proposed.metadata.album or "",
        "proposed_album_artist": join_values(proposed.metadata.album_artist),
        "proposed_track_number": str(proposed.metadata.track_number or ""),
        "proposed_release_date": proposed.metadata.release_date or "",
        "proposed_label": proposed.metadata.label or "",
        "proposed_barcode": proposed.metadata.barcode or "",
        "proposed_catalog_number": proposed.metadata.catalog_number or "",
        "proposed_discogs_release_id": proposed.metadata.discogs_release_id or "",
        "best_source": best_candidate.source if best_candidate else "none",
        "best_candidate_confidence": f"{best_candidate.confidence:.4f}" if best_candidate else "",
        "score": format_confidence(diff_report.auto_apply_confidence),
        "review_required": str(diff_report.review_required),
        "change_count": str(len(diff_report.changes)),
        "reasons": "; ".join(diff_report.reasons),
        "changed_fields": changed_fields,
        "proposed_musicbrainz_recording_id": proposed.metadata.musicbrainz_recording_id or "",
        "proposed_musicbrainz_release_id": proposed.metadata.musicbrainz_release_id or "",
    }


def join_values(values: list[str]) -> str:
    """Render a list of strings safely for terminal output."""
    return ", ".join(values) if values else "(missing)"


def format_value(value) -> str:
    """Render diff values in a compact, readable way."""
    if value in (None, "", []):
        return "(missing)"
    if isinstance(value, list):
        return ", ".join(str(item) for item in value)
    return str(value)


def format_confidence(value: float | None) -> str:
    """Render confidence values with a consistent precision."""
    if value is None:
        return "(missing)"
    return f"{value:.4f}"


if __name__ == "__main__":
    raise SystemExit(main())
