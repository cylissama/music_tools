Purpose: Record short, append-only summaries of meaningful project changes.

# Changelog

## 2026-04-30

### Discogs Integration
- Added Discogs as a secondary release-metadata source in the tagging pipeline, using token-authenticated release search alongside MusicBrainz, AcoustID, and filename parsing.
- Extended the canonical metadata model to carry Discogs release ids, catalog numbers, label data, and barcode values when Discogs candidates can provide them.
- Added read/write support for Discogs release ids and catalog numbers across canonical reader/writer paths so those fields can survive a full preview and apply cycle.
- Expanded the CSV tagging review export to include Discogs and release-detail columns for easier visual QA of proposed metadata.

### Saved Music Locations
- Added persistent saved music locations so one or more library roots can be remembered across app runs and restored automatically on startup.
- Added UI controls for selecting, adding, and removing saved music locations, with the active location auto-scanned when restored or changed.

### Tagging UI Workflow
- Added a library-side `Preview Tags` action that resolves one selected track to disk, builds a tagging proposal, and opens a detailed review dialog before any write is allowed.
- Added a tagging preview dialog with summary, field-by-field changes, and candidate source tabs so the user can review both the proposed metadata and the reasoning behind it.

### Tagging UI Logging
- Added structured activity logs for tag preview start/success/dismiss/failure and tag apply start/success/failure so UI-level tagging actions are traceable across sessions.

### Tagging Preview Safeguard
- Added a required preview-and-confirm workflow to the tagging service so tags cannot be written without first generating a preview report and explicitly accepting it.
- Added a dedicated preview helper method to keep review-first UI and CLI flows straightforward.

### Tagging Review Export
- Added automatic CSV export for each tagging evaluation run so current tags, proposed tags, scores, reasons, and changed fields can be reviewed more efficiently in a spreadsheet.
- Added configurable CSV output paths and default timestamped report generation under `reports/`.

### Tagging Score Tuning
- Added a source-aware score bonus for `acoustid_musicbrainz` and `acoustid` candidates so strong fingerprint-backed matches receive more appropriate weight.
- Expanded text normalization to better handle symbolic titles such as `9°` and strip punctuation that can reduce otherwise correct title matches.

### Tagging Score Normalization
- Improved candidate similarity scoring to normalize punctuation, spacing, unicode, and common title separators before comparing text.
- Added title-specific normalization so feature annotations like `ft.` or `feat.` do not unfairly lower match scores.

### Tagging Evaluation Flow
- Updated the tag evaluation tooling to support both single-file and folder-based testing with compact summaries.
- Improved candidate collection so MusicBrainz search, AcoustID-enriched MusicBrainz matches, and filename parsing are all scored together.

### Tagging Safety And Persistence
- Added persistent tagging audit storage with review queue support and safe workspace fallback storage.
- Added canonical metadata read/write flow with dry-run diffs, snapshots, and post-write verification.
