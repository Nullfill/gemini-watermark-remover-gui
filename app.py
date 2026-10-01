#!/usr/bin/env python3
"""
Watermark Remover - Desktop Application Entry Point.
"""
import os
from pathlib import Path
import sys

# Ensure project root is in sys.path
_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from core.config import AppConfig
from core.logger import setup_logger
from ui.main_window import MainWindow
from ui.theme import DARK_THEME_QSS


def main():
    # Setup central logger
    logger = setup_logger()
    logger.info("Starting Watermark Remover Desktop Application...")

    # Cleanup leftover temp directories from prior crashed runs
    AppConfig.cleanup_old_temp()

    # Enable High DPI
    if hasattr(Qt, "AA_EnableHighDpiScaling"):
        QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    if hasattr(Qt, "AA_UseHighDpiPixmaps"):
        QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)
    app.setApplicationName("WatermarkRemover")
    app.setOrganizationName("DevSaraiva")
    app.setStyleSheet(DARK_THEME_QSS)

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
