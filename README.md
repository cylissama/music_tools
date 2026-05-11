# music_tools

## Rename Config

The app settings file now supports a persistent `rename_config` block for post-tagging file moves.

On macOS the default settings path is `~/Library/Application Support/WalkmanPlaylistCreator/app_settings.json`.

Example:

```json
{
  "music_directories": ["/Users/you/Music/Digital"],
  "selected_music_directory": "/Users/you/Music/Digital",
  "rename_config": {
    "enabled": true,
    "folder_template": "{album_artist} - {album} ({release_year}) [{file_type}]",
    "file_template": "{track_number_padded} {title}",
    "use_album_level_folder_naming": true,
    "replace_existing": false,
    "cleanup_empty_source_dirs": true
  }
}
```

The application also exposes these settings in the main window under the `Settings` tab.

Available template fields:

- `album_artist`
- `artist`
- `album`
- `title`
- `release_year`
- `track_number`
- `track_number_padded`
- `disc_number`
- `disc_number_padded`
- `file_type`
- `file_extension`
