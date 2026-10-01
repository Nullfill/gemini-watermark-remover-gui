"""
Application Configuration and Settings Manager.
Handles paths, persistent user settings, and temporary directory maintenance.
"""
from pathlib import Path
import shutil
import sys
from typing import Dict, Any

from PySide6.QtCore import QSettings

# Determine base app directory (handles both frozen PyInstaller EXE and normal dev)
if getattr(sys, "frozen", False):
    APP_DIR = Path(sys.executable).resolve().parent
else:
    APP_DIR = Path(__file__).resolve().parent.parent

MODELS_DIR = APP_DIR / "models"
FFMPEG_DIR = APP_DIR / "ffmpeg"
DEFAULT_OUTPUT_DIR = APP_DIR / "output"
TEMP_DIR = APP_DIR / "temp"
LOGS_DIR = APP_DIR / "logs"

# Ensure runtime directories exist
MODELS_DIR.mkdir(parents=True, exist_ok=True)
DEFAULT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
TEMP_DIR.mkdir(parents=True, exist_ok=True)
LOGS_DIR.mkdir(parents=True, exist_ok=True)

# Quality Preset mapping
QUALITY_PRESETS: Dict[str, Dict[str, Any]] = {
    "high": {
        "label": "High Quality (CRF 16)",
        "crf": 16,
        "preset": "slow",
        "description": "Best visual fidelity, larger output file"
    },
    "balanced": {
        "label": "Balanced (CRF 20) - Recommended",
        "crf": 20,
        "preset": "medium",
        "description": "Standard balance between quality and file size"
    },
    "small": {
        "label": "Smaller File (CRF 26)",
        "crf": 26,
        "preset": "fast",
        "description": "Aggressive compression for minimal storage"
    },
    "custom": {
        "label": "Custom CRF",
        "crf": 20,
        "preset": "medium",
        "description": "User-defined constant rate factor"
    }
}


class AppConfig:
    _SETTINGS_ORG = "DevSaraiva"
    _SETTINGS_APP = "WatermarkRemover"

    @classmethod
    def get_settings(cls) -> QSettings:
        return QSettings(cls._SETTINGS_ORG, cls._SETTINGS_APP)

    @classmethod
    def get_output_dir(cls) -> Path:
        s = cls.get_settings()
        val = s.value("output_directory", str(DEFAULT_OUTPUT_DIR))
        p = Path(val) if val else DEFAULT_OUTPUT_DIR
        p.mkdir(parents=True, exist_ok=True)
        return p

    @classmethod
    def set_output_dir(cls, path: Path) -> None:
        cls.get_settings().setValue("output_directory", str(path))

    @classmethod
    def get_quality_preset(cls) -> str:
        return cls.get_settings().value("quality_preset", "balanced")

    @classmethod
    def set_quality_preset(cls, preset: str) -> None:
        if preset in QUALITY_PRESETS:
            cls.get_settings().setValue("quality_preset", preset)

    @classmethod
    def get_crf(cls) -> int:
        preset = cls.get_quality_preset()
        if preset == "custom":
            return int(cls.get_settings().value("custom_crf", 20))
        return QUALITY_PRESETS.get(preset, QUALITY_PRESETS["balanced"])["crf"]

    @classmethod
    def set_custom_crf(cls, crf: int) -> None:
        cls.get_settings().setValue("custom_crf", max(0, min(51, int(crf))))

    @classmethod
    def get_x264_preset(cls) -> str:
        preset = cls.get_quality_preset()
        if preset == "custom":
            return cls.get_settings().value("custom_x264_preset", "medium")
        return QUALITY_PRESETS.get(preset, QUALITY_PRESETS["balanced"])["preset"]

    @classmethod
    def get_device(cls) -> str:
        """Options: 'auto', 'cuda', 'cpu'"""
        return cls.get_settings().value("device", "auto")

    @classmethod
    def set_device(cls, device: str) -> None:
        if device in ("auto", "cuda", "cpu"):
            cls.get_settings().setValue("device", device)

    @classmethod
    def get_ctx_size(cls) -> int:
        """Inpaint context window size (multiple of 8)"""
        val = int(cls.get_settings().value("ctx_size", 256))
        return max(128, min(512, val - (val % 8)))

    @classmethod
    def set_ctx_size(cls, size: int) -> None:
        cls.get_settings().setValue("ctx_size", max(128, min(512, size - (size % 8))))

    @classmethod
    def get_mask_dilation(cls) -> int:
        """Mask dilation in pixels"""
        return int(cls.get_settings().value("mask_dilation", 6))

    @classmethod
    def set_mask_dilation(cls, dilation: int) -> None:
        cls.get_settings().setValue("mask_dilation", max(1, min(24, int(dilation))))

    @classmethod
    def cleanup_old_temp(cls) -> None:
        """Clean leftover temporary files from previous crashed sessions."""
        if not TEMP_DIR.exists():
            return
        for item in TEMP_DIR.iterdir():
            try:
                if item.is_dir():
                    shutil.rmtree(item, ignore_errors=True)
                else:
                    item.unlink(missing_ok=True)
            except Exception:
                pass
