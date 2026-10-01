"""
Main Window for Watermark Remover.
Modern PySide6 GUI with drag-and-drop, interactive bounding box adjustment,
real-time progress tracking, and non-blocking background workers.
"""
from dataclasses import dataclass
import os
from pathlib import Path
import subprocess
import sys
from typing import Optional, Tuple

from PySide6.QtCore import QEvent, QPoint, QSize, Qt, QThread, Signal
from PySide6.QtGui import QColor, QDragEnterEvent, QDropEvent, QFont, QIcon, QPixmap
from PySide6.QtWidgets import (
    QApplication, QButtonGroup, QFileDialog, QFrame, QGridLayout, QGroupBox,
    QHBoxLayout, QLabel, QMainWindow, QMessageBox, QProgressBar, QPushButton,
    QRadioButton, QScrollArea, QSizePolicy, QSpinBox, QSplitter, QVBoxLayout,
    QWidget
)

from core.config import AppConfig, DEFAULT_OUTPUT_DIR, MODELS_DIR, TEMP_DIR
from core.detection import (
    DetectionResult, detect_watermark, resolve_corner_preset
)
from core.logger import get_logger
from core.models_manager import are_models_installed
from core.processor import ProcessingOptions, WatermarkProcessor
from core.video_info import VideoInfo, extract_preview_frame, probe_video
from ui.models_dialog import ModelsDialog
from ui.preview_widget import PreviewWidget
from ui.settings_dialog import SettingsDialog
from ui.theme import DARK_THEME_QSS

logger = get_logger()


class DetectWorker(QThread):
    finished = Signal(DetectionResult)
    error = Signal(str)

    def __init__(self, video_path: Path, parent=None):
        super().__init__(parent)
        self.video_path = video_path

    def run(self):
        try:
            res = detect_watermark(self.video_path)
            self.finished.emit(res)
        except Exception as e:
            self.error.emit(str(e))


