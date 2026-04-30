"""Purpose: Build the Qt interface and connect user actions to app logic."""

from pathlib import Path

from PySide6.QtCore import Qt, QSortFilterProxyModel
from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

from models import LibraryAlbum, PlaylistState
from services.activity_logger import (
    log_album_toggled,
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
    log_tracks_added,
)
from services.library_scanner import scan_music_files
from services.playlist_writer import write_m3u8_playlist

ALBUM_TRACKS_ROLE = Qt.UserRole + 1


class MainWindow(QWidget):
    """Main application window for browsing music and creating playlists."""

    def __init__(self) -> None:
        super().__init__()
        self.state = PlaylistState()

        self.setWindowTitle("Walkman Playlist Creator")
        self.resize(1000, 600)

        self._build_widgets()
        self._build_layout()
        self._connect_signals()
        self._update_root_label()

    def _build_widgets(self) -> None:
        self.root_label = QLabel()
        self.choose_root_btn = QPushButton("Choose Root Music Folder")
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

    def _build_layout(self) -> None:
        top_row = QHBoxLayout()
        top_row.addWidget(self.root_label)
        top_row.addWidget(self.choose_root_btn)
        top_row.addWidget(self.scan_btn)

        left_col = QVBoxLayout()
        left_col.addWidget(QLabel("Library"))
        left_col.addWidget(self.search_input)
        left_col.addWidget(self.library_view)

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
        self.scan_btn.clicked.connect(self.scan_folder)
        self.search_input.textChanged.connect(self.filter_library)
        self.library_view.doubleClicked.connect(self.handle_library_double_click)
        self.add_btn.clicked.connect(self.add_selected_to_playlist)
        self.remove_btn.clicked.connect(self.remove_selected_from_playlist)
        self.up_btn.clicked.connect(self.move_up)
        self.down_btn.clicked.connect(self.move_down)
        self.clear_btn.clicked.connect(self.clear_playlist)
        self.save_btn.clicked.connect(self.save_playlist)
        self.playlist_widget.model().rowsMoved.connect(self._sync_playlist_from_widget)

    def _update_root_label(self) -> None:
        if self.state.root_folder is None:
            self.root_label.setText("Root Music Folder: (none)")
            return

        self.root_label.setText(f"Root Music Folder: {self.state.root_folder}")

    def choose_root(self) -> None:
        selected = QFileDialog.getExistingDirectory(
            self,
            "Select Root Music Folder",
            str(Path.home()),
        )
        if not selected:
            log_root_selection_cancelled()
            return

        self.state.set_root_folder(Path(selected))
        self._update_root_label()
        log_root_selected(self.state.root_folder)
        self.scan_folder()

    def scan_folder(self) -> None:
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

        log_scan_started(start, self.state.root_folder)
        albums = scan_music_files(start=start, root_folder=self.state.root_folder)
        base_folder = self.state.root_folder or start

        self.state.set_library(albums, base_folder)
        self.populate_library()

        total_tracks = sum(album.track_count for album in albums)
        log_scan_completed(start, len(albums), total_tracks)

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
            item.appendRow(child_item)

        return item
