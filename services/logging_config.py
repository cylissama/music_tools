"""Purpose: Configure persistent application logging for all app sessions."""

from __future__ import annotations

import json
import logging
import os
import sys
import uuid
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path

APP_NAME = "WalkmanPlaylistCreator"
LOGGER_NAME = "walkman"
LOG_FILENAME = "activity.log"
MAX_LOG_BYTES = 1_000_000
BACKUP_COUNT = 10
SESSION_ID = uuid.uuid4().hex


class JsonLineFormatter(logging.Formatter):
    """Write one JSON object per log line for easy debugging and parsing."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": datetime.fromtimestamp(
                record.created,
                tz=timezone.utc,
            ).astimezone().isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "session_id": getattr(record, "session_id", SESSION_ID),
            "event": getattr(record, "event", record.getMessage()),
        }

        message = record.getMessage()
        if message and message != payload["event"]:
            payload["message"] = message

        details = getattr(record, "details", None)
        if details:
            payload["details"] = details

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, ensure_ascii=True)


def configure_logging() -> Path:
    """Configure a persistent rotating log file and return its path."""
    log_file_path = get_log_file_path()
    logger = logging.getLogger(LOGGER_NAME)

    if logger.handlers:
        return log_file_path

    log_file_path.parent.mkdir(parents=True, exist_ok=True)

    handler = RotatingFileHandler(
        log_file_path,
        maxBytes=MAX_LOG_BYTES,
        backupCount=BACKUP_COUNT,
        encoding="utf-8",
    )
    handler.setFormatter(JsonLineFormatter())

    logger.setLevel(logging.INFO)
    logger.addHandler(handler)
    logger.propagate = False

    return log_file_path


def get_log_file_path() -> Path:
    """Return the persistent log file location for the current platform."""
    return get_log_directory() / LOG_FILENAME


def get_session_id() -> str:
    """Return the unique id for the current application run."""
    return SESSION_ID


def install_exception_hook() -> None:
    """Log uncaught exceptions so app crashes are preserved in the log file."""
    previous_hook = sys.excepthook

    def handle_exception(exc_type, exc_value, exc_traceback) -> None:
        logger = logging.getLogger(LOGGER_NAME)
        logger.error(
            "unhandled_exception",
            exc_info=(exc_type, exc_value, exc_traceback),
            extra={
                "event": "unhandled_exception",
                "details": {},
                "session_id": SESSION_ID,
            },
        )
        previous_hook(exc_type, exc_value, exc_traceback)

    sys.excepthook = handle_exception


def get_log_directory() -> Path:
    """Return an OS-appropriate directory for persistent application logs."""
    home = Path.home()

    if sys.platform == "darwin":
        return home / "Library" / "Logs" / APP_NAME

    if sys.platform.startswith("win"):
        local_app_data = os.environ.get("LOCALAPPDATA")
        base_dir = Path(local_app_data) if local_app_data else home / "AppData" / "Local"
        return base_dir / APP_NAME / "Logs"

    state_home = os.environ.get("XDG_STATE_HOME")
    base_dir = Path(state_home) if state_home else home / ".local" / "state"
    return base_dir / APP_NAME / "logs"
