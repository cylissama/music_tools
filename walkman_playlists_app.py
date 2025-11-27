"""
Walkman Playlist Creator (macOS) - PySide6

Features:
- Scan a music folder (local or mounted Walkman) recursively for audio files
- Display library list with search/filter
- Drag/click to add tracks to a playlist list
- Reorder/remove tracks in playlist
- Save playlist as UTF-8 .m3u8 using relative paths (relative to selected root)

Dependencies:
    pip install PySide6

Notes:
- Choose the Walkman MUSIC folder as the "Root Music Folder" when you want relative paths to be correct.
- The playlist will be written inside the chosen root folder by default, but you can choose elsewhere.

"""

import sys
import os
from pathlib import Path
from functools import partial

from PySide6.QtCore import Qt, QSortFilterProxyModel, QSize
from PySide6.QtGui import QStandardItemModel, QStandardItem
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QListView, QFileDialog, QLabel, QLineEdit, QMessageBox, QListWidget,
    QListWidgetItem, QAbstractItemView, QSplitter, QInputDialog
)

AUDIO_EXTS = ('.mp3', '.flac', '.wav', '.m4a', '.aac', '.ogg')

class WalkmanPlaylistApp(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('Walkman Playlist Creator')
        self.resize(1000, 600)

        self.root_folder = None  # root for relative paths
        self.library = []  # list of relative paths (relative to root_folder or absolute if root unset)

        # Widgets
        self.root_label = QLabel('Root Music Folder: (none)')
        self.choose_root_btn = QPushButton('Choose Root Music Folder')
        self.choose_root_btn.clicked.connect(self.choose_root)

        self.scan_btn = QPushButton('Scan Folder')
        self.scan_btn.clicked.connect(self.scan_folder)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText('Filter library (type to search)')
        self.search_input.textChanged.connect(self.filter_library)

        # Library view
        self.library_model = QStandardItemModel()
        self.library_view = QListView()
        self.library_view.setModel(self.library_model)
        self.library_view.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.library_view.doubleClicked.connect(self.add_selected_to_playlist)

        # Playlist view (drag/drop supported)
        self.playlist_widget = QListWidget()
        self.playlist_widget.setSelectionMode(QAbstractItemView.SingleSelection)
        self.playlist_widget.setDragDropMode(QAbstractItemView.InternalMove)
        self.playlist_widget.setDefaultDropAction(Qt.MoveAction)

        # Buttons for playlist
        self.add_btn = QPushButton('Add →')
        self.add_btn.clicked.connect(self.add_selected_to_playlist)
        self.remove_btn = QPushButton('Remove')
        self.remove_btn.clicked.connect(self.remove_selected_from_playlist)
        self.up_btn = QPushButton('Move Up')
        self.up_btn.clicked.connect(self.move_up)
        self.down_btn = QPushButton('Move Down')
        self.down_btn.clicked.connect(self.move_down)
        self.clear_btn = QPushButton('Clear Playlist')
        self.clear_btn.clicked.connect(self.clear_playlist)

        self.save_btn = QPushButton('Save Playlist (.m3u8)')
        self.save_btn.clicked.connect(self.save_playlist)

        # Layouts
        top_row = QHBoxLayout()
        top_row.addWidget(self.root_label)
        top_row.addWidget(self.choose_root_btn)
        top_row.addWidget(self.scan_btn)

        left_col = QVBoxLayout()
        left_col.addWidget(QLabel('Library'))
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
        right_col.addWidget(QLabel('Playlist (drag to reorder)'))
        right_col.addWidget(self.playlist_widget)
        right_col.addWidget(self.save_btn)

        main_h = QHBoxLayout()
        left_widget = QWidget(); left_widget.setLayout(left_col)
        center_widget = QWidget(); center_widget.setLayout(center_col)
        right_widget = QWidget(); right_widget.setLayout(right_col)

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(left_widget)
        splitter.addWidget(center_widget)
        splitter.addWidget(right_widget)
        splitter.setSizes([400, 100, 400])

        layout = QVBoxLayout(self)
        layout.addLayout(top_row)
        layout.addWidget(splitter)

    def choose_root(self):
        d = QFileDialog.getExistingDirectory(self, 'Select Root Music Folder', os.path.expanduser('~'))
        if d:
            self.root_folder = Path(d)
            self.root_label.setText(f'Root Music Folder: {str(self.root_folder)}')

    def scan_folder(self):
        start = self.root_folder
        if not start:
            start = QFileDialog.getExistingDirectory(self, 'Select Folder to Scan', os.path.expanduser('~'))
            if not start:
                return
            start = Path(start)
        else:
            start = Path(start)

        track_list = []
        for root, _, files in os.walk(start):
            for f in files:
                if f.lower().endswith(AUDIO_EXTS):
                    full = Path(root) / f
                    # compute relative path if root_folder is set and the scanned folder is within it
                    if self.root_folder and full.is_relative_to(self.root_folder):
                        rel = full.relative_to(self.root_folder)
                        track_list.append(str(rel))
                    else:
                        # store absolute relative to scanned folder root
                        rel = full.relative_to(start)
                        track_list.append(str(rel))

        track_list = sorted(track_list, key=lambda s: s.lower())
        self.library = track_list
        self.populate_library()
        QMessageBox.information(self, 'Scan Complete', f'Found {len(track_list)} audio files.')

    def populate_library(self):
        self.library_model.clear()
        for t in self.library:
            item = QStandardItem(t)
            item.setEditable(False)
            self.library_model.appendRow(item)

    def filter_library(self, txt):
        txt = txt.strip().lower()
        self.library_model.clear()
        for t in self.library:
            if txt == '' or txt.lower().find(txt) != -1:
                item = QStandardItem(t)
                item.setEditable(False)
                self.library_model.appendRow(item)

    def get_selected_library_items(self):
        sel = self.library_view.selectionModel().selectedIndexes()
        return [self.library_model.itemFromIndex(i).text() for i in sel]

    def add_selected_to_playlist(self):
        items = self.get_selected_library_items()
        if not items:
            # if double-click added, the method receives a QModelIndex; handle gracefully
            sel = self.library_view.selectedIndexes()
            if sel:
                items = [self.library_model.itemFromIndex(sel[0]).text()]
        for it in items:
            w = QListWidgetItem(it)
            self.playlist_widget.addItem(w)

    def remove_selected_from_playlist(self):
        row = self.playlist_widget.currentRow()
        if row >= 0:
            self.playlist_widget.takeItem(row)

    def move_up(self):
        row = self.playlist_widget.currentRow()
        if row > 0:
            item = self.playlist_widget.takeItem(row)
            self.playlist_widget.insertItem(row-1, item)
            self.playlist_widget.setCurrentRow(row-1)

    def move_down(self):
        row = self.playlist_widget.currentRow()
        if row >= 0 and row < self.playlist_widget.count()-1:
            item = self.playlist_widget.takeItem(row)
            self.playlist_widget.insertItem(row+1, item)
            self.playlist_widget.setCurrentRow(row+1)

    def clear_playlist(self):
        self.playlist_widget.clear()

    def save_playlist(self):
        if self.playlist_widget.count() == 0:
            QMessageBox.warning(self, 'Nothing to save', 'Playlist is empty.')
            return

        suggested_name, ok = QInputDialog.getText(self, 'Playlist name', 'Enter playlist name (no extension):')
        if not ok or not suggested_name.strip():
            return
        name = suggested_name.strip()

        default_dir = str(self.root_folder) if self.root_folder else os.path.expanduser('~')
        path, _ = QFileDialog.getSaveFileName(self, 'Save playlist as', os.path.join(default_dir, f'{name}.m3u8'), 'M3U8 files (*.m3u8)')
        if not path:
            return

        # Build list of track paths as strings
        tracks = [self.playlist_widget.item(i).text() for i in range(self.playlist_widget.count())]

        # If root_folder is set and playlist will be saved inside it, ensure relative paths are relative to root_folder.
        save_path = Path(path)
        try:
            with open(save_path, 'w', encoding='utf-8') as f:
                f.write('#EXTM3U\n')
                for t in tracks:
                    f.write('#EXTINF:,\n')
                    # If the saved playlist is inside root_folder, write paths relative to root_folder
                    if self.root_folder and save_path.parent.resolve() == self.root_folder.resolve():
                        f.write(f"{t}\n")
                    else:
                        # If playlist saved elsewhere, compute path relative to playlist location if possible
                        # If track is stored relative to root_folder, attempt to compute path to track via filesystem
                        if self.root_folder:
                            track_abs = self.root_folder / t
                            try:
                                rel_to_save = os.path.relpath(track_abs, save_path.parent)
                                f.write(f"{rel_to_save}\n")
                            except Exception:
                                f.write(f"{t}\n")
                        else:
                            f.write(f"{t}\n")
        except Exception as e:
            QMessageBox.critical(self, 'Save failed', f'Could not save playlist: {e}')
            return

        QMessageBox.information(self, 'Saved', f'Playlist saved to {str(save_path)}')


if __name__ == '__main__':
    app = QApplication(sys.argv)
    w = WalkmanPlaylistApp()
    w.show()
    sys.exit(app.exec())
