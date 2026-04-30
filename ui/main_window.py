"""Purpose: Build the Qt interface and connect user actions to app logic."""

import os
from pathlib import Path

from PySide6.QtCore import Qt, QSignalBlocker, QSortFilterProxyModel
from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QAbstractItemView,
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
    QPlainTextEdit,
    QPushButton,
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
    log_tracks_added,
)
from services.app_settings import AppSettings, AppSettingsStore
from services.library_scanner import scan_music_files
from services.playlist_writer import write_m3u8_playlist
from services.tagging import TaggingService

ALBUM_TRACKS_ROLE = Qt.UserRole + 1
TRACK_PATH_ROLE = Qt.UserRole + 2


class TagPreviewDialog(QDialog):
    """Show a detailed preview of current tags, proposed tags, and candidate matches."""

    def __init__(self, track, proposed_track, diff_report, candidates, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Tagging Preview")
        self.resize(900, 650)

        layout = QVBoxLayout(self)

        summary = QPlainTextEdit()
        summary.setReadOnly(True)
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


class MainWindow(QWidget):
    """Main application window for browsing music and creating playlists."""

    def __init__(self) -> None:
        super().__init__()
        self.state = PlaylistState()
        self.settings_store = AppSettingsStore()
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

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Filter library (type to search)")

        self.library_model = QStandardItemModel(self)
        self.library_proxy = QSortFilterProxyModel(self)
        self.library_proxy.setSourceModel(self.library_model)
        self.library_proxy.setFilterCaseSensitivity(Qt.CaseInsensitive)
        self.library_proxy.setFilterKeyColumn(0)
        self.library_proxy.setRecursiveFilteringEnabled(True)

        self.library_view = QTreeView()
        self.library_view.setModel(self.library_proxy)
        self.library_view.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.library_view.setHeaderHidden(True)
        self.library_view.setUniformRowHeights(True)
        self.library_view.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)

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
        self.preview_tag_btn = QPushButton("Preview Tags")
        self.preview_tag_btn.setToolTip("Preview proposed tags for one selected track before applying them.")

    def _build_layout(self) -> None:
        top_row = QHBoxLayout()
        top_row.addWidget(self.root_label)
        top_row.addWidget(self.music_location_combo, stretch=1)
        top_row.addWidget(self.choose_root_btn)
        top_row.addWidget(self.remove_location_btn)
        top_row.addWidget(self.scan_btn)

        left_col = QVBoxLayout()
        left_col.addWidget(QLabel("Library"))
        left_col.addWidget(self.search_input)
        left_col.addWidget(self.library_view)
        left_col.addWidget(self.preview_tag_btn)

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
        left_widget.setLayout(left_col)

        center_widget = QWidget()
        center_widget.setLayout(center_col)

        right_widget = QWidget()
        right_widget.setLayout(right_col)

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(left_widget)
        splitter.addWidget(center_widget)
        splitter.addWidget(right_widget)
        splitter.setSizes([400, 100, 400])

        layout = QVBoxLayout(self)
        layout.addLayout(top_row)
        layout.addWidget(splitter)

    def _connect_signals(self) -> None:
        self.choose_root_btn.clicked.connect(self.choose_root)
        self.remove_location_btn.clicked.connect(self.remove_selected_music_location)
        self.music_location_combo.currentIndexChanged.connect(self.change_music_location)
        self.scan_btn.clicked.connect(self.scan_folder)
        self.search_input.textChanged.connect(self.filter_library)
        self.library_view.doubleClicked.connect(self.handle_library_double_click)
        self.add_btn.clicked.connect(self.add_selected_to_playlist)
        self.remove_btn.clicked.connect(self.remove_selected_from_playlist)
        self.up_btn.clicked.connect(self.move_up)
        self.down_btn.clicked.connect(self.move_down)
        self.clear_btn.clicked.connect(self.clear_playlist)
        self.save_btn.clicked.connect(self.save_playlist)
        self.preview_tag_btn.clicked.connect(self.preview_selected_track_tags)
        self.playlist_widget.model().rowsMoved.connect(self._sync_playlist_from_widget)

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
        settings = self.settings_store.load()
        folders = self._existing_music_directories(settings.music_directories)
        self.state.set_music_directories(folders)

        selected_folder = None
        if settings.selected_music_directory:
            selected_candidate = Path(settings.selected_music_directory)
            if selected_candidate in folders:
                selected_folder = selected_candidate
        if selected_folder is None and folders:
            selected_folder = folders[0]

        self.state.set_root_folder(selected_folder)
        self._refresh_music_location_combo()
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
        settings = AppSettings(
            music_directories=[str(folder) for folder in self.state.music_directories],
            selected_music_directory=str(self.state.root_folder) if self.state.root_folder else None,
        )
        try:
            self.settings_store.save(settings)
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
                f"Found {len(albums)} album folders and {total_tracks} audio files.",
            )

    def populate_library(self) -> None:
        self.library_model.clear()

        for album in self.state.library_albums:
            item = self._build_library_item(album)
            item.setEditable(False)
            self.library_model.appendRow(item)

        self.filter_library(self.search_input.text())
        self.library_view.collapseAll()

    def filter_library(self, text: str) -> None:
        self.library_proxy.setFilterFixedString(text.strip())
        if text.strip():
            self.library_view.expandAll()
        else:
            self.library_view.collapseAll()

    def get_selected_library_tracks(self) -> list[str]:
        indexes = self.library_view.selectionModel().selectedIndexes()
        tracks: list[str] = []

        for proxy_index in indexes:
            source_index = self.library_proxy.mapToSource(proxy_index)
            item = self.library_model.itemFromIndex(source_index)
            if item is not None:
                tracks.extend(item.data(ALBUM_TRACKS_ROLE) or [])

        return tracks

    def handle_library_double_click(self, proxy_index) -> None:
        source_index = self.library_proxy.mapToSource(proxy_index)
        item = self.library_model.itemFromIndex(source_index)

        if item is None:
            return

        if item.hasChildren():
            expanded = not self.library_view.isExpanded(proxy_index)
            self.library_view.setExpanded(proxy_index, expanded)
            log_album_toggled(item.text(), expanded)
            return

        self.add_tracks_to_playlist(
            item.data(ALBUM_TRACKS_ROLE) or [],
            source="library_double_click",
        )

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
            proposed_track, diff_report, candidates = self.tagging_service.propose_tags(absolute_path)
            preview_report = self.tagging_service.preview_tags(proposed_track, source="ui_preview")
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

        dialog = TagPreviewDialog(track, proposed_track, diff_report, candidates, parent=self)
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
                ]
            ),
        )

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
            child_item = QStandardItem(Path(track).name)
            child_item.setEditable(False)
            child_item.setData([track], ALBUM_TRACKS_ROLE)
            child_item.setData(track, TRACK_PATH_ROLE)
            child_item.setToolTip(track)
            item.appendRow(child_item)

        return item

    def get_selected_single_track_path(self) -> str | None:
        """Return the relative path for one selected track row, or None if selection is invalid."""
        indexes = self.library_view.selectionModel().selectedIndexes()
        track_paths: list[str] = []

        for proxy_index in indexes:
            source_index = self.library_proxy.mapToSource(proxy_index)
            item = self.library_model.itemFromIndex(source_index)
            if item is None or item.hasChildren():
                continue

            track_path = item.data(TRACK_PATH_ROLE)
            if isinstance(track_path, str):
                track_paths.append(track_path)

        unique_paths = sorted(set(track_paths))
        if len(unique_paths) != 1:
            return None
        return unique_paths[0]

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
