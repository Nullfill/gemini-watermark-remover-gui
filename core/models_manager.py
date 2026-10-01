"""
ProPainter AI Model Weights Manager.
Verifies file existence, checks integrity, and handles user-consented downloads with progress and cancel support.
"""
from dataclasses import dataclass
import os
from pathlib import Path
import time
from typing import Callable, Dict, List, Optional
import urllib.request

from PySide6.QtCore import QObject, QThread, Signal

from core.config import MODELS_DIR
from core.logger import get_logger

logger = get_logger()

BASE_RELEASE_URL = "https://github.com/sczhou/ProPainter/releases/download/v0.1.0"

REQUIRED_MODELS: Dict[str, Dict[str, any]] = {
    "raft-things.pth": {
        "url": f"{BASE_RELEASE_URL}/raft-things.pth",
        "expected_size": 21108000,
        "description": "Optical Flow Estimation Network"
    },
    "recurrent_flow_completion.pth": {
        "url": f"{BASE_RELEASE_URL}/recurrent_flow_completion.pth",
        "expected_size": 20348681,
        "description": "Recurrent Flow Completion Network"
    },
    "ProPainter.pth": {
        "url": f"{BASE_RELEASE_URL}/ProPainter.pth",
        "expected_size": 157780510,
        "description": "ProPainter Spatio-Temporal Transformer"
    }
}


def are_models_installed() -> bool:
    """Check if all 3 required ProPainter weights exist and have valid size."""
    for filename, meta in REQUIRED_MODELS.items():
        file_path = MODELS_DIR / filename
        if not file_path.is_file():
            return False
        if file_path.stat().st_size < 1_000_000:  # Must be at least 1MB
            return False
    return True


def get_missing_models() -> List[str]:
    missing = []
    for filename in REQUIRED_MODELS:
        file_path = MODELS_DIR / filename
        if not file_path.is_file() or file_path.stat().st_size < 1_000_000:
            missing.append(filename)
    return missing


def download_single_model(
    filename: str,
    target_dir: Path,
    progress_callback: Optional[Callable[[int, int, float, float], None]] = None,
    cancel_check: Optional[Callable[[], bool]] = None
) -> Path:
    meta = REQUIRED_MODELS.get(filename)
    if not meta:
        raise ValueError(f"Unknown model name: {filename}")

    target_dir.mkdir(parents=True, exist_ok=True)
    dest_path = target_dir / filename
    temp_path = target_dir / f"{filename}.downloading"

    url = meta["url"]
    expected_size = meta["expected_size"]

    logger.info("Downloading model %s from %s...", filename, url)

    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) WatermarkRemover/2.0"}
    )

    with urllib.request.urlopen(req) as resp:
        content_length = resp.headers.get("Content-Length")
        total_size = int(content_length) if content_length and content_length.isdigit() else expected_size

        downloaded = 0
        chunk_size = 64 * 1024
        start_time = time.time()
        last_update = start_time

        with open(temp_path, "wb") as f:
            while True:
                if cancel_check and cancel_check():
                    f.close()
                    temp_path.unlink(missing_ok=True)
                    raise InterruptedError(f"Download of {filename} was cancelled.")

                chunk = resp.read(chunk_size)
                if not chunk:
                    break

                f.write(chunk)
                downloaded += len(chunk)

                now = time.time()
                if now - last_update >= 0.15 or downloaded == total_size:
                    last_update = now
                    elapsed = max(0.001, now - start_time)
                    speed_mb = (downloaded / (1024 * 1024)) / elapsed
                    pct = min(100.0, (downloaded / max(1, total_size)) * 100.0)
                    if progress_callback:
                        progress_callback(downloaded, total_size, speed_mb, pct)

    if temp_path.exists():
        temp_path.replace(dest_path)

    logger.info("Model %s downloaded successfully (%d bytes)", filename, dest_path.stat().st_size)
    return dest_path


class ModelDownloadWorker(QThread):
    progress = Signal(str, float, str)  # model_name, percent, speed_text
    finished = Signal()
    error = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._is_cancelled = False

    def cancel(self):
        self._is_cancelled = True

    def run(self):
        try:
            missing = get_missing_models()
            if not missing:
                self.finished.emit()
                return

            total_missing = len(missing)
            for idx, filename in enumerate(missing):
                if self._is_cancelled:
                    return

                def on_progress(dl, total, speed_mb, pct):
                    overall_pct = (idx * 100.0 + pct) / total_missing
                    speed_txt = f"{speed_mb:.1f} MB/s"
                    self.progress.emit(filename, overall_pct, speed_txt)

                download_single_model(
                    filename,
                    MODELS_DIR,
                    progress_callback=on_progress,
                    cancel_check=lambda: self._is_cancelled
                )

            if not self._is_cancelled:
                self.finished.emit()

        except InterruptedError:
            logger.info("Model download cancelled by user.")
        except Exception as e:
            logger.error("Model download error: %s", e)
            self.error.emit(str(e))
