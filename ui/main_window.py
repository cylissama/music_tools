"""Purpose: Build the Qt interface and connect user actions to app logic."""

import os
from pathlib import Path

from PySide6.QtCore import QItemSelectionModel, Qt, QSignalBlocker, QSortFilterProxyModel
from PySide6.QtGui import QAction, QPixmap, QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHeaderView,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QMenu,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

from models import LibraryAlbum, PlaylistState
from services.activity_logger import (
    log_album_toggled,
    log_cover_art_loaded,
    log_cover_art_not_found,
    log_cover_art_probe_failed,
    log_music_location_activated,
    log_music_location_added,
    log_music_location_removed,
    log_music_locations_loaded,
    log_playlist_cleared,
    log_playlist_reordered,
    log_playlist_reordered_from_drag,
    log_playlist_save_cancelled,
    log_playlist_save_failed,
    log_playlist_save_started,
    log_playlist_saved,
    log_playlist_track_removed,
    log_root_selected,
    log_root_selection_cancelled,
    log_scan_cancelled,
    log_scan_completed,
    log_scan_started,
    log_settings_save_failed,
    log_tag_apply_failed,
    log_tag_apply_started,
    log_tag_apply_succeeded,
    log_tag_preview_dismissed,
    log_tag_preview_failed,
    log_tag_preview_ready,
    log_tag_preview_started,
    log_tag_selection_details_refreshed,
    log_tracks_added,
)
from services.app_settings import AppSettings, AppSettingsStore, RenameConfig
from services.library_scanner import scan_music_files
from services.playlist_writer import write_m3u8_playlist
from services.tagging import TaggingService
from services.tagging.reader import read_embedded_cover_art

ALBUM_TRACKS_ROLE = Qt.UserRole + 1
TRACK_PATH_ROLE = Qt.UserRole + 2


