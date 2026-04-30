"""Purpose: Run a readable tagging evaluation for one local audio file."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from services.tagging import TaggingService


def main() -> int:
    """Evaluate one file and print a concise tagging report."""
    parser = argparse.ArgumentParser(description="Inspect tagging proposals for one audio file.")
    parser.add_argument("file", help="Path to the audio file to inspect.")
    args = parser.parse_args()

    api_key = os.environ.get("ACOUSTID_API_KEY")
    service = TaggingService(acoustid_api_key=api_key)

    file_path = Path(args.file).expanduser().resolve()
    track = service.read_track(file_path)
    proposed, diff_report, candidates = service.propose_tags(file_path)

    print_summary(track, proposed, diff_report, candidates)
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
