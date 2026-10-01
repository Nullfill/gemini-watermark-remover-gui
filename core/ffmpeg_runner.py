"""
FFmpeg and FFprobe Process Runner & Locator.
Provides robust process supervision, cancellation, and real-time progress parsing.
"""
from io import BytesIO
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import threading
import time
from typing import Callable, Dict, List, Optional, Tuple
import urllib.request
import zipfile

from core.config import APP_DIR, FFMPEG_DIR
from core.logger import get_logger

logger = get_logger()

_FFMPEG_BIN: Optional[Path] = None
_FFPROBE_BIN: Optional[Path] = None


def get_ffmpeg_path() -> Optional[Path]:
    global _FFMPEG_BIN
    if _FFMPEG_BIN and _FFMPEG_BIN.is_file():
        return _FFMPEG_BIN

    # 1. Check bundled ffmpeg directory
    bundled = FFMPEG_DIR / ("ffmpeg.exe" if sys.platform == "win32" else "ffmpeg")
    if bundled.is_file():
        _FFMPEG_BIN = bundled
        return _FFMPEG_BIN

    # 2. Check application root
    app_root_bin = APP_DIR / ("ffmpeg.exe" if sys.platform == "win32" else "ffmpeg")
    if app_root_bin.is_file():
        _FFMPEG_BIN = app_root_bin
        return _FFMPEG_BIN

    # 3. Check system PATH
    which_bin = shutil.which("ffmpeg")
    if which_bin:
        _FFMPEG_BIN = Path(which_bin)
        return _FFMPEG_BIN

    # 4. Check Windows WinGet directory
    local_appdata = os.environ.get("LOCALAPPDATA")
    if local_appdata:
        winget_dir = Path(local_appdata) / "Microsoft" / "WinGet" / "Packages"
        if winget_dir.exists():
            for p in winget_dir.glob("**/ffmpeg.exe"):
                if p.is_file():
                    _FFMPEG_BIN = p
                    return _FFMPEG_BIN

    return None


def get_ffprobe_path() -> Optional[Path]:
    global _FFPROBE_BIN
    if _FFPROBE_BIN and _FFPROBE_BIN.is_file():
        return _FFPROBE_BIN

    bundled = FFMPEG_DIR / ("ffprobe.exe" if sys.platform == "win32" else "ffprobe")
    if bundled.is_file():
        _FFPROBE_BIN = bundled
        return _FFPROBE_BIN

    app_root_bin = APP_DIR / ("ffprobe.exe" if sys.platform == "win32" else "ffprobe")
    if app_root_bin.is_file():
        _FFPROBE_BIN = app_root_bin
        return _FFPROBE_BIN

    which_bin = shutil.which("ffprobe")
    if which_bin:
        _FFPROBE_BIN = Path(which_bin)
        return _FFPROBE_BIN

    local_appdata = os.environ.get("LOCALAPPDATA")
    if local_appdata:
        winget_dir = Path(local_appdata) / "Microsoft" / "WinGet" / "Packages"
        if winget_dir.exists():
            for p in winget_dir.glob("**/ffprobe.exe"):
                if p.is_file():
                    _FFPROBE_BIN = p
                    return _FFPROBE_BIN

    return None


def is_ffmpeg_available() -> bool:
    return (get_ffmpeg_path() is not None) and (get_ffprobe_path() is not None)


def run_ffprobe(args: List[str], timeout: int = 30) -> subprocess.CompletedProcess:
    ffprobe = get_ffprobe_path()
    if not ffprobe:
        raise FileNotFoundError("ffprobe executable was not found. Please bundle or install FFmpeg.")
    cmd = [str(ffprobe)] + args
    logger.debug("Running ffprobe command: %s", " ".join(cmd))
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, encoding="utf-8", errors="replace")


def kill_process_tree(pid: int) -> None:
    """Force terminate a process and all its children cleanly on Windows/Unix."""
    try:
        if sys.platform == "win32":
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], capture_output=True)
        else:
            os.kill(pid, 9)
    except Exception as e:
        logger.warning(f"Error killing process {pid}: {e}")


class FFmpegProcess:
    """Supervised FFmpeg process execution with real-time progress and cancellation."""

    def __init__(self):
        self.process: Optional[subprocess.Popen] = None
        self._cancelled: bool = False
        self._stderr_lines: List[str] = []

    def cancel(self) -> None:
        self._cancelled = True
        if self.process and self.process.poll() is None:
            logger.info("Cancelling FFmpeg process (PID %s)...", self.process.pid)
            kill_process_tree(self.process.pid)

    def is_cancelled(self) -> bool:
        return self._cancelled

    def run(
        self,
        args: List[str],
        total_duration: float = 0.0,
        progress_callback: Optional[Callable[[float, str, str], None]] = None,
        cancel_check: Optional[Callable[[], bool]] = None
    ) -> int:
        ffmpeg = get_ffmpeg_path()
        if not ffmpeg:
            raise FileNotFoundError("ffmpeg executable was not found.")

        # Ensure progress options are present
        cmd = [str(ffmpeg), "-nostats", "-progress", "pipe:1"] + args
        logger.info("Starting FFmpeg: %s", " ".join(cmd))

        self.process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1
        )

        self._stderr_lines.clear()

        # Thread to read stderr so buffers do not block
        def read_stderr():
            for line in self.process.stderr:
                self._stderr_lines.append(line)
                if len(self._stderr_lines) > 200:
                    self._stderr_lines.pop(0)

        err_thread = threading.Thread(target=read_stderr, daemon=True)
        err_thread.start()

        # Parse stdout key=value lines
        last_out_time_us = 0
        speed_str = "1.0x"
        time_str = "00:00:00"

        for raw_line in self.process.stdout:
            if self._cancelled or (cancel_check and cancel_check()):
                self.cancel()
                break

            line = raw_line.strip()
            if not line:
                continue

            if "=" in line:
                key, val = line.split("=", 1)
                key = key.strip()
                val = val.strip()

                if key == "out_time_us":
                    try:
                        last_out_time_us = int(val)
                    except ValueError:
                        pass
                elif key == "out_time_ms":
                    try:
                        last_out_time_us = int(val) * 1000
                    except ValueError:
                        pass
                elif key == "out_time":
                    time_str = val.split(".")[0]
                elif key == "speed":
                    speed_str = val
                elif key == "progress":
                    if total_duration > 0 and progress_callback:
                        cur_sec = last_out_time_us / 1_000_000.0
                        pct = min(100.0, max(0.0, (cur_sec / total_duration) * 100.0))
                        progress_callback(pct, speed_str, time_str)

        self.process.wait()
        err_thread.join(timeout=2.0)

        ret = self.process.returncode
        if self._cancelled:
            raise InterruptedError("FFmpeg execution was cancelled by user.")
        if ret != 0:
            err_msg = "".join(self._stderr_lines[-30:])
            logger.error("FFmpeg failed with return code %d:\n%s", ret, err_msg)
            raise RuntimeError(f"FFmpeg error (code {ret}):\n{err_msg}")

        if progress_callback:
            progress_callback(100.0, speed_str, time_str)

        return ret