class TagPreviewDialog(QDialog):
    """Show a detailed preview of current tags, proposed tags, and candidate matches."""

    def __init__(self, track, proposed_track, diff_report, candidates, rename_plan=None, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Tagging Preview")
        self.resize(900, 650)

        layout = QVBoxLayout(self)

        summary = QPlainTextEdit()
        summary.setReadOnly(True)
        summary.setLineWrapMode(QPlainTextEdit.NoWrap)
        summary.setPlainText(
            "\n".join(
                [
                    f"File: {track.file_path}",
                    f"Format: {track.file_format}",
                    f"Review required: {diff_report.review_required}",
                    f"Confidence score: {self._format_confidence(diff_report.auto_apply_confidence)}",
                    f"Reasons: {', '.join(diff_report.reasons) if diff_report.reasons else '(none)'}",
                    "",
                    "Current",
                    f"  Title: {track.metadata.title or '(missing)'}",
                    f"  Artist: {self._join_values(track.metadata.artist)}",
                    f"  Album: {track.metadata.album or '(missing)'}",
                    f"  Album artist: {self._join_values(track.metadata.album_artist)}",
                    f"  Track number: {track.metadata.track_number or '(missing)'}",
                    f"  Release date: {track.metadata.release_date or '(missing)'}",
                    "",
                    "Proposed",
                    f"  Title: {proposed_track.metadata.title or '(missing)'}",
                    f"  Artist: {self._join_values(proposed_track.metadata.artist)}",
                    f"  Album: {proposed_track.metadata.album or '(missing)'}",
                    f"  Album artist: {self._join_values(proposed_track.metadata.album_artist)}",
                    f"  Track number: {proposed_track.metadata.track_number or '(missing)'}",
                    f"  Release date: {proposed_track.metadata.release_date or '(missing)'}",
                    f"  Recording ID: {proposed_track.metadata.musicbrainz_recording_id or '(missing)'}",
                    f"  Release ID: {proposed_track.metadata.musicbrainz_release_id or '(missing)'}",
                    "",
                    "Rename",
                    f"  Enabled: {'yes' if rename_plan else 'no'}",
                    f"  Current path: {track.file_path}",
                    f"  Target path: {rename_plan.target_path if rename_plan else track.file_path}",
                    f"  Will move file: {rename_plan.rename_required if rename_plan else False}",
                    f"  Warnings: {', '.join(rename_plan.warnings) if rename_plan and rename_plan.warnings else '(none)'}",
                    "",
                    "Changed fields",
                    *self._format_change_lines(diff_report.changes),
                ]
            )
        )

        changes_table = QTableWidget(len(diff_report.changes), 3)
        changes_table.setHorizontalHeaderLabels(["Field", "Before", "After"])
        changes_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        changes_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        changes_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        changes_table.verticalHeader().setVisible(False)
        changes_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        for row, change in enumerate(diff_report.changes):
            changes_table.setItem(row, 0, QTableWidgetItem(change.field_path))
            changes_table.setItem(row, 1, QTableWidgetItem(self._format_value(change.before)))
            changes_table.setItem(row, 2, QTableWidgetItem(self._format_value(change.after)))

        candidates_table = QTableWidget(len(candidates), 7)
        candidates_table.setHorizontalHeaderLabels(
            ["Source", "Confidence", "Title", "Artist", "Album", "Date", "Recording ID"]
        )
        candidates_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        candidates_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        for column in range(2, 7):
            candidates_table.horizontalHeader().setSectionResizeMode(column, QHeaderView.Stretch)
        candidates_table.verticalHeader().setVisible(False)
        candidates_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        sorted_candidates = sorted(candidates, key=lambda candidate: candidate.confidence, reverse=True)
        for row, candidate in enumerate(sorted_candidates):
            candidates_table.setItem(row, 0, QTableWidgetItem(candidate.source))
            candidates_table.setItem(row, 1, QTableWidgetItem(f"{candidate.confidence:.4f}"))
            candidates_table.setItem(row, 2, QTableWidgetItem(candidate.title or "(missing)"))
            candidates_table.setItem(row, 3, QTableWidgetItem(self._join_values(candidate.artist)))
            candidates_table.setItem(row, 4, QTableWidgetItem(candidate.album or "(missing)"))
            candidates_table.setItem(row, 5, QTableWidgetItem(candidate.release_date or "(missing)"))
            candidates_table.setItem(
                row,
                6,
                QTableWidgetItem(candidate.musicbrainz_recording_id or "(missing)"),
            )

        tabs = QTabWidget()
        tabs.addTab(summary, "Summary")
        tabs.addTab(changes_table, f"Changes ({len(diff_report.changes)})")
        tabs.addTab(candidates_table, f"Candidates ({len(candidates)})")
        layout.addWidget(tabs)

        button_box = QDialogButtonBox(QDialogButtonBox.Close)
        self.accept_button = button_box.addButton("Accept Tags", QDialogButtonBox.AcceptRole)
        self.close_button = button_box.button(QDialogButtonBox.Close)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    @staticmethod
    def _join_values(values: list[str]) -> str:
        return ", ".join(values) if values else "(missing)"

    @staticmethod
    def _format_value(value) -> str:
        if value in (None, "", []):
            return "(missing)"
        if isinstance(value, list):
            return ", ".join(str(item) for item in value)
        return str(value)

    @staticmethod
    def _format_confidence(value: float | None) -> str:
        if value is None:
            return "(missing)"
        return f"{value:.4f}"

    @staticmethod
    def _join_values(values: list[str]) -> str:
        return ", ".join(values) if values else "(missing)"

    @staticmethod
    def _format_value(value) -> str:
        if value in (None, "", []):
            return "(missing)"
        if isinstance(value, list):
            return ", ".join(str(item) for item in value)
        return str(value)

    @staticmethod
    def _format_change_lines(changes) -> list[str]:
        if not changes:
            return ["  (none)"]

        return [
            f"  {change.field_path}: {TagPreviewDialog._format_value(change.before)} -> {TagPreviewDialog._format_value(change.after)}"
            for change in changes
        ]


class CurrentTagsDialog(QDialog):
    """Show the currently embedded and parsed tags for one audio file."""

    def __init__(self, track, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Current File Tags")
        self.resize(920, 680)

        layout = QVBoxLayout(self)

        summary = QPlainTextEdit()
        summary.setReadOnly(True)
        summary.setLineWrapMode(QPlainTextEdit.NoWrap)
        summary.setPlainText(
            "\n".join(
                [
                    f"File: {track.file_path}",
                    f"Format: {track.file_format}",
                    f"Title: {track.metadata.title or '(missing)'}",
                    f"Artist: {self._format_value(track.metadata.artist)}",
                    f"Album: {track.metadata.album or '(missing)'}",
                    f"Album artist: {self._format_value(track.metadata.album_artist)}",
                    f"Track: {self._format_pair(track.metadata.track_number, track.metadata.track_total)}",
                    f"Disc: {self._format_pair(track.metadata.disc_number, track.metadata.disc_total)}",
                    f"Release date: {track.metadata.release_date or '(missing)'}",
                    f"Genre: {self._format_value(track.metadata.genre)}",
                ]
            )
        )

        metadata_table = self._build_table(
            [
                ("title", track.metadata.title),
                ("artist", track.metadata.artist),
                ("album", track.metadata.album),
                ("album_artist", track.metadata.album_artist),
                ("track_number", track.metadata.track_number),
                ("track_total", track.metadata.track_total),
                ("disc_number", track.metadata.disc_number),
                ("disc_total", track.metadata.disc_total),
                ("release_date", track.metadata.release_date),
                ("original_date", track.metadata.original_date),
                ("genre", track.metadata.genre),
                ("subgenre", track.metadata.subgenre),
                ("composer", track.metadata.composer),
                ("comment", track.metadata.comment),
                ("grouping", track.metadata.grouping),
                ("label", track.metadata.label),
                ("copyright", track.metadata.copyright),
                ("isrc", track.metadata.isrc),
                ("musicbrainz_recording_id", track.metadata.musicbrainz_recording_id),
                ("musicbrainz_release_id", track.metadata.musicbrainz_release_id),
                ("musicbrainz_release_group_id", track.metadata.musicbrainz_release_group_id),
                ("musicbrainz_artist_id", track.metadata.musicbrainz_artist_id),
                ("discogs_release_id", track.metadata.discogs_release_id),
                ("barcode", track.metadata.barcode),
                ("catalog_number", track.metadata.catalog_number),
            ]
        )

        content_table = self._build_table(
            [
                ("mood", track.content_tags.mood),
                ("energy", track.content_tags.energy),
                ("bpm", track.content_tags.bpm),
                ("key", track.content_tags.key),
                ("vocal_presence", track.content_tags.vocal_presence),
                ("vocal_type", track.content_tags.vocal_type),
                ("instruments", track.content_tags.instruments),
                ("language", track.content_tags.language),
                ("era", track.content_tags.era),
                ("use_case", track.content_tags.use_case),
                ("texture", track.content_tags.texture),
                ("explicitness", track.content_tags.explicitness),
            ]
        )

        technical_table = self._build_table(
            [
                ("duration_sec", track.technical.duration_sec),
                ("bitrate_kbps", track.technical.bitrate_kbps),
                ("sample_rate", track.technical.sample_rate),
                ("channels", track.technical.channels),
                ("file_size_bytes", track.technical.file_size_bytes),
                ("codec", track.technical.codec),
            ]
        )

        raw_tags_table = self._build_table(
            [(key, value) for key, value in sorted(track.raw_tags.items())],
            empty_label="No raw tags were found.",
        )
        custom_tags_table = self._build_table(
            [(key, value) for key, value in sorted(track.custom_tags.items())],
            empty_label="No custom tags were found.",
        )

        tabs = QTabWidget()
        tabs.addTab(summary, "Summary")
        tabs.addTab(metadata_table, "Metadata")
        tabs.addTab(content_table, "Content Tags")
        tabs.addTab(technical_table, "Technical")
        tabs.addTab(raw_tags_table, f"Raw Tags ({len(track.raw_tags)})")
        tabs.addTab(custom_tags_table, f"Custom Tags ({len(track.custom_tags)})")
        layout.addWidget(tabs)

        button_box = QDialogButtonBox(QDialogButtonBox.Close)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def _build_table(self, rows, *, empty_label: str = "No values found.") -> QTableWidget:
        if not rows:
            rows = [("(none)", empty_label)]

        table = QTableWidget(len(rows), 2)
        table.setHorizontalHeaderLabels(["Field", "Value"])
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)

        for row_index, (field_name, value) in enumerate(rows):
            table.setItem(row_index, 0, QTableWidgetItem(str(field_name)))
            table.setItem(row_index, 1, QTableWidgetItem(self._format_value(value)))
        return table

    @staticmethod
    def _format_value(value) -> str:
        if value in (None, "", []):
            return "(missing)"
        if isinstance(value, list):
            return ", ".join(str(item) for item in value) if value else "(missing)"
        return str(value)

    @staticmethod
    def _format_pair(first: int | None, second: int | None) -> str:
        if first is None and second is None:
            return "(missing)"
        if second is None:
            return str(first)
        return f"{first or 0}/{second}"


class EditTagsDialog(QDialog):
    """Edit a track's writable canonical tags before previewing and applying them."""

    def __init__(self, track, parent=None) -> None:
        super().__init__(parent)
        self._original_track = track
        self.setWindowTitle("Edit Tags")
        self.resize(760, 720)

        layout = QVBoxLayout(self)

        intro = QLabel(
            "Edit the current tags for this file. Multi-value fields use comma-separated values."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        tabs = QTabWidget()
        tabs.addTab(self._build_metadata_tab(track), "Metadata")
        tabs.addTab(self._build_content_tab(track), "Content Tags")
        layout.addWidget(tabs)

        button_box = QDialogButtonBox(QDialogButtonBox.Cancel | QDialogButtonBox.Ok)
        self.save_button = button_box.button(QDialogButtonBox.Ok)
        self.save_button.setText("Preview Changes")
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def _build_metadata_tab(self, track) -> QWidget:
        widget = QWidget()
        form = QFormLayout(widget)

        self.title_input = QLineEdit(track.metadata.title or "")
        self.artist_input = QLineEdit(", ".join(track.metadata.artist))
        self.album_input = QLineEdit(track.metadata.album or "")
        self.album_artist_input = QLineEdit(", ".join(track.metadata.album_artist))
        self.track_number_input = QLineEdit(self._string_value(track.metadata.track_number))
        self.track_total_input = QLineEdit(self._string_value(track.metadata.track_total))
        self.disc_number_input = QLineEdit(self._string_value(track.metadata.disc_number))
        self.disc_total_input = QLineEdit(self._string_value(track.metadata.disc_total))
        self.release_date_input = QLineEdit(track.metadata.release_date or "")
        self.original_date_input = QLineEdit(track.metadata.original_date or "")
        self.genre_input = QLineEdit(", ".join(track.metadata.genre))
        self.subgenre_input = QLineEdit(", ".join(track.metadata.subgenre))
        self.composer_input = QLineEdit(", ".join(track.metadata.composer))
        self.grouping_input = QLineEdit(track.metadata.grouping or "")
        self.label_input = QLineEdit(track.metadata.label or "")
        self.copyright_input = QLineEdit(track.metadata.copyright or "")
        self.isrc_input = QLineEdit(track.metadata.isrc or "")
        self.musicbrainz_recording_id_input = QLineEdit(track.metadata.musicbrainz_recording_id or "")
        self.musicbrainz_release_id_input = QLineEdit(track.metadata.musicbrainz_release_id or "")
        self.musicbrainz_release_group_id_input = QLineEdit(track.metadata.musicbrainz_release_group_id or "")
        self.musicbrainz_artist_id_input = QLineEdit(", ".join(track.metadata.musicbrainz_artist_id))
        self.discogs_release_id_input = QLineEdit(track.metadata.discogs_release_id or "")
        self.barcode_input = QLineEdit(track.metadata.barcode or "")
        self.catalog_number_input = QLineEdit(track.metadata.catalog_number or "")
        self.comment_input = QPlainTextEdit()
        self.comment_input.setPlainText(track.metadata.comment or "")
        self.comment_input.setMaximumHeight(90)

        form.addRow("Title", self.title_input)
        form.addRow("Artist", self.artist_input)
        form.addRow("Album", self.album_input)
        form.addRow("Album artist", self.album_artist_input)
        form.addRow("Track number", self.track_number_input)
        form.addRow("Track total", self.track_total_input)
        form.addRow("Disc number", self.disc_number_input)
        form.addRow("Disc total", self.disc_total_input)
        form.addRow("Release date", self.release_date_input)
        form.addRow("Original date", self.original_date_input)
        form.addRow("Genre", self.genre_input)
        form.addRow("Subgenre", self.subgenre_input)
        form.addRow("Composer", self.composer_input)
        form.addRow("Grouping", self.grouping_input)
        form.addRow("Label", self.label_input)
        form.addRow("Copyright", self.copyright_input)
        form.addRow("ISRC", self.isrc_input)
        form.addRow("MusicBrainz recording ID", self.musicbrainz_recording_id_input)
        form.addRow("MusicBrainz release ID", self.musicbrainz_release_id_input)
        form.addRow("MusicBrainz release group ID", self.musicbrainz_release_group_id_input)
        form.addRow("MusicBrainz artist IDs", self.musicbrainz_artist_id_input)
        form.addRow("Discogs release ID", self.discogs_release_id_input)
        form.addRow("Barcode", self.barcode_input)
        form.addRow("Catalog number", self.catalog_number_input)
        form.addRow("Comment", self.comment_input)
        return widget

    def _build_content_tab(self, track) -> QWidget:
        widget = QWidget()
        form = QFormLayout(widget)

        self.mood_input = QLineEdit(", ".join(track.content_tags.mood))
        self.energy_input = QLineEdit(track.content_tags.energy or "")
        self.bpm_input = QLineEdit(self._string_value(track.content_tags.bpm))
        self.key_input = QLineEdit(track.content_tags.key or "")
        self.vocal_presence_input = QLineEdit(track.content_tags.vocal_presence or "")
        self.vocal_type_input = QLineEdit(", ".join(track.content_tags.vocal_type))
        self.instruments_input = QLineEdit(", ".join(track.content_tags.instruments))
        self.language_input = QLineEdit(", ".join(track.content_tags.language))
        self.era_input = QLineEdit(", ".join(track.content_tags.era))
        self.use_case_input = QLineEdit(", ".join(track.content_tags.use_case))
        self.texture_input = QLineEdit(", ".join(track.content_tags.texture))
        self.explicitness_input = QLineEdit(track.content_tags.explicitness or "")

        form.addRow("Mood", self.mood_input)
        form.addRow("Energy", self.energy_input)
        form.addRow("BPM", self.bpm_input)
        form.addRow("Key", self.key_input)
        form.addRow("Vocal presence", self.vocal_presence_input)
        form.addRow("Vocal type", self.vocal_type_input)
        form.addRow("Instruments", self.instruments_input)
        form.addRow("Language", self.language_input)
        form.addRow("Era", self.era_input)
        form.addRow("Use case", self.use_case_input)
        form.addRow("Texture", self.texture_input)
        form.addRow("Explicitness", self.explicitness_input)
        return widget

    def build_track(self):
        track = self._original_track.clone()

        track.metadata.title = self._optional_text(self.title_input.text())
        track.metadata.artist = self._list_value(self.artist_input.text())
        track.metadata.album = self._optional_text(self.album_input.text())
        track.metadata.album_artist = self._list_value(self.album_artist_input.text())
        track.metadata.track_number = self._optional_int(self.track_number_input.text())
        track.metadata.track_total = self._optional_int(self.track_total_input.text())
        track.metadata.disc_number = self._optional_int(self.disc_number_input.text())
        track.metadata.disc_total = self._optional_int(self.disc_total_input.text())
        track.metadata.release_date = self._optional_text(self.release_date_input.text())
        track.metadata.original_date = self._optional_text(self.original_date_input.text())
        track.metadata.genre = self._list_value(self.genre_input.text())
        track.metadata.subgenre = self._list_value(self.subgenre_input.text())
        track.metadata.composer = self._list_value(self.composer_input.text())
        track.metadata.grouping = self._optional_text(self.grouping_input.text())
        track.metadata.label = self._optional_text(self.label_input.text())
        track.metadata.copyright = self._optional_text(self.copyright_input.text())
        track.metadata.isrc = self._optional_text(self.isrc_input.text())
        track.metadata.musicbrainz_recording_id = self._optional_text(self.musicbrainz_recording_id_input.text())
        track.metadata.musicbrainz_release_id = self._optional_text(self.musicbrainz_release_id_input.text())
        track.metadata.musicbrainz_release_group_id = self._optional_text(self.musicbrainz_release_group_id_input.text())
        track.metadata.musicbrainz_artist_id = self._list_value(self.musicbrainz_artist_id_input.text())
        track.metadata.discogs_release_id = self._optional_text(self.discogs_release_id_input.text())
        track.metadata.barcode = self._optional_text(self.barcode_input.text())
        track.metadata.catalog_number = self._optional_text(self.catalog_number_input.text())
        track.metadata.comment = self._optional_text(self.comment_input.toPlainText())

        track.content_tags.mood = self._list_value(self.mood_input.text())
        track.content_tags.energy = self._optional_text(self.energy_input.text())
        track.content_tags.bpm = self._optional_int(self.bpm_input.text())
        track.content_tags.key = self._optional_text(self.key_input.text())
        track.content_tags.vocal_presence = self._optional_text(self.vocal_presence_input.text())
        track.content_tags.vocal_type = self._list_value(self.vocal_type_input.text())
        track.content_tags.instruments = self._list_value(self.instruments_input.text())
        track.content_tags.language = self._list_value(self.language_input.text())
        track.content_tags.era = self._list_value(self.era_input.text())
        track.content_tags.use_case = self._list_value(self.use_case_input.text())
        track.content_tags.texture = self._list_value(self.texture_input.text())
        track.content_tags.explicitness = self._optional_text(self.explicitness_input.text())
        return track

    @staticmethod
    def _optional_text(value: str) -> str | None:
        cleaned = value.strip()
        return cleaned or None

    @staticmethod
    def _list_value(value: str) -> list[str]:
        return [item.strip() for item in value.split(",") if item.strip()]

    @staticmethod
    def _optional_int(value: str) -> int | None:
        cleaned = value.strip()
        if not cleaned:
            return None
        return int(cleaned)

    @staticmethod
    def _string_value(value: int | None) -> str:
        return "" if value is None else str(value)


class AlbumTagPreviewDialog(QDialog):
    """Review proposed tag and rename changes for one selected album."""

    def __init__(self, album_name: str, track_rows: list[dict[str, object]], album_issues: list[dict[str, object]], parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Album Tagging Preview")
        self.resize(1100, 700)

        layout = QVBoxLayout(self)

        total_changes = sum(int(row["change_count"]) for row in track_rows)
        review_count = sum(1 for row in track_rows if row["review_required"])
        rename_count = sum(1 for row in track_rows if row["rename_required"])

        summary = QPlainTextEdit()
        summary.setReadOnly(True)
        summary.setLineWrapMode(QPlainTextEdit.NoWrap)
        summary.setPlainText(
            "\n".join(
                [
                    f"Album: {album_name}",
                    f"Tracks: {len(track_rows)}",
                    f"Tracks requiring review: {review_count}",
                    f"Tracks with rename targets: {rename_count}",
                    f"Total field changes: {total_changes}",
                    "",
                    "Album consistency issues",
                    *self._format_album_issues(album_issues),
                ]
            )
        )

        tracks_table = QTableWidget(len(track_rows), 8)
        tracks_table.setHorizontalHeaderLabels(
            ["Track", "Score", "Review", "Changes", "Current Title", "Proposed Title", "Current Path", "Target Path"]
        )
        tracks_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        tracks_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        tracks_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        tracks_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        for column in range(4, 8):
            tracks_table.horizontalHeader().setSectionResizeMode(column, QHeaderView.Stretch)
        tracks_table.verticalHeader().setVisible(False)
        tracks_table.setEditTriggers(QAbstractItemView.NoEditTriggers)

        for row_index, row in enumerate(track_rows):
            tracks_table.setItem(row_index, 0, QTableWidgetItem(str(row["track_name"])))
            tracks_table.setItem(row_index, 1, QTableWidgetItem(self._format_score(row["score"])))
            tracks_table.setItem(row_index, 2, QTableWidgetItem("Yes" if row["review_required"] else "No"))
            tracks_table.setItem(row_index, 3, QTableWidgetItem(str(row["change_count"])))
            tracks_table.setItem(row_index, 4, QTableWidgetItem(str(row["current_title"])))
            tracks_table.setItem(row_index, 5, QTableWidgetItem(str(row["proposed_title"])))
            tracks_table.setItem(row_index, 6, QTableWidgetItem(str(row["current_path"])))
            tracks_table.setItem(row_index, 7, QTableWidgetItem(str(row["target_path"])))

        changes_table = QTableWidget(sum(len(row["changes"]) for row in track_rows), 4)
        changes_table.setHorizontalHeaderLabels(["Track", "Field", "Before", "After"])
        changes_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        changes_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        changes_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        changes_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        changes_table.verticalHeader().setVisible(False)
        changes_table.setEditTriggers(QAbstractItemView.NoEditTriggers)

        change_row = 0
        for row in track_rows:
            for change in row["changes"]:
                changes_table.setItem(change_row, 0, QTableWidgetItem(str(row["track_name"])))
                changes_table.setItem(change_row, 1, QTableWidgetItem(change.field_path))
                changes_table.setItem(change_row, 2, QTableWidgetItem(TagPreviewDialog._format_value(change.before)))
                changes_table.setItem(change_row, 3, QTableWidgetItem(TagPreviewDialog._format_value(change.after)))
                change_row += 1

        tabs = QTabWidget()
        tabs.addTab(summary, "Summary")
        tabs.addTab(tracks_table, f"Tracks ({len(track_rows)})")
        tabs.addTab(changes_table, f"Changes ({total_changes})")
        layout.addWidget(tabs)

        button_box = QDialogButtonBox(QDialogButtonBox.Close)
        self.accept_button = button_box.addButton("Apply Album Tags", QDialogButtonBox.AcceptRole)
        self.close_button = button_box.button(QDialogButtonBox.Close)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    @staticmethod
    def _format_album_issues(album_issues: list[dict[str, object]]) -> list[str]:
        if not album_issues:
            return ["  (none)"]
        return [
            f"  {issue.get('field', 'unknown')}: {', '.join(str(value) for value in issue.get('values', []))}"
            for issue in album_issues
        ]

    @staticmethod
    def _format_score(score: object) -> str:
        return f"{float(score):.4f}" if isinstance(score, (float, int)) else "(missing)"


class MainWindow(QWidget):
    """Main application window for browsing music and creating playlists."""

    def __init__(self) -> None:
        super().__init__()
        self.state = PlaylistState()
        self.settings_store = AppSettingsStore()
        self.settings = AppSettings()
        self.tagging_service = TaggingService(acoustid_api_key=os.environ.get("ACOUSTID_API_KEY"))

        self.setWindowTitle("Walkman Playlist Creator")
        self.resize(1000, 600)

        self._build_widgets()
        self._build_layout()
        self._connect_signals()
        self._load_saved_music_locations()
        self._update_root_label()

    def _build_widgets(self) -> None:
        self.root_label = QLabel()
        self.music_location_combo = QComboBox()
        self.music_location_combo.setPlaceholderText("No saved music locations")
        self.choose_root_btn = QPushButton("Add Music Location")
        self.remove_location_btn = QPushButton("Remove Selected Location")
        self.scan_btn = QPushButton("Scan Folder")

        self.playlist_search_input = QLineEdit()
        self.playlist_search_input.setPlaceholderText("Filter library for playlist building")
        self.tag_search_input = QLineEdit()
        self.tag_search_input.setPlaceholderText("Filter library for tagging")

        self.playlist_library_model = QStandardItemModel(self)
        self.playlist_library_proxy = QSortFilterProxyModel(self)
        self.playlist_library_proxy.setSourceModel(self.playlist_library_model)
        self.playlist_library_proxy.setFilterCaseSensitivity(Qt.CaseInsensitive)
        self.playlist_library_proxy.setFilterKeyColumn(0)
        self.playlist_library_proxy.setRecursiveFilteringEnabled(True)

        self.playlist_library_view = QTreeView()
        self.playlist_library_view.setModel(self.playlist_library_proxy)
        self.playlist_library_view.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.playlist_library_view.setHeaderHidden(True)
        self.playlist_library_view.setUniformRowHeights(True)
        self.playlist_library_view.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        self.tag_library_model = QStandardItemModel(self)
        self.tag_library_proxy = QSortFilterProxyModel(self)
        self.tag_library_proxy.setSourceModel(self.tag_library_model)
        self.tag_library_proxy.setFilterCaseSensitivity(Qt.CaseInsensitive)
        self.tag_library_proxy.setFilterKeyColumn(0)
        self.tag_library_proxy.setRecursiveFilteringEnabled(True)

        self.tag_library_view = QTreeView()
        self.tag_library_view.setModel(self.tag_library_proxy)
        self.tag_library_view.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tag_library_view.setHeaderHidden(True)
        self.tag_library_view.setUniformRowHeights(True)
        self.tag_library_view.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.tag_library_view.setContextMenuPolicy(Qt.CustomContextMenu)

        self.playlist_widget = QListWidget()
        self.playlist_widget.setSelectionMode(QAbstractItemView.SingleSelection)
        self.playlist_widget.setDragDropMode(QAbstractItemView.InternalMove)
        self.playlist_widget.setDefaultDropAction(Qt.MoveAction)

        self.add_btn = QPushButton("Add ->")
        self.remove_btn = QPushButton("Remove")
        self.up_btn = QPushButton("Move Up")
        self.down_btn = QPushButton("Move Down")
        self.clear_btn = QPushButton("Clear Playlist")
        self.save_btn = QPushButton("Save Playlist (.m3u8)")
        self.edit_tag_btn = QPushButton("Edit Tags")
        self.edit_tag_btn.setToolTip("Edit current tags for one selected track before previewing changes.")
        self.preview_tag_btn = QPushButton("Preview Tags")
        self.preview_tag_btn.setToolTip("Preview proposed tags for one selected track before applying them.")
        self.preview_album_tag_btn = QPushButton("Preview Album Tags")
        self.preview_album_tag_btn.setToolTip("Preview and apply tags for every track in one selected album.")

        self.main_tabs = QTabWidget()
        self.playlist_tab = QWidget()
        self.tagging_tab = QWidget()
        self.settings_tab = QWidget()

        self.tag_cover_label = QLabel("No cover art")
        self.tag_cover_label.setAlignment(Qt.AlignCenter)
        self.tag_cover_label.setMinimumSize(220, 220)
        self.tag_cover_label.setStyleSheet("border: 1px solid #555; padding: 8px;")

        self.tag_selection_summary = QPlainTextEdit()
        self.tag_selection_summary.setReadOnly(True)
        self.tag_selection_summary.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.tag_selection_summary.setPlaceholderText("Select an album or track to view tags and details.")

        self.tag_tracks_table = QTableWidget(0, 4)
        self.tag_tracks_table.setHorizontalHeaderLabels(["#", "Title", "Artist", "Path"])
        self.tag_tracks_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.tag_tracks_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.tag_tracks_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.tag_tracks_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.tag_tracks_table.verticalHeader().setVisible(False)
        self.tag_tracks_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tag_tracks_table.setSelectionMode(QAbstractItemView.NoSelection)

        self.tag_metadata_table = QTableWidget(0, 2)
        self.tag_metadata_table.setHorizontalHeaderLabels(["Field", "Value"])
        self.tag_metadata_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.tag_metadata_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.tag_metadata_table.verticalHeader().setVisible(False)
        self.tag_metadata_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tag_metadata_table.setSelectionMode(QAbstractItemView.NoSelection)

        self.rename_enabled_checkbox = QCheckBox("Enable automatic renaming after tag apply")
        self.album_level_folder_checkbox = QCheckBox("Build album folder names from album-wide tag aggregate")
        self.replace_existing_checkbox = QCheckBox("Replace existing files when target path already exists")
        self.cleanup_dirs_checkbox = QCheckBox("Remove empty source folders after moving tracks")
        self.folder_template_input = QLineEdit()
        self.file_template_input = QLineEdit()
        self.rename_settings_status = QLabel()
        self.rename_preview_label = QPlainTextEdit()
        self.rename_preview_label.setReadOnly(True)
        self.rename_preview_label.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.save_rename_settings_btn = QPushButton("Save Rename Settings")
        self.reset_rename_defaults_btn = QPushButton("Reset Rename Defaults")

    def _build_layout(self) -> None:
        top_row = QHBoxLayout()
        top_row.addWidget(self.root_label)
        top_row.addWidget(self.music_location_combo, stretch=1)
        top_row.addWidget(self.choose_root_btn)
        top_row.addWidget(self.remove_location_btn)
        top_row.addWidget(self.scan_btn)

        playlist_left_col = QVBoxLayout()
        playlist_left_col.addWidget(QLabel("Library"))
        playlist_left_col.addWidget(self.playlist_search_input)
        playlist_left_col.addWidget(self.playlist_library_view)

        center_col = QVBoxLayout()
        center_col.addStretch()
        center_col.addWidget(self.add_btn)
        center_col.addWidget(self.remove_btn)
        center_col.addWidget(self.up_btn)
        center_col.addWidget(self.down_btn)
        center_col.addWidget(self.clear_btn)
        center_col.addStretch()

        right_col = QVBoxLayout()
        right_col.addWidget(QLabel("Playlist (drag to reorder)"))
        right_col.addWidget(self.playlist_widget)
        right_col.addWidget(self.save_btn)

        left_widget = QWidget()
        left_widget.setLayout(playlist_left_col)

        center_widget = QWidget()
        center_widget.setLayout(center_col)

        right_widget = QWidget()
        right_widget.setLayout(right_col)

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(left_widget)
        splitter.addWidget(center_widget)
        splitter.addWidget(right_widget)
        splitter.setSizes([400, 100, 400])

        playlist_tab_layout = QVBoxLayout(self.playlist_tab)
        playlist_tab_layout.addWidget(splitter)

        tag_actions = QHBoxLayout()
        tag_actions.addWidget(self.edit_tag_btn)
        tag_actions.addWidget(self.preview_tag_btn)
        tag_actions.addWidget(self.preview_album_tag_btn)
        tag_actions.addStretch()

        tag_left_col = QVBoxLayout()
        tag_left_col.addWidget(QLabel("Library"))
        tag_left_col.addWidget(self.tag_search_input)
        tag_left_col.addWidget(self.tag_library_view)
        tag_left_col.addLayout(tag_actions)

        tag_header = QHBoxLayout()
        tag_header.addWidget(self.tag_cover_label, stretch=0)
        tag_header.addWidget(self.tag_selection_summary, stretch=1)

        tag_detail_tabs = QTabWidget()
        tag_detail_tabs.addTab(self.tag_tracks_table, "Tracks")
        tag_detail_tabs.addTab(self.tag_metadata_table, "Tag Details")

        tag_right_col = QVBoxLayout()
        tag_right_col.addLayout(tag_header)
        tag_right_col.addWidget(tag_detail_tabs)

        tag_left_widget = QWidget()
        tag_left_widget.setLayout(tag_left_col)
        tag_right_widget = QWidget()
        tag_right_widget.setLayout(tag_right_col)

        tag_splitter = QSplitter(Qt.Horizontal)
        tag_splitter.addWidget(tag_left_widget)
        tag_splitter.addWidget(tag_right_widget)
        tag_splitter.setSizes([360, 640])

        tagging_tab_layout = QVBoxLayout(self.tagging_tab)
        tagging_tab_layout.addWidget(tag_splitter)

        self.folder_template_input.setPlaceholderText("{album_artist} - {album} ({release_year}) [{file_type}]")
        self.file_template_input.setPlaceholderText("{track_number_padded} {title}")
        self.folder_template_input.setMinimumWidth(520)
        self.file_template_input.setMinimumWidth(520)
        self.rename_settings_status.setWordWrap(True)

        settings_form = QFormLayout()
        settings_form.addRow(self.rename_enabled_checkbox)
        settings_form.addRow(self.album_level_folder_checkbox)
        settings_form.addRow(self.replace_existing_checkbox)
        settings_form.addRow(self.cleanup_dirs_checkbox)
        settings_form.addRow("Album folder template", self.folder_template_input)
        settings_form.addRow("Track file template", self.file_template_input)

        settings_help = QLabel(
            "Available fields: album_artist, artist, album, title, release_year, "
            "track_number, track_number_padded, disc_number, disc_number_padded, "
            "file_type, file_extension"
        )
        settings_help.setWordWrap(True)

        settings_buttons = QHBoxLayout()
        settings_buttons.addWidget(self.save_rename_settings_btn)
        settings_buttons.addWidget(self.reset_rename_defaults_btn)
        settings_buttons.addStretch()

        settings_content = QWidget()
        settings_content_layout = QVBoxLayout(settings_content)
        settings_content_layout.addLayout(settings_form)
        settings_content_layout.addWidget(settings_help)
        settings_content_layout.addWidget(QLabel("Preview"))
        settings_content_layout.addWidget(self.rename_preview_label)
        settings_content_layout.addWidget(self.rename_settings_status)
        settings_content_layout.addLayout(settings_buttons)
        settings_content_layout.addStretch()

        settings_scroll = QScrollArea()
        settings_scroll.setWidgetResizable(True)
        settings_scroll.setWidget(settings_content)

        settings_tab_layout = QVBoxLayout(self.settings_tab)
        settings_tab_layout.addWidget(settings_scroll)

        self.main_tabs.addTab(self.playlist_tab, "Playlists")
        self.main_tabs.addTab(self.tagging_tab, "View/Update Tags")
        self.main_tabs.addTab(self.settings_tab, "Settings")

        layout = QVBoxLayout(self)
        layout.addLayout(top_row)
        layout.addWidget(self.main_tabs)

    def _connect_signals(self) -> None:
        self.choose_root_btn.clicked.connect(self.choose_root)
        self.remove_location_btn.clicked.connect(self.remove_selected_music_location)
        self.music_location_combo.currentIndexChanged.connect(self.change_music_location)
        self.scan_btn.clicked.connect(self.scan_folder)
        self.playlist_search_input.textChanged.connect(self.filter_playlist_library)
        self.tag_search_input.textChanged.connect(self.filter_tag_library)
        self.playlist_library_view.doubleClicked.connect(self.handle_playlist_library_double_click)
        self.tag_library_view.customContextMenuRequested.connect(self.show_tag_library_context_menu)
        self.tag_library_view.selectionModel().selectionChanged.connect(self.refresh_tag_selection_details)
        self.tag_library_view.selectionModel().currentChanged.connect(self.refresh_tag_selection_details)
        self.tag_library_view.clicked.connect(self.refresh_tag_selection_details)
        self.add_btn.clicked.connect(self.add_selected_to_playlist)
        self.remove_btn.clicked.connect(self.remove_selected_from_playlist)
        self.up_btn.clicked.connect(self.move_up)
        self.down_btn.clicked.connect(self.move_down)
        self.clear_btn.clicked.connect(self.clear_playlist)
        self.save_btn.clicked.connect(self.save_playlist)
        self.edit_tag_btn.clicked.connect(self.edit_selected_track_tags)
        self.preview_tag_btn.clicked.connect(self.preview_selected_track_tags)
        self.preview_album_tag_btn.clicked.connect(self.preview_selected_album_tags)
        self.playlist_widget.model().rowsMoved.connect(self._sync_playlist_from_widget)
        self.save_rename_settings_btn.clicked.connect(self.save_rename_settings)
        self.reset_rename_defaults_btn.clicked.connect(self.reset_rename_settings_defaults)
        self.rename_enabled_checkbox.toggled.connect(self._refresh_rename_settings_preview)
        self.album_level_folder_checkbox.toggled.connect(self._refresh_rename_settings_preview)
        self.replace_existing_checkbox.toggled.connect(self._refresh_rename_settings_preview)
        self.cleanup_dirs_checkbox.toggled.connect(self._refresh_rename_settings_preview)
        self.folder_template_input.textChanged.connect(self._refresh_rename_settings_preview)
        self.file_template_input.textChanged.connect(self._refresh_rename_settings_preview)

    def _update_root_label(self) -> None:
        if self.state.root_folder is None:
            count = len(self.state.music_directories)
            label = "1 saved location" if count == 1 else f"{count} saved locations"
            self.root_label.setText(f"Active Music Location: (none) | {label}")
            return

        count = len(self.state.music_directories)
        label = "1 saved location" if count == 1 else f"{count} saved locations"
        self.root_label.setText(f"Active Music Location: {self.state.root_folder} | {label}")

    def _load_saved_music_locations(self) -> None:
        self.settings = self.settings_store.load()
        folders = self._existing_music_directories(self.settings.music_directories)
        self.state.set_music_directories(folders)

        selected_folder = None
        if self.settings.selected_music_directory:
            selected_candidate = Path(self.settings.selected_music_directory)
            if selected_candidate in folders:
                selected_folder = selected_candidate
        if selected_folder is None and folders:
            selected_folder = folders[0]

        self.state.set_root_folder(selected_folder)
        self._refresh_music_location_combo()
        self._load_rename_settings_ui()
        log_music_locations_loaded(len(folders), selected_folder)

        if selected_folder is not None:
            self.scan_folder(show_feedback=False)

    def _refresh_music_location_combo(self) -> None:
        blocker = QSignalBlocker(self.music_location_combo)
        self.music_location_combo.clear()

        for folder in self.state.music_directories:
            self.music_location_combo.addItem(str(folder), folder)

        if self.state.root_folder is not None:
            index = self.music_location_combo.findData(self.state.root_folder)
            if index >= 0:
                self.music_location_combo.setCurrentIndex(index)
        del blocker

    def _save_music_location_settings(self, operation: str) -> bool:
        return self._save_settings(operation)

    def _save_settings(self, operation: str) -> bool:
        self.settings = AppSettings(
            music_directories=[str(folder) for folder in self.state.music_directories],
            selected_music_directory=str(self.state.root_folder) if self.state.root_folder else None,
            rename_config=self.settings.rename_config,
        )
        try:
            self.settings_store.save(self.settings)
        except OSError as exc:
            log_settings_save_failed(operation, exc)
            QMessageBox.critical(self, "Settings Save Failed", f"Could not save music locations: {exc}")
            return False
        return True

    @staticmethod
    def _existing_music_directories(directory_values: list[str]) -> list[Path]:
        folders: list[Path] = []
        for value in directory_values:
            folder = Path(value).expanduser()
            if folder.exists() and folder.is_dir() and folder not in folders:
                folders.append(folder)
        return folders

    def choose_root(self) -> None:
        selected = QFileDialog.getExistingDirectory(
            self,
            "Select Music Location",
            str(Path.home()),
        )
        if not selected:
            log_root_selection_cancelled()
            return

        selected_folder = Path(selected)
        added = self.state.add_music_directory(selected_folder)
        self.state.set_root_folder(selected_folder)
        self._refresh_music_location_combo()
        self._update_root_label()
        if not self._save_music_location_settings("add_music_location"):
            return

        log_root_selected(self.state.root_folder)
        if added:
            log_music_location_added(selected_folder, len(self.state.music_directories))
        log_music_location_activated(selected_folder)
        self.scan_folder(show_feedback=False)

    def remove_selected_music_location(self) -> None:
        current_folder = self.state.root_folder
        if current_folder is None:
            QMessageBox.information(self, "No Location Selected", "Select a saved music location first.")
            return

        removed = self.state.remove_music_directory(current_folder)
        if not removed:
            return

        next_folder = self.state.music_directories[0] if self.state.music_directories else None
        self.state.set_root_folder(next_folder)
        if next_folder is None:
            self.state.clear_library()
            self.populate_library()

        self._refresh_music_location_combo()
        self._update_root_label()
        if not self._save_music_location_settings("remove_music_location"):
            return

        log_music_location_removed(current_folder, len(self.state.music_directories))
        if next_folder is not None:
            log_music_location_activated(next_folder)
            self.scan_folder(show_feedback=False)

    def change_music_location(self, index: int) -> None:
        if index < 0:
            return

        selected_data = self.music_location_combo.itemData(index)
        if not isinstance(selected_data, Path):
            return
        if self.state.root_folder == selected_data:
            return

        self.state.set_root_folder(selected_data)
        self._update_root_label()
        if not self._save_music_location_settings("change_music_location"):
            return

        log_music_location_activated(selected_data)
        self.scan_folder(show_feedback=False)

    def scan_folder(self, *, show_feedback: bool = True) -> None:
        start = self.state.root_folder

        if start is None:
            selected = QFileDialog.getExistingDirectory(
                self,
                "Select Folder to Scan",
                str(Path.home()),
            )
            if not selected:
                log_scan_cancelled()
                return
            start = Path(selected)
            self.state.set_root_folder(start)
            if self.state.add_music_directory(start):
                self._refresh_music_location_combo()
                self._save_music_location_settings("scan_selected_music_location")
            self._update_root_label()

        log_scan_started(start, self.state.root_folder)
        albums = scan_music_files(start=start, root_folder=self.state.root_folder)
        base_folder = self.state.root_folder or start

        self.state.set_library(albums, base_folder)
        self.populate_library()

        total_tracks = sum(album.track_count for album in albums)
        log_scan_completed(start, len(albums), total_tracks)

        if show_feedback:
            QMessageBox.information(
                self,
                "Scan Complete",
                "\n".join(
                    [
                        f"Found {len(albums)} album folders and {total_tracks} audio files.",
                        f"Indexed metadata for {sum(len(album.track_metadata) for album in albums)} tracks.",
                    ]
                ),
            )

    def populate_library(self) -> None:
        self.playlist_library_model.clear()
        self.tag_library_model.clear()

        for album in self.state.library_albums:
            playlist_item = self._build_library_item(album)
            playlist_item.setEditable(False)
            self.playlist_library_model.appendRow(playlist_item)

            tag_item = self._build_library_item(album)
            tag_item.setEditable(False)
            self.tag_library_model.appendRow(tag_item)

        self.filter_playlist_library(self.playlist_search_input.text())
        self.filter_tag_library(self.tag_search_input.text())
        self.playlist_library_view.collapseAll()
        self.tag_library_view.collapseAll()
        self.refresh_tag_selection_details()

    def filter_playlist_library(self, text: str) -> None:
        self._filter_library_view(self.playlist_library_proxy, self.playlist_library_view, text)

    def filter_tag_library(self, text: str) -> None:
        self._filter_library_view(self.tag_library_proxy, self.tag_library_view, text)

    @staticmethod
    def _filter_library_view(proxy, view, text: str) -> None:
        proxy.setFilterFixedString(text.strip())
        if text.strip():
            view.expandAll()
        else:
            view.collapseAll()

    def get_selected_library_tracks(self) -> list[str]:
        indexes = self.playlist_library_view.selectionModel().selectedIndexes()
        tracks: list[str] = []

        for proxy_index in indexes:
            source_index = self.playlist_library_proxy.mapToSource(proxy_index)
            item = self.playlist_library_model.itemFromIndex(source_index)
            if item is not None:
                tracks.extend(item.data(ALBUM_TRACKS_ROLE) or [])

        return tracks

    def handle_playlist_library_double_click(self, proxy_index) -> None:
        source_index = self.playlist_library_proxy.mapToSource(proxy_index)
        item = self.playlist_library_model.itemFromIndex(source_index)

        if item is None:
            return

        if item.hasChildren():
            expanded = not self.playlist_library_view.isExpanded(proxy_index)
            self.playlist_library_view.setExpanded(proxy_index, expanded)
            log_album_toggled(item.text(), expanded)
            return

        self.add_tracks_to_playlist(
            item.data(ALBUM_TRACKS_ROLE) or [],
            source="library_double_click",
        )

    def show_tag_library_context_menu(self, position) -> None:
        proxy_index = self.tag_library_view.indexAt(position)
        if not proxy_index.isValid():
            return

        source_index = self.tag_library_proxy.mapToSource(proxy_index)
        item = self.tag_library_model.itemFromIndex(source_index)
        if item is None:
            return

        selection_model = self.tag_library_view.selectionModel()
        if selection_model is not None and not selection_model.isSelected(proxy_index):
            selection_model.select(proxy_index, QItemSelectionModel.ClearAndSelect)
            self.tag_library_view.setCurrentIndex(proxy_index)

        menu = QMenu(self)
        view_tags_action = None
        edit_tags_action = None
        preview_tags_action = None
        preview_album_action = None

        if item.hasChildren():
            preview_album_action = QAction("Preview Album Tags", self)
            menu.addAction(preview_album_action)
        else:
            view_tags_action = QAction("View Current Tags", self)
            edit_tags_action = QAction("Edit Tags", self)
            preview_tags_action = QAction("Preview Tags", self)
            menu.addAction(view_tags_action)
            menu.addAction(edit_tags_action)
            menu.addAction(preview_tags_action)

        chosen_action = menu.exec(self.tag_library_view.viewport().mapToGlobal(position))
        if chosen_action is view_tags_action:
            self.view_selected_track_tags()
        elif chosen_action is edit_tags_action:
            self.edit_selected_track_tags()
        elif chosen_action is preview_tags_action:
            self.preview_selected_track_tags()
        elif chosen_action is preview_album_action:
            self.preview_selected_album_tags()

    def view_selected_track_tags(self) -> None:
        """Open a read-only dialog for one selected track's current embedded tags."""
        track_path = self.get_selected_single_track_path()
        if track_path is None:
            QMessageBox.information(
                self,
                "Select One Track",
                "Select exactly one track row in the library tree to view its current tags.",
            )
            return

        absolute_path = self.resolve_library_track_path(track_path)
        if absolute_path is None:
            QMessageBox.warning(
                self,
                "Track Not Found",
                "The selected track could not be resolved to a file on disk.",
            )
            return

        try:
            track = self.tagging_service.read_track(absolute_path)
        except Exception as exc:
            QMessageBox.critical(self, "Read Tags Failed", f"Could not read current tags: {exc}")
            return

        dialog = CurrentTagsDialog(track, parent=self)
        dialog.exec()

    def refresh_tag_selection_details(self, *args) -> None:
        """Update the tag details pane from the current tagging-tree selection."""
        selection = self._get_current_tag_selection()
        if selection is None:
            self._clear_tag_selection_details()
            return

        selection_type = selection["type"]
        track_paths = selection["track_paths"]
        absolute_paths = [path for path in (self.resolve_library_track_path(track_path) for track_path in track_paths) if path is not None]
        if not absolute_paths:
            self._clear_tag_selection_details("The selected item could not be resolved on disk.")
            return

        representative_path = self.resolve_library_track_path(str(selection["representative_track_path"])) or absolute_paths[0]
        try:
            representative_track = self.tagging_service.read_track(representative_path)
        except Exception as exc:
            self._clear_tag_selection_details(f"Could not load tag details: {exc}")
            return

        log_tag_selection_details_refreshed(
            selection_type,
            len(absolute_paths),
            str(representative_path),
        )

        self.tag_selection_summary.setPlainText(
            self._build_tag_selection_summary(selection_type, representative_track, absolute_paths)
        )
        self._populate_tag_tracks_table(track_paths)
        self._populate_tag_metadata_table(selection_type, representative_track, len(absolute_paths))
        self._update_cover_art(absolute_paths)

    def _get_current_tag_selection(self) -> dict[str, object] | None:
        indexes = self.tag_library_view.selectionModel().selectedIndexes()
        if len(indexes) != 1:
            return None

        source_index = self.tag_library_proxy.mapToSource(indexes[0])
        item = self.tag_library_model.itemFromIndex(source_index)
        if item is None:
            return None

        track_paths = item.data(ALBUM_TRACKS_ROLE) or []
        if not isinstance(track_paths, list) or not track_paths:
            return None

        selection_type = "album" if item.hasChildren() else "track"
        representative_track_path = track_paths[0]
        if selection_type == "track":
            selected_track_path = track_paths[0]
            track_paths = self._get_album_track_paths_for_track(selected_track_path)
            representative_track_path = selected_track_path

        return {
            "type": selection_type,
            "track_paths": list(track_paths),
            "representative_track_path": representative_track_path,
            "label": item.text(),
        }

    def _clear_tag_selection_details(self, message: str = "Select an album or track to view tags and details.") -> None:
        self.tag_cover_label.setPixmap(QPixmap())
        self.tag_cover_label.setText("No cover art")
        self.tag_cover_label.setToolTip("")
        self.tag_selection_summary.setPlainText(message)
        self.tag_tracks_table.setRowCount(0)
        self.tag_metadata_table.setRowCount(0)

    def _build_tag_selection_summary(self, selection_type: str, track, absolute_paths: list[Path]) -> str:
        title = track.metadata.title or Path(track.file_path).name
        album = track.metadata.album or Path(track.file_path).parent.name
        artist = ", ".join(track.metadata.artist) if track.metadata.artist else "(missing)"
        album_artist = ", ".join(track.metadata.album_artist) if track.metadata.album_artist else artist
        genre = ", ".join(track.metadata.genre) if track.metadata.genre else "(missing)"
        return "\n".join(
            [
                f"Selection: {'Album' if selection_type == 'album' else 'Track'}",
                f"Album: {album}",
                f"Album artist: {album_artist}",
                f"Representative track: {title}",
                f"Track artist: {artist}",
                f"Release date: {track.metadata.release_date or '(missing)'}",
                f"Genre: {genre}",
                f"File type: {track.file_format}",
                f"Tracks in selection: {len(absolute_paths)}",
                f"Folder: {Path(track.file_path).parent}",
            ]
        )

    def _populate_tag_tracks_table(self, track_paths: list[str]) -> None:
        rows: list[tuple[str, str, str, str]] = []
        for track_path in track_paths:
            metadata = self._find_track_scan_metadata(track_path)
            if metadata is not None:
                rows.append(
                    (
                        str(metadata.track_number or ""),
                        metadata.title or metadata.file_name,
                        ", ".join(metadata.artist) if metadata.artist else "(missing)",
                        metadata.relative_path,
                    )
                )
            else:
                rows.append(("", Path(track_path).name, "(missing)", track_path))

        self.tag_tracks_table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            for column_index, value in enumerate(row):
                self.tag_tracks_table.setItem(row_index, column_index, QTableWidgetItem(value))

    def _populate_tag_metadata_table(self, selection_type: str, track, track_count: int) -> None:
        rows = [
            ("selection_type", "album" if selection_type == "album" else "track"),
            ("file_path", track.file_path),
            ("file_format", track.file_format),
            ("title", track.metadata.title or "(missing)"),
            ("artist", self._join_values(track.metadata.artist)),
            ("album", track.metadata.album or "(missing)"),
            ("album_artist", self._join_values(track.metadata.album_artist)),
            ("track_number", self._format_value(track.metadata.track_number)),
            ("track_total", self._format_value(track.metadata.track_total)),
            ("disc_number", self._format_value(track.metadata.disc_number)),
            ("disc_total", self._format_value(track.metadata.disc_total)),
            ("release_date", track.metadata.release_date or "(missing)"),
            ("original_date", track.metadata.original_date or "(missing)"),
            ("genre", self._join_values(track.metadata.genre)),
            ("subgenre", self._join_values(track.metadata.subgenre)),
            ("label", track.metadata.label or "(missing)"),
            ("catalog_number", track.metadata.catalog_number or "(missing)"),
            ("barcode", track.metadata.barcode or "(missing)"),
            ("isrc", track.metadata.isrc or "(missing)"),
            ("mood", self._join_values(track.content_tags.mood)),
            ("bpm", self._format_value(track.content_tags.bpm)),
            ("key", track.content_tags.key or "(missing)"),
            ("language", self._join_values(track.content_tags.language)),
            ("duration_sec", self._format_value(track.technical.duration_sec)),
            ("bitrate_kbps", self._format_value(track.technical.bitrate_kbps)),
            ("sample_rate", self._format_value(track.technical.sample_rate)),
            ("channels", self._format_value(track.technical.channels)),
            ("tracks_in_selection", str(track_count)),
        ]
        self.tag_metadata_table.setRowCount(len(rows))
        for row_index, (field_name, value) in enumerate(rows):
            self.tag_metadata_table.setItem(row_index, 0, QTableWidgetItem(field_name))
            self.tag_metadata_table.setItem(row_index, 1, QTableWidgetItem(str(value)))

    def _update_cover_art(self, absolute_paths: list[Path]) -> None:
        pixmap, source_path = self._load_cover_art_pixmap(absolute_paths)
        if pixmap is None:
            self.tag_cover_label.setPixmap(QPixmap())
            self.tag_cover_label.setText("No cover art")
            self.tag_cover_label.setToolTip("")
            return

        scaled = pixmap.scaled(
            self.tag_cover_label.width(),
            self.tag_cover_label.height(),
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation,
        )
        self.tag_cover_label.setText("")
        self.tag_cover_label.setPixmap(scaled)
        self.tag_cover_label.setToolTip(str(source_path) if source_path else "")

    def _load_cover_art_pixmap(self, absolute_paths: list[Path]) -> tuple[QPixmap | None, Path | None]:
        if not absolute_paths:
            return None, None

        album_dir = absolute_paths[0].parent
        try:
            for candidate in sorted(album_dir.iterdir(), key=lambda path: path.name.lower()):
                if not candidate.is_file():
                    continue
                if candidate.suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif"}:
                    continue
                pixmap = QPixmap(str(candidate))
                if not pixmap.isNull():
                    log_cover_art_loaded("folder_image", str(candidate), str(album_dir))
                    return pixmap, candidate
        except OSError as exc:
            log_cover_art_probe_failed("album_directory_scan", str(album_dir), exc)

        for path in absolute_paths:
            try:
                art_bytes = read_embedded_cover_art(path)
            except Exception as exc:
                log_cover_art_probe_failed("embedded_cover_read", str(album_dir), exc)
                art_bytes = None
            if not art_bytes:
                continue
            pixmap = QPixmap()
            if pixmap.loadFromData(art_bytes):
                log_cover_art_loaded("embedded_cover_art", str(path), str(album_dir))
                return pixmap, path
        log_cover_art_not_found(str(album_dir), [str(path) for path in absolute_paths])
        return None, None

    def _find_track_scan_metadata(self, track_path: str):
        for album in self.state.library_albums:
            metadata = album.track_metadata.get(track_path)
            if metadata is not None:
                return metadata
        return None

    def edit_selected_track_tags(self) -> None:
        """Open a manual tag editor for one selected track and save via preview/apply."""
        track_path = self.get_selected_single_track_path()
        if track_path is None:
            QMessageBox.information(
                self,
                "Select One Track",
                "Select exactly one track row in the library tree to edit its tags.",
            )
            return

        absolute_path = self.resolve_library_track_path(track_path)
        if absolute_path is None:
            QMessageBox.warning(
                self,
                "Track Not Found",
                "The selected track could not be resolved to a file on disk.",
            )
            return

        try:
            current_track = self.tagging_service.read_track(absolute_path)
        except Exception as exc:
            QMessageBox.critical(self, "Read Tags Failed", f"Could not read current tags: {exc}")
            return

        editor = EditTagsDialog(current_track, parent=self)
        if editor.exec() != QDialog.Accepted:
            return

        try:
            proposed_track = editor.build_track()
        except ValueError as exc:
            QMessageBox.warning(self, "Invalid Tag Value", f"Please correct the edited values: {exc}")
            return

        preview_report = self.tagging_service.preview_tags(proposed_track, source="ui_manual_edit_preview")
        if not preview_report.changes:
            QMessageBox.information(self, "No Changes", "The edited tags match the current file tags.")
            return

        album_context_tracks = self._load_album_context_tracks(proposed_track.file_path, proposed_track=proposed_track)
        rename_plan = self._build_rename_preview(proposed_track, album_context_tracks)
        dialog = TagPreviewDialog(
            current_track,
            proposed_track,
            preview_report,
            [],
            rename_plan=rename_plan,
            parent=self,
        )
        if dialog.exec() != QDialog.Accepted:
            return

        try:
            applied_report = self.tagging_service.apply_tags(
                proposed_track,
                preview_report=preview_report,
                confirmed=True,
                source="ui_manual_edit_apply",
                rename_config=self.settings.rename_config,
                album_tracks=album_context_tracks,
            )
        except Exception as exc:
            QMessageBox.critical(self, "Tag Save Failed", f"Could not apply edited tags: {exc}")
            return

        QMessageBox.information(
            self,
            "Tags Updated",
            "\n".join(
                [
                    f"Updated tags for: {absolute_path.name}",
                    f"Applied changes: {len(applied_report.changes)}",
                    f"Final path: {applied_report.result_file_path or absolute_path}",
                ]
            ),
        )
        self.scan_folder(show_feedback=False)

    def preview_selected_track_tags(self) -> None:
        """Preview and optionally apply tag changes for one selected library track."""
        track_path = self.get_selected_single_track_path()
        if track_path is None:
            QMessageBox.information(
                self,
                "Select One Track",
                "Select exactly one track row in the library tree to preview tagging changes.",
            )
            return

        absolute_path = self.resolve_library_track_path(track_path)
        if absolute_path is None:
            QMessageBox.warning(
                self,
                "Track Not Found",
                "The selected track could not be resolved to a file on disk.",
            )
            return

        log_tag_preview_started(str(absolute_path))
        try:
            track = self.tagging_service.read_track(absolute_path)
            proposed_track, diff_report, candidates = self.tagging_service.propose_tags_for_track(track)
            preview_report = self.tagging_service.preview_tags(proposed_track, source="ui_preview")
            album_context_tracks = self._load_album_context_tracks(proposed_track.file_path, proposed_track=proposed_track)
            rename_plan = self._build_rename_preview(proposed_track, album_context_tracks)
            best_candidate = max(candidates, key=lambda candidate: candidate.confidence, default=None)
            log_tag_preview_ready(
                str(absolute_path),
                diff_report.auto_apply_confidence,
                diff_report.review_required,
                best_candidate.source if best_candidate else "none",
                len(diff_report.changes),
            )
        except Exception as exc:
            log_tag_preview_failed(str(absolute_path), exc)
            QMessageBox.critical(self, "Tag Preview Failed", f"Could not prepare a tag preview: {exc}")
            return

        dialog = TagPreviewDialog(track, proposed_track, diff_report, candidates, rename_plan=rename_plan, parent=self)
        accepted = dialog.exec() == QDialog.Accepted
        if not accepted:
            log_tag_preview_dismissed(str(absolute_path))
            return

        log_tag_apply_started(str(absolute_path), diff_report.auto_apply_confidence)
        try:
            applied_report = self.tagging_service.apply_tags(
                proposed_track,
                preview_report=preview_report,
                confirmed=True,
                source="ui_apply",
                rename_config=self.settings.rename_config,
                album_tracks=album_context_tracks,
            )
        except Exception as exc:
            log_tag_apply_failed(str(absolute_path), exc)
            QMessageBox.critical(self, "Tag Apply Failed", f"Could not apply tags: {exc}")
            return

        log_tag_apply_succeeded(str(absolute_path), len(applied_report.changes))
        QMessageBox.information(
            self,
            "Tags Applied",
            "\n".join(
                [
                    f"Updated tags for: {absolute_path.name}",
                    f"Applied changes: {len(applied_report.changes)}",
                    f"Score: {self._format_confidence(diff_report.auto_apply_confidence)}",
                    f"Final path: {applied_report.result_file_path or absolute_path}",
                ]
            ),
        )
        self.scan_folder(show_feedback=False)

    def preview_selected_album_tags(self) -> None:
        """Preview and optionally apply tag changes for one selected album row."""
        album_track_paths = self.get_selected_album_track_paths()
        if album_track_paths is None:
            QMessageBox.information(
                self,
                "Select One Album",
                "Select exactly one album row in the library tree to preview album tagging changes.",
            )
            return

        album_name = self._get_album_label_for_track_paths(album_track_paths)
        absolute_paths: list[Path] = []
        for track_path in album_track_paths:
            absolute_path = self.resolve_library_track_path(track_path)
            if absolute_path is not None:
                absolute_paths.append(absolute_path)

        if not absolute_paths:
            QMessageBox.warning(
                self,
                "Album Not Found",
                "The selected album tracks could not be resolved to files on disk.",
            )
            return

        proposals: list[dict[str, object]] = []
        try:
            for absolute_path in absolute_paths:
                track = self.tagging_service.read_track(absolute_path)
                proposed_track, diff_report, candidates = self.tagging_service.propose_tags_for_track(track)
                proposals.append(
                    {
                        "track": track,
                        "proposed_track": proposed_track,
                        "diff_report": diff_report,
                        "candidates": candidates,
                    }
                )
        except Exception as exc:
            QMessageBox.critical(self, "Album Tag Preview Failed", f"Could not prepare album tag previews: {exc}")
            return

        proposed_album_tracks = [row["proposed_track"].clone() for row in proposals]
        album_issues = self._validate_proposed_album_tracks([row["proposed_track"] for row in proposals])
        track_rows: list[dict[str, object]] = []
        for proposal in proposals:
            rename_plan = self._build_rename_preview(proposal["proposed_track"], proposed_album_tracks)
            diff_report = proposal["diff_report"]
            track_rows.append(
                {
                    "track_name": Path(proposal["track"].file_path).name,
                    "score": diff_report.auto_apply_confidence,
                    "review_required": diff_report.review_required,
                    "change_count": len(diff_report.changes),
                    "current_title": proposal["track"].metadata.title or "(missing)",
                    "proposed_title": proposal["proposed_track"].metadata.title or "(missing)",
                    "current_path": proposal["track"].file_path,
                    "target_path": rename_plan.target_path if rename_plan else proposal["track"].file_path,
                    "rename_required": rename_plan.rename_required if rename_plan else False,
                    "changes": diff_report.changes,
                }
            )

        dialog = AlbumTagPreviewDialog(album_name, track_rows, album_issues, parent=self)
        accepted = dialog.exec() == QDialog.Accepted
        if not accepted:
            return

        applied_tracks = 0
        try:
            for proposal in proposals:
                preview_report = self.tagging_service.preview_tags(
                    proposal["proposed_track"],
                    source="ui_album_preview",
                )
                self.tagging_service.apply_tags(
                    proposal["proposed_track"],
                    preview_report=preview_report,
                    confirmed=True,
                    source="ui_album_apply",
                    rename_config=self.settings.rename_config,
                    album_tracks=proposed_album_tracks,
                )
                applied_tracks += 1
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Album Tag Apply Failed",
                f"Applied {applied_tracks} of {len(proposals)} tracks before failing: {exc}",
            )
            self.scan_folder(show_feedback=False)
            return

        QMessageBox.information(
            self,
            "Album Tags Applied",
            "\n".join(
                [
                    f"Album: {album_name}",
                    f"Tracks updated: {applied_tracks}",
                    f"Tracks renamed: {sum(1 for row in track_rows if row['rename_required'])}",
                ]
            ),
        )
        self.scan_folder(show_feedback=False)

    def add_selected_to_playlist(self) -> None:
        self.add_tracks_to_playlist(
            self.get_selected_library_tracks(),
            source="library_selection",
        )

    def add_tracks_to_playlist(self, tracks: list[str], source: str) -> None:
        if not tracks:
            return

        self.state.add_tracks_to_playlist(tracks)
        log_tracks_added(tracks, source)
        self.populate_playlist()
        self.playlist_widget.setCurrentRow(self.playlist_widget.count() - 1)

    def populate_playlist(self) -> None:
        self.playlist_widget.clear()

        for track in self.state.playlist_tracks:
            self.playlist_widget.addItem(QListWidgetItem(track))

    def remove_selected_from_playlist(self) -> None:
        row = self.playlist_widget.currentRow()
        if row < 0:
            return

        removed_track = self.state.playlist_tracks[row]
        self.state.remove_playlist_track(row)
        log_playlist_track_removed(removed_track, row)
        self.populate_playlist()

        if self.playlist_widget.count() > 0:
            self.playlist_widget.setCurrentRow(min(row, self.playlist_widget.count() - 1))

    def move_up(self) -> None:
        row = self.playlist_widget.currentRow()
        if row <= 0:
            return

        track = self.state.playlist_tracks[row]
        self.state.move_playlist_track(row, row - 1)
        log_playlist_reordered(track, row, row - 1, "move_up_button")
        self.populate_playlist()
        self.playlist_widget.setCurrentRow(row - 1)

    def move_down(self) -> None:
        row = self.playlist_widget.currentRow()
        if row < 0 or row >= self.playlist_widget.count() - 1:
            return

        track = self.state.playlist_tracks[row]
        self.state.move_playlist_track(row, row + 1)
        log_playlist_reordered(track, row, row + 1, "move_down_button")
        self.populate_playlist()
        self.playlist_widget.setCurrentRow(row + 1)

    def clear_playlist(self) -> None:
        cleared_count = len(self.state.playlist_tracks)
        self.state.clear_playlist()
        log_playlist_cleared(cleared_count)
        self.populate_playlist()

    def save_playlist(self) -> None:
        if not self.state.playlist_tracks:
            QMessageBox.warning(self, "Nothing to save", "Playlist is empty.")
            return

        suggested_name, ok = QInputDialog.getText(
            self,
            "Playlist name",
            "Enter playlist name (no extension):",
        )
        if not ok or not suggested_name.strip():
            log_playlist_save_cancelled("name_prompt")
            return

        playlist_name = suggested_name.strip()
        default_dir = self.state.root_folder or self.state.library_base_folder or Path.home()

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save playlist as",
            str(default_dir / f"{playlist_name}.m3u8"),
            "M3U8 files (*.m3u8)",
        )
        if not file_path:
            log_playlist_save_cancelled("save_dialog")
            return

        save_path = Path(file_path)
        log_playlist_save_started(playlist_name, save_path, self.state.playlist_tracks)

        try:
            write_m3u8_playlist(
                tracks=self.state.playlist_tracks,
                save_path=save_path,
                base_folder=self.state.library_base_folder,
            )
        except Exception as exc:
            log_playlist_save_failed(
                playlist_name,
                save_path,
                self.state.playlist_tracks,
                exc,
            )
            QMessageBox.critical(self, "Save failed", f"Could not save playlist: {exc}")
            return

        log_playlist_saved(playlist_name, save_path, self.state.playlist_tracks)
        QMessageBox.information(self, "Saved", f"Playlist saved to {file_path}")

    def _sync_playlist_from_widget(self, *args) -> None:
        # Drag-and-drop reorders the widget directly, so we copy that order back
        # into the state to keep the UI and business data aligned.
        self.state.playlist_tracks = [
            self.playlist_widget.item(index).text()
            for index in range(self.playlist_widget.count())
        ]
        log_playlist_reordered_from_drag(self.state.playlist_tracks)

    def _build_library_item(self, album: LibraryAlbum) -> QStandardItem:
        """Create one library row that displays a folder and stores its tracks."""
        item = QStandardItem(album.display_name)
        item.setData(album.tracks, ALBUM_TRACKS_ROLE)

        for track in album.tracks:
            track_metadata = album.track_metadata.get(track)
            child_item = QStandardItem(track_metadata.display_name if track_metadata else Path(track).name)
            child_item.setEditable(False)
            child_item.setData([track], ALBUM_TRACKS_ROLE)
            child_item.setData(track, TRACK_PATH_ROLE)
            child_item.setToolTip(track_metadata.tooltip_text if track_metadata else track)
            item.appendRow(child_item)

        return item

    def get_selected_single_track_path(self) -> str | None:
        """Return the relative path for one selected track row, or None if selection is invalid."""
        indexes = self.tag_library_view.selectionModel().selectedIndexes()
        track_paths: list[str] = []

        for proxy_index in indexes:
            source_index = self.tag_library_proxy.mapToSource(proxy_index)
            item = self.tag_library_model.itemFromIndex(source_index)
            if item is None or item.hasChildren():
                continue

            track_path = item.data(TRACK_PATH_ROLE)
            if isinstance(track_path, str):
                track_paths.append(track_path)

        unique_paths = sorted(set(track_paths))
        if len(unique_paths) != 1:
            return None
        return unique_paths[0]

    def get_selected_album_track_paths(self) -> list[str] | None:
        """Return one selected album row's tracks, or None if the selection is invalid."""
        indexes = self.tag_library_view.selectionModel().selectedIndexes()
        if len(indexes) != 1:
            return None

        source_index = self.tag_library_proxy.mapToSource(indexes[0])
        item = self.tag_library_model.itemFromIndex(source_index)
        if item is None or not item.hasChildren():
            return None

        tracks = item.data(ALBUM_TRACKS_ROLE) or []
        return list(tracks) if isinstance(tracks, list) and tracks else None

    def resolve_library_track_path(self, track_path: str) -> Path | None:
        """Resolve a relative library track path into an absolute file path."""
        if self.state.library_base_folder is None:
            return None

        absolute_path = self.state.library_base_folder / track_path
        return absolute_path if absolute_path.exists() else None

    @staticmethod
    def _format_confidence(value: float | None) -> str:
        if value is None:
            return "(missing)"
        return f"{value:.4f}"

    @staticmethod
    def _join_values(values: list[str]) -> str:
        return ", ".join(values) if values else "(missing)"

    @staticmethod
    def _format_value(value) -> str:
        if value in (None, "", []):
            return "(missing)"
        if isinstance(value, list):
            return ", ".join(str(item) for item in value)
        return str(value)

    def _build_rename_preview(self, proposed_track, album_tracks=None):
        rename_config = self.settings.rename_config
        if not rename_config.enabled:
            return None
        return self.tagging_service.preview_rename(proposed_track, rename_config, album_tracks=album_tracks)

    def _load_rename_settings_ui(self) -> None:
        rename_config = self.settings.rename_config
        self.rename_enabled_checkbox.setChecked(rename_config.enabled)
        self.album_level_folder_checkbox.setChecked(rename_config.use_album_level_folder_naming)
        self.replace_existing_checkbox.setChecked(rename_config.replace_existing)
        self.cleanup_dirs_checkbox.setChecked(rename_config.cleanup_empty_source_dirs)
        self.folder_template_input.setText(rename_config.folder_template)
        self.file_template_input.setText(rename_config.file_template)
        self.rename_settings_status.setText("Rename settings loaded.")
        self._refresh_rename_settings_preview()

    def _current_rename_config_from_ui(self):
        return RenameConfig(
            enabled=self.rename_enabled_checkbox.isChecked(),
            folder_template=self.folder_template_input.text().strip() or RenameConfig.folder_template,
            file_template=self.file_template_input.text().strip() or RenameConfig.file_template,
            use_album_level_folder_naming=self.album_level_folder_checkbox.isChecked(),
            replace_existing=self.replace_existing_checkbox.isChecked(),
            cleanup_empty_source_dirs=self.cleanup_dirs_checkbox.isChecked(),
        )

    def save_rename_settings(self) -> None:
        self.settings.rename_config = self._current_rename_config_from_ui()
        if not self._save_settings("save_rename_settings"):
            return
        self.rename_settings_status.setText("Rename settings saved.")
        self._refresh_rename_settings_preview()

    def reset_rename_settings_defaults(self) -> None:
        defaults = type(self.settings.rename_config)()
        self.rename_enabled_checkbox.setChecked(defaults.enabled)
        self.album_level_folder_checkbox.setChecked(defaults.use_album_level_folder_naming)
        self.replace_existing_checkbox.setChecked(defaults.replace_existing)
        self.cleanup_dirs_checkbox.setChecked(defaults.cleanup_empty_source_dirs)
        self.folder_template_input.setText(defaults.folder_template)
        self.file_template_input.setText(defaults.file_template)
        self.rename_settings_status.setText("Reset rename settings to defaults. Save to persist.")
        self._refresh_rename_settings_preview()

    def _refresh_rename_settings_preview(self) -> None:
        rename_config = self._current_rename_config_from_ui()
        sample_path = Path("/Music/Artist - Album/01 Example Song.flac")
        sample_track = self._build_sample_track(sample_path)
        sibling_track = self._build_sample_track(
            Path("/Music/Artist - Album/02 Follow Up.flac"),
            title="Follow Up",
            track_number=2,
        )
        try:
            rename_plan = self.tagging_service.preview_rename(
                sample_track,
                rename_config,
                album_tracks=[sample_track.clone(), sibling_track],
            )
            self.rename_preview_label.setPlainText(
                "\n".join(
                    [
                        f"Enabled: {rename_config.enabled}",
                        f"Album aggregate folder naming: {rename_config.use_album_level_folder_naming}",
                        f"Sample source: {rename_plan.source_path}",
                        f"Sample target: {rename_plan.target_path}",
                        f"Warnings: {', '.join(rename_plan.warnings) if rename_plan.warnings else '(none)'}",
                    ]
                )
            )
        except Exception as exc:
            self.rename_preview_label.setPlainText(f"Preview unavailable: {exc}")

    def _build_sample_track(self, file_path: Path, *, title: str = "Example Song", track_number: int = 1):
        from services.tagging.schema import CanonicalTrack

        track = CanonicalTrack(file_path=str(file_path), file_format="FLAC")
        track.metadata.title = title
        track.metadata.artist = ["DreamWeaver"]
        track.metadata.album = "cloud9"
        track.metadata.album_artist = ["DreamWeaver"]
        track.metadata.track_number = track_number
        track.metadata.release_date = "2020-02-09"
        return track

    def _load_album_context_tracks(self, proposed_track_path: str, *, proposed_track=None):
        album_track_paths = self._get_album_track_paths_for_track(proposed_track_path)
        tracks = []
        for track_path in album_track_paths:
            absolute_path = self.resolve_library_track_path(track_path)
            if absolute_path is None:
                continue
            if proposed_track is not None and str(absolute_path) == proposed_track.file_path:
                tracks.append(proposed_track.clone())
                continue
            try:
                tracks.append(self.tagging_service.read_track(absolute_path))
            except Exception:
                continue
        return tracks

    def _get_album_track_paths_for_track(self, track_path: str) -> list[str]:
        if self.state.library_base_folder is None:
            return [track_path]

        for album in self.state.library_albums:
            if track_path in album.tracks:
                return list(album.tracks)
        return [track_path]

    def _get_album_label_for_track_paths(self, track_paths: list[str]) -> str:
        track_path_set = set(track_paths)
        for album in self.state.library_albums:
            if track_path_set == set(album.tracks):
                return album.display_name
        if track_paths:
            return Path(track_paths[0]).parent.name or "Selected Album"
        return "Selected Album"

    @staticmethod
    def _validate_proposed_album_tracks(proposed_tracks) -> list[dict[str, object]]:
        """Check the proposed album metadata for mismatches before apply."""
        album_fields = ["album", "album_artist", "release_date", "disc_total"]
        issues: list[dict[str, object]] = []
        for field_name in album_fields:
            values = {
                str(getattr(track.metadata, field_name))
                for track in proposed_tracks
                if getattr(track.metadata, field_name)
            }
            if len(values) > 1:
                issues.append(
                    {
                        "field": field_name,
                        "values": sorted(values),
                        "severity": "warning",
                    }
                )
        return issues
