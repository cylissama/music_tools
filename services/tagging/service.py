"""Purpose: Orchestrate safe metadata reading, lookup, normalization, review, and writing."""

from __future__ import annotations

import os
from pathlib import Path

from services.app_settings import RenameConfig
from services.tagging.audit_store import TaggingAuditStore
from services.tagging.conflict_resolution import (
    choose_best_candidate,
    merge_candidate_into_track,
    parse_filename_context,
    review_required_for_score,
    validate_album_consistency,
)
from services.tagging.diff_report import build_diff_report
from services.tagging.lookup.acoustid_client import AcoustIdLookupClient
from services.tagging.lookup.discogs_client import DiscogsLookupClient
from services.tagging.lookup.musicbrainz_client import MusicBrainzLookupClient
from services.tagging.normalize import normalize_track_tags
from services.tagging.reader import read_canonical_metadata
from services.tagging.renamer import (
    RenamePlan,
    apply_track_rename_with_context,
    plan_track_rename_with_context,
)
from services.tagging.review_queue import ReviewQueueService
from services.tagging.schema import CanonicalTrack, DiffReport, FieldDiff, LookupCandidate
from services.tagging.writer import write_canonical_metadata


class TaggingService:
    """Facade that exposes the Phase 1 and Phase 2 tagging workflow."""

    def __init__(
        self,
        *,
        audit_store: TaggingAuditStore | None = None,
        acoustid_api_key: str | None = None,
    ) -> None:
        self.audit_store = audit_store or TaggingAuditStore()
        self.review_queue = ReviewQueueService(self.audit_store)
        self.musicbrainz = MusicBrainzLookupClient()
        self.acoustid = AcoustIdLookupClient(api_key=acoustid_api_key)
        self.discogs = DiscogsLookupClient(user_token=os.environ.get("DISCOGS_USER_TOKEN"))

    def read_track(self, file_path: str | Path) -> CanonicalTrack:
        """Read a file into the canonical schema and normalize descriptive tags."""
        return normalize_track_tags(read_canonical_metadata(file_path))

    def propose_tags(self, file_path: str | Path) -> tuple[CanonicalTrack, DiffReport, list[LookupCandidate]]:
        """Build a safe proposal by combining embedded tags, filename clues, and lookups."""
        track = self.read_track(file_path)
        return self.propose_tags_for_track(track)

    def propose_tags_for_track(self, track: CanonicalTrack) -> tuple[CanonicalTrack, DiffReport, list[LookupCandidate]]:
        """Build a safe proposal for an already-read canonical track."""
        context = parse_filename_context(track.file_path)
        candidates = self._collect_candidates(track, context)
        best_candidate, score = choose_best_candidate(candidates, track, context)

        if best_candidate is not None:
            proposed = normalize_track_tags(merge_candidate_into_track(track, best_candidate))
            review_required, reasons = review_required_for_score(score)
            diff_report = build_diff_report(
                track,
                proposed,
                review_required=review_required,
                reasons=reasons,
                auto_apply_confidence=score,
            )
            return proposed, diff_report, candidates

        diff_report = build_diff_report(
            track,
            track.clone(),
            review_required=True,
            reasons=["no_lookup_candidates_found"],
            auto_apply_confidence=0.0,
        )
        return track.clone(), diff_report, candidates

    def preview_tags(self, proposed_track: CanonicalTrack, *, source: str = "tagging_preview") -> DiffReport:
        """Persist and return a dry-run preview that the user can review before accepting."""
        return write_canonical_metadata(
            proposed_track,
            audit_store=self.audit_store,
            source=source,
            dry_run=True,
        )

    def apply_tags(
        self,
        proposed_track: CanonicalTrack,
        *,
        preview_report: DiffReport | None = None,
        confirmed: bool = False,
        source: str = "tagging_service",
        rename_config: RenameConfig | None = None,
        album_tracks: list[CanonicalTrack] | None = None,
    ) -> DiffReport:
        """Write a previously previewed proposal only after explicit confirmation."""
        self._validate_preview_confirmation(proposed_track, preview_report, confirmed)
        applied_report = write_canonical_metadata(
            proposed_track,
            audit_store=self.audit_store,
            source=source,
            dry_run=False,
        )
        if rename_config is not None and rename_config.enabled:
            rename_plan = apply_track_rename_with_context(proposed_track, rename_config, album_tracks)
            self._attach_rename_result(applied_report, rename_plan)
        return applied_report

    def dry_run(self, proposed_track: CanonicalTrack, *, source: str = "tagging_service") -> DiffReport:
        """Create and persist a dry-run report without modifying the file."""
        return self.preview_tags(proposed_track, source=source)

    def queue_for_review(self, proposed_track: CanonicalTrack, diff_report: DiffReport) -> int:
        """Persist a reviewable proposal for later UI or batch processing."""
        reason = ", ".join(diff_report.reasons) if diff_report.reasons else "review_required"
        return self.review_queue.queue_track(proposed_track, diff_report, reason)

    def validate_album(self, file_paths: list[str | Path]) -> list[dict[str, object]]:
        """Read a set of files and report album-level inconsistencies."""
        tracks = [self.read_track(file_path) for file_path in file_paths]
        return validate_album_consistency(tracks)

    def preview_rename(
        self,
        proposed_track: CanonicalTrack,
        rename_config: RenameConfig,
        album_tracks: list[CanonicalTrack] | None = None,
    ) -> RenamePlan:
        """Build a dry-run rename plan for a tagged track."""
        return plan_track_rename_with_context(proposed_track, rename_config, album_tracks)

    def _collect_candidates(
        self,
        track: CanonicalTrack,
        context: dict[str, object],
    ) -> list[LookupCandidate]:
        candidates: list[LookupCandidate] = []

        if track.metadata.musicbrainz_recording_id:
            candidates.extend(self.musicbrainz.lookup_by_recording_id(track.metadata.musicbrainz_recording_id))

        if context.get("title"):
            artist = "; ".join(context.get("artist", [])) if isinstance(context.get("artist"), list) else None
            candidates.extend(
                self.musicbrainz.search_recordings(
                    str(context["title"]),
                    artist=artist,
                    album=str(context["album"]) if context.get("album") else None,
                )
            )
            candidates.extend(
                self.discogs.search_releases(
                    title=str(context["title"]),
                    artist=artist,
                    album=str(context["album"]) if context.get("album") else None,
                )
            )

        candidates.extend(self._enrich_acoustid_candidates(self.acoustid.lookup_file(track.file_path)))

        if context.get("title"):
            candidates.append(
                LookupCandidate(
                    source="filename_parser",
                    title=str(context["title"]),
                    artist=list(context.get("artist", [])),
                    album=str(context["album"]) if context.get("album") else None,
                    track_number=context.get("track_number"),
                    confidence=0.35,
                    details={"source": "filename_parser"},
                )
            )

        return candidates

    def _enrich_acoustid_candidates(self, acoustid_candidates: list[LookupCandidate]) -> list[LookupCandidate]:
        """Expand AcoustID recording hits with MusicBrainz release metadata when possible."""
        enriched: list[LookupCandidate] = []

        for candidate in acoustid_candidates:
            if not candidate.musicbrainz_recording_id:
                enriched.append(candidate)
                continue

            musicbrainz_matches = self.musicbrainz.lookup_by_recording_id(candidate.musicbrainz_recording_id)
            if not musicbrainz_matches:
                enriched.append(candidate)
                continue

            for match in musicbrainz_matches:
                match.confidence = candidate.confidence
                if not match.title:
                    match.title = candidate.title
                if not match.artist:
                    match.artist = list(candidate.artist)
                match.details.update(candidate.details)
                match.details["enriched_from"] = "acoustid"
                match.source = "acoustid_musicbrainz"
                enriched.append(match)

        return enriched

    def _validate_preview_confirmation(
        self,
        proposed_track: CanonicalTrack,
        preview_report: DiffReport | None,
        confirmed: bool,
    ) -> None:
        """Require an explicit preview-and-confirm step before mutating a file."""
        if preview_report is None:
            raise ValueError("A preview report is required before applying tags.")

        if preview_report.file_path != proposed_track.file_path:
            raise ValueError("The preview report does not match the proposed file.")

        if not confirmed:
            raise ValueError("Tag application requires explicit confirmation after preview.")

    @staticmethod
    def _attach_rename_result(diff_report: DiffReport, rename_plan: RenamePlan) -> None:
        if not rename_plan.rename_required:
            diff_report.result_file_path = rename_plan.source_path
            return

        diff_report.changes.append(
            FieldDiff(
                field_path="file_path",
                before=rename_plan.source_path,
                after=rename_plan.target_path,
            )
        )
        diff_report.result_file_path = rename_plan.target_path
