"""Purpose: Start the Qt application and show the main window."""

import sys

from PySide6.QtWidgets import QApplication

from services.activity_logger import log_app_exited, log_app_started
from services.logging_config import configure_logging, install_exception_hook
from ui.main_window import MainWindow


def main() -> int:
    """Create the application, show the window, and start the event loop."""
    log_file_path = configure_logging()
    install_exception_hook()
    log_app_started(log_file_path)

    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    exit_code = app.exec()
    log_app_exited(exit_code)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
