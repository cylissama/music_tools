Purpose: Record short, append-only summaries of meaningful project changes.

# Changelog

## 2026-05-07

### Current Tag Viewer
- Added a right-click library action for track rows so the current embedded tags for a file can be inspected without starting the tagging proposal flow.
- Added a read-only current-tags dialog with canonical metadata, content tags, technical fields, raw container tags, and custom tags.
- Added a manual `Edit Tags` workflow for selected track rows so current canonical fields can be edited in-app and then saved through the same preview/apply safety flow used by automatic tagging.
- Split playlist creation and tag management into separate application tabs, and added a tag-focused workspace that shows library selection details, track lists, cover art, and metadata in one view.

### Metadata Indexing And Factual Tag Coverage
- Expanded the lookup and merge pipeline to carry additional factual fields such as track totals, disc totals, and original release dates when available.
- Fixed read/write coverage so standalone `TRACKTOTAL` and `DISCTOTAL` values are read correctly and `original_date` can round-trip for MP3, Vorbis-style formats, and MP4 freeform tags.
- Upgraded the library scan to read lightweight per-track metadata summaries so library rows can display tag-aware names and tooltips instead of relying only on filenames.

### Configurable File Renaming
- Added a persistent rename configuration to app settings so tagged tracks can be moved into a folder and filename pattern derived from canonical metadata.
- Added rename planning and safe file moves after confirmed tag application, with support for album-folder templates like `{album_artist} - {album} ({release_year}) [{file_type}]` and track templates like `{track_number_padded} {title}`.
- Extended the tag preview/apply flow to show the planned destination path and rescan the library after a successful rename.
- Added an in-app Settings tab for editing rename templates and toggles, including a live preview and an album-level folder naming option that aggregates shared metadata from sibling tracks.
- Updated album renames to carry along non-track sibling items from the original album folder, such as cover images and extra files, into the renamed destination directory.

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
