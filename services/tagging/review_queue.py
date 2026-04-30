"""Purpose: Provide a thin workflow API around the tagging review queue."""

from __future__ import annotations

from services.tagging.audit_store import TaggingAuditStore
from services.tagging.schema import CanonicalTrack, DiffReport


class ReviewQueueService:
    """High-level API for queueing and updating reviewable tagging work."""

    def __init__(self, audit_store: TaggingAuditStore) -> None:
        self.audit_store = audit_store

    def queue_track(self, proposed_track: CanonicalTrack, diff_report: DiffReport, reason: str) -> int:
        """Add one track to the persistent review queue."""
        return self.audit_store.enqueue_review(
            file_path=proposed_track.file_path,
            diff_report=diff_report,
            proposed_track=proposed_track,
            reason=reason,
        )

    def list_pending(self) -> list[dict[str, object]]:
        """Return pending review items."""
        return self.audit_store.list_review_items("pending")

    def mark_accepted(self, review_id: int) -> None:
        self.audit_store.set_review_status(review_id, "accepted")

    def mark_rejected(self, review_id: int) -> None:
        self.audit_store.set_review_status(review_id, "rejected")