class MainWindow(QMainWindow):

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Watermark Remover - Desktop Studio")
        self.resize(1120, 820)
        self.setMinimumSize(960, 680)
        self.setAcceptDrops(True)

        self._current_video_path: Optional[Path] = None
        self._current_video_info: Optional[VideoInfo] = None
        self._current_preview_frame: Optional[Path] = None
        self._active_processor: Optional[WatermarkProcessor] = None
        self._detect_worker: Optional[DetectWorker] = None
        self._last_output_path: Optional[Path] = None

        self._build_ui()
        self._update_models_status()

    def closeEvent(self, event):
        if self._detect_worker and self._detect_worker.isRunning():
            self._detect_worker.wait(1500)
        if self._active_processor and self._active_processor.isRunning():
            self._active_processor.cancel()
            self._active_processor.wait(2000)
        event.accept()

    def _build_ui(self):
        central = QWidget(self)
        self.setCentralWidget(central)
        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(16, 12, 16, 12)
        root_layout.setSpacing(12)

        # 1. Top Header Bar
        header = QHBoxLayout()
        title_box = QVBoxLayout()
        title = QLabel("Watermark Remover")
        title.setStyleSheet("font-size: 20px; font-weight: 700; color: #ffffff;")
        subtitle = QLabel("AI Inpainting • Lossless Delogo • VFR & HDR Color Preserving")
        subtitle.setStyleSheet("font-size: 12px; color: #8b949e;")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        header.addLayout(title_box)

        header.addStretch()

        self.models_btn = QPushButton("Checking Models...")
        self.models_btn.clicked.connect(self._open_models_dialog)
        header.addWidget(self.models_btn)

        self.settings_btn = QPushButton("⚙ Settings")
        self.settings_btn.clicked.connect(self._open_settings_dialog)
        header.addWidget(self.settings_btn)

        root_layout.addLayout(header)

        # 2. Main Splitter (Left: Controls & Info, Right: Interactive Preview)
        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(8)

        # LEFT PANEL (Scrollable)
        left_scroll = QScrollArea()
        left_scroll.setWidgetResizable(True)
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 8, 0)
        left_layout.setSpacing(12)

        # Drop Zone / File Card
        self.drop_frame = QFrame()
        self.drop_frame.setObjectName("dropZone")
        drop_layout = QVBoxLayout(self.drop_frame)
        drop_layout.setContentsMargins(16, 16, 16, 16)
        drop_layout.setAlignment(Qt.AlignCenter)

        self.drop_icon_lbl = QLabel("🎬")
        self.drop_icon_lbl.setStyleSheet("font-size: 32px;")
        self.drop_icon_lbl.setAlignment(Qt.AlignCenter)
        drop_layout.addWidget(self.drop_icon_lbl)

        self.drop_label = QLabel("Drag & Drop video file here\nor")
        self.drop_label.setStyleSheet("color: #8b949e; font-size: 13px;")
        self.drop_label.setAlignment(Qt.AlignCenter)
        drop_layout.addWidget(self.drop_label)

        self.select_btn = QPushButton("Select Video...")
        self.select_btn.setObjectName("secondaryBtn")
        self.select_btn.clicked.connect(self._on_select_video_clicked)
        drop_layout.addWidget(self.select_btn, alignment=Qt.AlignCenter)

        left_layout.addWidget(self.drop_frame)

        # Media Info Card
        self.info_group = QGroupBox("Video Information")
        self.info_layout = QGridLayout(self.info_group)
        self.info_layout.setSpacing(8)

        self.lbl_file = QLabel("File: -")
        self.lbl_file.setStyleSheet("font-weight: 600; color: #58a6ff;")
        self.info_layout.addWidget(self.lbl_file, 0, 0, 1, 2)

        self.badge_res = QLabel("-")
        self.badge_res.setObjectName("badgeHighlight")
        self.badge_dur = QLabel("-")
        self.badge_dur.setObjectName("badge")
        self.badge_fps = QLabel("-")
        self.badge_fps.setObjectName("badgeHighlight")
        self.badge_codec = QLabel("-")
        self.badge_codec.setObjectName("badge")
        self.badge_hdr = QLabel("SDR")
        self.badge_hdr.setObjectName("badge")

        badges_row = QHBoxLayout()
        badges_row.addWidget(self.badge_res)
        badges_row.addWidget(self.badge_dur)
        badges_row.addWidget(self.badge_fps)
        badges_row.addWidget(self.badge_codec)
        badges_row.addWidget(self.badge_hdr)
        badges_row.addStretch()

        self.info_layout.addLayout(badges_row, 1, 0, 1, 2)
        self.info_group.setVisible(False)
        left_layout.addWidget(self.info_group)

        # Removal Strategy Selection
        method_group = QGroupBox("Removal Method")
        method_layout = QVBoxLayout(method_group)
        method_layout.setSpacing(6)

        self.method_btn_group = QButtonGroup(self)
        self.radio_inpaint = QRadioButton("AI Inpaint / ProPainter (Default - Best Quality)")
        self.radio_inpaint.setChecked(True)
        self.radio_inpaint.setToolTip("Flow-based deep inpainting. Reconstructs moving textures behind the logo.")

        self.radio_delogo = QRadioButton("Delogo (Instant - Border Interpolation)")
        self.radio_delogo.setToolTip("FFmpeg delogo filter. Blurs watermark using edge pixels; fast on static scenes.")

        self.radio_crop = QRadioButton("Crop (Instant - Cut Border Band)")
        self.radio_crop.setToolTip("Crops out the watermark edge and scales back to original resolution.")

        self.method_btn_group.addButton(self.radio_inpaint, 1)
        self.method_btn_group.addButton(self.radio_delogo, 2)
        self.method_btn_group.addButton(self.radio_crop, 3)

        method_layout.addWidget(self.radio_inpaint)
        method_layout.addWidget(self.radio_delogo)
        method_layout.addWidget(self.radio_crop)
        left_layout.addWidget(method_group)

        # Watermark Controls & Quick Presets
        detect_group = QGroupBox("Watermark Position & Detection")
        det_layout = QVBoxLayout(detect_group)
        det_layout.setSpacing(8)

        det_btn_row = QHBoxLayout()
        self.detect_btn = QPushButton("🔍 Auto-Detect Watermark")
        self.detect_btn.clicked.connect(self._run_auto_detection)
        self.detect_status_lbl = QLabel("")
        self.detect_status_lbl.setStyleSheet("color: #8b949e; font-size: 11px;")
        det_btn_row.addWidget(self.detect_btn)
        det_btn_row.addWidget(self.detect_status_lbl)
        det_btn_row.addStretch()
        det_layout.addLayout(det_btn_row)

        # Corner Presets
        corner_row = QHBoxLayout()
        corner_row.addWidget(QLabel("Corner Presets:"))
        for name, key in [("Top Left", "tl"), ("Top Right", "tr"), ("Bottom Left", "bl"), ("Bottom Right", "br")]:
            btn = QPushButton(name)
            btn.clicked.connect(lambda _, k=key: self._apply_corner_preset(k))
            corner_row.addWidget(btn)
        det_layout.addLayout(corner_row)

        # Manual Coordinates
        coord_grid = QGridLayout()
        coord_grid.setSpacing(6)

        self.spin_x = QSpinBox()
        self.spin_x.setRange(0, 7680)
        self.spin_y = QSpinBox()
        self.spin_y.setRange(0, 7680)
        self.spin_w = QSpinBox()
        self.spin_w.setRange(8, 7680)
        self.spin_h = QSpinBox()
        self.spin_h.setRange(8, 7680)

        for s in (self.spin_x, self.spin_y, self.spin_w, self.spin_h):
            s.valueChanged.connect(self._on_spinbox_changed)

        coord_grid.addWidget(QLabel("X:"), 0, 0)
        coord_grid.addWidget(self.spin_x, 0, 1)
        coord_grid.addWidget(QLabel("Y:"), 0, 2)
        coord_grid.addWidget(self.spin_y, 0, 3)
        coord_grid.addWidget(QLabel("Width:"), 1, 0)
        coord_grid.addWidget(self.spin_w, 1, 1)
        coord_grid.addWidget(QLabel("Height:"), 1, 2)
        coord_grid.addWidget(self.spin_h, 1, 3)

        det_layout.addLayout(coord_grid)
        left_layout.addWidget(detect_group)

        left_layout.addStretch()
        left_scroll.setWidget(left_widget)
        splitter.addWidget(left_scroll)

        # RIGHT PANEL (Preview & Adjust Canvas)
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(8, 0, 0, 0)
        right_layout.setSpacing(8)

        preview_header = QHBoxLayout()
        preview_title = QLabel("Visual Preview & Box Editor")
        preview_title.setStyleSheet("font-weight: 600; color: #58a6ff;")
        preview_hint = QLabel("Drag box to move • Drag corner handles to resize")
        preview_hint.setStyleSheet("color: #8b949e; font-size: 11px;")
        preview_header.addWidget(preview_title)
        preview_header.addStretch()
        preview_header.addWidget(preview_hint)
        right_layout.addLayout(preview_header)

        self.preview_widget = PreviewWidget(self)
        self.preview_widget.box_changed.connect(self._on_preview_box_changed)
        right_layout.addWidget(self.preview_widget, stretch=1)

        splitter.addWidget(right_panel)
        splitter.setStretchFactor(0, 4)
        splitter.setStretchFactor(1, 6)
        root_layout.addWidget(splitter, stretch=1)

        # 3. Bottom Action & Progress Bar
        action_bar = QFrame()
        action_bar.setStyleSheet("background-color: #161b22; border-radius: 8px; padding: 6px;")
        action_layout = QVBoxLayout(action_bar)
        action_layout.setSpacing(8)

        top_action_row = QHBoxLayout()
        self.stage_lbl = QLabel("Ready")
        self.stage_lbl.setStyleSheet("font-weight: 600; color: #c9d1d9;")
        self.details_lbl = QLabel("")
        self.details_lbl.setStyleSheet("color: #8b949e; font-size: 11px;")

        top_action_row.addWidget(self.stage_lbl)
        top_action_row.addWidget(self.details_lbl)
        top_action_row.addStretch()

        self.open_output_btn = QPushButton("📁 Open Output Folder")
        self.open_output_btn.setVisible(False)
        self.open_output_btn.clicked.connect(self._open_output_folder)
        top_action_row.addWidget(self.open_output_btn)

        self.play_output_btn = QPushButton("▶ Play Clean Video")
        self.play_output_btn.setVisible(False)
        self.play_output_btn.clicked.connect(self._play_output_video)
        top_action_row.addWidget(self.play_output_btn)

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setObjectName("dangerBtn")
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.clicked.connect(self._cancel_processing)
        top_action_row.addWidget(self.cancel_btn)

        self.start_btn = QPushButton("Remove Watermark")
        self.start_btn.setObjectName("primaryBtn")
        self.start_btn.setEnabled(False)
        self.start_btn.clicked.connect(self._start_processing)
        top_action_row.addWidget(self.start_btn)

        action_layout.addLayout(top_action_row)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        action_layout.addWidget(self.progress_bar)

        root_layout.addWidget(action_bar)

    def _update_models_status(self):
        installed = are_models_installed()
        if installed:
            self.models_btn.setText("✓ AI Models Ready")
            self.models_btn.setStyleSheet("color: #3fb950; font-weight: 500;")
        else:
            self.models_btn.setText("⚠ Download AI Models")
            self.models_btn.setStyleSheet("color: #d29922; font-weight: 600;")

    def _open_models_dialog(self):
        dlg = ModelsDialog(self)
        dlg.exec()
        self._update_models_status()

    def _open_settings_dialog(self):
        dlg = SettingsDialog(self)
        dlg.exec()

    # Drag and Drop Events
    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            if urls and urls[0].isLocalFile():
                ext = Path(urls[0].toLocalFile()).suffix.lower()
                if ext in (".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v"):
                    event.acceptProposedAction()
                    self.drop_frame.setProperty("dragOver", True)
                    self.drop_frame.style().unpolish(self.drop_frame)
                    self.drop_frame.style().polish(self.drop_frame)
                    return
        event.ignore()

    def dragLeaveEvent(self, event: QEvent):
        self.drop_frame.setProperty("dragOver", False)
        self.drop_frame.style().unpolish(self.drop_frame)
        self.drop_frame.style().polish(self.drop_frame)

    def dropEvent(self, event: QDropEvent):
        self.drop_frame.setProperty("dragOver", False)
        self.drop_frame.style().unpolish(self.drop_frame)
        self.drop_frame.style().polish(self.drop_frame)

        urls = event.mimeData().urls()
        if urls and urls[0].isLocalFile():
            local_path = Path(urls[0].toLocalFile())
            self._load_video(local_path)
            event.acceptProposedAction()

    def _on_select_video_clicked(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Video File",
            "",
            "Video Files (*.mp4 *.mov *.mkv *.avi *.webm *.m4v);;All Files (*.*)"
        )
        if file_path:
            self._load_video(Path(file_path))

    def _load_video(self, path: Path):
        try:
            self.stage_lbl.setText("Analyzing video...")
            info = probe_video(path)
            self._current_video_path = path
            self._current_video_info = info

            # Update UI Info
            self.lbl_file.setText(f"File: {path.name}")
            self.badge_res.setText(info.resolution_str)
            self.badge_dur.setText(info.duration_str)
            self.badge_fps.setText(info.fps_str)
            self.badge_codec.setText(f"{info.video_codec.upper()} {info.bit_depth}-bit")

            if info.is_hdr:
                self.badge_hdr.setText("⚠ HDR 10-bit")
                self.badge_hdr.setObjectName("badgeWarning")
            else:
                self.badge_hdr.setText("SDR")
                self.badge_hdr.setObjectName("badge")
            self.badge_hdr.style().unpolish(self.badge_hdr)
            self.badge_hdr.style().polish(self.badge_hdr)

            self.info_group.setVisible(True)
            self.start_btn.setEnabled(True)
            self.open_output_btn.setVisible(False)
            self.play_output_btn.setVisible(False)

            # Extract preview frame
            self.stage_lbl.setText("Extracting preview frame...")
            p_img = extract_preview_frame(path, timestamp_sec=min(2.0, info.duration * 0.1))
            self._current_preview_frame = p_img
            self.preview_widget.set_frame_image(p_img, info.width, info.height)

            # Auto-detect watermark
            self._run_auto_detection()

        except Exception as e:
            logger.exception("Error loading video: %s", e)
            QMessageBox.critical(self, "Video Load Error", f"Failed to load video file:\n{e}")
            self.stage_lbl.setText("Error loading video.")

    def _run_auto_detection(self):
        if not self._current_video_path:
            return

        self.detect_btn.setEnabled(False)
        self.detect_status_lbl.setText("Detecting temporal edges...")
        self.stage_lbl.setText("Detecting watermark...")

        self._detect_worker = DetectWorker(self._current_video_path, self)
        self._detect_worker.finished.connect(self._on_detection_finished)
        self._detect_worker.error.connect(self._on_detection_error)
        self._detect_worker.start()

    def _on_detection_finished(self, res: DetectionResult):
        self.detect_btn.setEnabled(True)
        corner_names = {"br": "Bottom Right", "bl": "Bottom Left", "tr": "Top Right", "tl": "Top Left"}
        c_name = corner_names.get(res.corner, res.corner)

        if res.is_confident:
            self.detect_status_lbl.setText(f"✓ Found at {c_name} (Confidence: {res.confidence:.1f}/10)")
            self.detect_status_lbl.setStyleSheet("color: #3fb950;")
        else:
            self.detect_status_lbl.setText(f"⚠ Low confidence ({res.confidence:.1f}/10). Please verify box.")
            self.detect_status_lbl.setStyleSheet("color: #d29922;")

        self.preview_widget.set_box(*res.box)
        self.stage_lbl.setText("Watermark identified. Ready to remove.")

    def _on_detection_error(self, err_msg: str):
        self.detect_btn.setEnabled(True)
        self.detect_status_lbl.setText("Auto-detection failed. Using default preset.")
        self.detect_status_lbl.setStyleSheet("color: #f85149;")
        self._apply_corner_preset("br")
        self.stage_lbl.setText("Ready")

    def _apply_corner_preset(self, corner: str):
        if not self._current_video_info:
            return
        box = resolve_corner_preset(corner, self._current_video_info.width, self._current_video_info.height)
        self.preview_widget.set_box(*box)

    def _on_preview_box_changed(self, x: int, y: int, w: int, h: int):
        self.spin_x.blockSignals(True)
        self.spin_y.blockSignals(True)
        self.spin_w.blockSignals(True)
        self.spin_h.blockSignals(True)

        self.spin_x.setValue(x)
        self.spin_y.setValue(y)
        self.spin_w.setValue(w)
        self.spin_h.setValue(h)

        self.spin_x.blockSignals(False)
        self.spin_y.blockSignals(False)
        self.spin_w.blockSignals(False)
        self.spin_h.blockSignals(False)

    def _on_spinbox_changed(self):
        box = (self.spin_x.value(), self.spin_y.value(), self.spin_w.value(), self.spin_h.value())
        self.preview_widget.set_box(*box)

    def _start_processing(self):
        if not self._current_video_path or not self._current_video_info:
            return

        method = "inpaint"
        if self.radio_delogo.isChecked():
            method = "delogo"
        elif self.radio_crop.isChecked():
            method = "crop"

        # Check AI models if inpaint selected
        if method == "inpaint" and not are_models_installed():
            ans = QMessageBox.question(
                self,
                "Models Required",
                "ProPainter AI models (~196 MB) need to be downloaded before running AI Inpaint.\n\n"
                "Would you like to download them now?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes
            )
            if ans == QMessageBox.Yes:
                self._open_models_dialog()
                if not are_models_installed():
                    return
            else:
                return

        box = self.preview_widget.get_box()

        opts = ProcessingOptions(
            input_path=self._current_video_path,
            output_dir=AppConfig.get_output_dir(),
            method=method,
            box=box,
            crf=AppConfig.get_crf(),
            x264_preset=AppConfig.get_x264_preset(),
            device=AppConfig.get_device(),
            ctx_size=AppConfig.get_ctx_size(),
            dilation=AppConfig.get_mask_dilation()
        )

        # Toggle UI controls
        self.start_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.select_btn.setEnabled(False)
        self.detect_btn.setEnabled(False)
        self.open_output_btn.setVisible(False)
        self.play_output_btn.setVisible(False)
        self.progress_bar.setValue(0)

        # Launch Worker
        self._active_processor = WatermarkProcessor(opts, self)
        self._active_processor.stage_changed.connect(self._on_stage_changed)
        self._active_processor.progress_changed.connect(self._on_progress_changed)
        self._active_processor.warning_occurred.connect(self._on_warning)
        self._active_processor.error_occurred.connect(self._on_error)
        self._active_processor.finished.connect(self._on_finished)
        self._active_processor.start()

    def _cancel_processing(self):
        if self._active_processor and self._active_processor.isRunning():
            self.stage_lbl.setText("Cancelling operation...")
            self._active_processor.cancel()
            self._active_processor.wait(4000)
            self._reset_ui_controls()
            self.stage_lbl.setText("Cancelled by user.")
            self.progress_bar.setValue(0)

    def _on_stage_changed(self, stage_name: str):
        self.stage_lbl.setText(stage_name)

    def _on_progress_changed(self, pct: float, details: str):
        self.progress_bar.setValue(int(pct))
        self.details_lbl.setText(details)

    def _on_warning(self, warn_msg: str):
        logger.warning("Pipeline warning: %s", warn_msg)
        QMessageBox.warning(self, "Advisory Notice", warn_msg)

    def _on_error(self, err_msg: str):
        self._reset_ui_controls()
        self.stage_lbl.setText("Error occurred")
        self.details_lbl.setText("")
        QMessageBox.critical(self, "Processing Error", f"An error occurred during processing:\n\n{err_msg}")

    def _on_finished(self, output_path: Path):
        self._last_output_path = output_path
        self._reset_ui_controls()
        self.stage_lbl.setText("✓ Watermark Removal Completed!")
        self.details_lbl.setText(f"Saved: {output_path.name}")
        self.progress_bar.setValue(100)

        self.open_output_btn.setVisible(True)
        self.play_output_btn.setVisible(True)

        QMessageBox.information(
            self,
            "Success",
            f"Clean video successfully saved to:\n\n{output_path}"
        )

    def _reset_ui_controls(self):
        self.start_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.select_btn.setEnabled(True)
        self.detect_btn.setEnabled(True)

    def _open_output_folder(self):
        if self._last_output_path and self._last_output_path.is_file():
            if sys.platform == "win32":
                subprocess.run(["explorer", f"/select,{str(self._last_output_path)}"])
            else:
                subprocess.run(["open", str(self._last_output_path.parent)])
        else:
            out_dir = AppConfig.get_output_dir()
            if sys.platform == "win32":
                os.startfile(str(out_dir))
            else:
                subprocess.run(["open", str(out_dir)])

    def _play_output_video(self):
        if self._last_output_path and self._last_output_path.is_file():
            if sys.platform == "win32":
                os.startfile(str(self._last_output_path))
            else:
                subprocess.run(["open", str(self._last_output_path)])
