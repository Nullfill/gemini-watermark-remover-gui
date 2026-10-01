"""
Application Settings & Hardware Configuration Dialog.
"""
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup, QComboBox, QDialog, QFileDialog, QFormLayout, QGroupBox,
    QHBoxLayout, QLabel, QLineEdit, QPushButton, QRadioButton, QSlider,
    QSpinBox, QVBoxLayout, QWidget
)
import torch

from core.config import AppConfig, DEFAULT_OUTPUT_DIR, QUALITY_PRESETS
from core.models_manager import are_models_installed


class SettingsDialog(QDialog):

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle("Settings - Watermark Remover")
        self.setMinimumWidth(520)
        self.setModal(True)

        self._build_ui()
        self._load_values()

    def _build_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(16)
        main_layout.setContentsMargins(20, 20, 20, 20)

        # 1. Output Folder Group
        out_group = QGroupBox("Output Directory")
        out_layout = QHBoxLayout(out_group)
        self.out_edit = QLineEdit()
        self.out_edit.setReadOnly(True)
        self.browse_btn = QPushButton("Browse...")
        self.browse_btn.clicked.connect(self._browse_output_dir)
        self.reset_out_btn = QPushButton("Reset")
        self.reset_out_btn.clicked.connect(lambda: self.out_edit.setText(str(DEFAULT_OUTPUT_DIR)))

        out_layout.addWidget(self.out_edit)
        out_layout.addWidget(self.browse_btn)
        out_layout.addWidget(self.reset_out_btn)
        main_layout.addWidget(out_group)

        # 2. Quality & Encoding Group
        qual_group = QGroupBox("Encoding Quality")
        qual_layout = QVBoxLayout(qual_group)

        self.qual_btn_group = QButtonGroup(self)
        self.radio_high = QRadioButton("High Quality (CRF 16) - Best fidelity, larger size")
        self.radio_balanced = QRadioButton("Balanced (CRF 20) - Recommended")
        self.radio_small = QRadioButton("Smaller File (CRF 26) - Aggressive compression")
        self.radio_custom = QRadioButton("Custom CRF")

        self.qual_btn_group.addButton(self.radio_high, 1)
        self.qual_btn_group.addButton(self.radio_balanced, 2)
        self.qual_btn_group.addButton(self.radio_small, 3)
        self.qual_btn_group.addButton(self.radio_custom, 4)

        qual_layout.addWidget(self.radio_high)
        qual_layout.addWidget(self.radio_balanced)
        qual_layout.addWidget(self.radio_small)
        qual_layout.addWidget(self.radio_custom)

        # Custom CRF controls
        custom_row = QHBoxLayout()
        custom_row.setContentsMargins(24, 0, 0, 0)
        self.crf_slider = QSlider(Qt.Horizontal)
        self.crf_slider.setRange(0, 51)
        self.crf_slider.setValue(20)
        self.crf_spin = QSpinBox()
        self.crf_spin.setRange(0, 51)
        self.crf_spin.setValue(20)
        self.crf_slider.valueChanged.connect(self.crf_spin.setValue)
        self.crf_spin.valueChanged.connect(self.crf_slider.setValue)

        custom_row.addWidget(QLabel("CRF Value (0 = lossless, 51 = worst):"))
        custom_row.addWidget(self.crf_slider)
        custom_row.addWidget(self.crf_spin)
        qual_layout.addLayout(custom_row)

        self.qual_btn_group.idToggled.connect(self._on_quality_toggled)
        main_layout.addWidget(qual_group)

        # 3. Hardware & Compute Device Group
        hw_group = QGroupBox("Hardware Acceleration")
        hw_layout = QVBoxLayout(hw_group)

        hw_form = QFormLayout()
        self.device_combo = QComboBox()
        self.device_combo.addItem("Auto (Prefer NVIDIA GPU if available)", "auto")
        self.device_combo.addItem("NVIDIA GPU (CUDA)", "cuda")
        self.device_combo.addItem("CPU (Safe fallback)", "cpu")
        hw_form.addRow("Compute Device:", self.device_combo)
        hw_layout.addLayout(hw_form)

        self.hw_info_lbl = QLabel()
        if torch.cuda.is_available():
            dev_name = torch.cuda.get_device_name(0)
            self.hw_info_lbl.setText(f"✓ NVIDIA CUDA detected: {dev_name}")
            self.hw_info_lbl.setStyleSheet("color: #3fb950; font-size: 11px;")
        else:
            self.hw_info_lbl.setText("ℹ CUDA not available. Inpainting will run on CPU.")
            self.hw_info_lbl.setStyleSheet("color: #8b949e; font-size: 11px;")
        hw_layout.addWidget(self.hw_info_lbl)

        main_layout.addWidget(hw_group)

        # 4. ProPainter Tuning Group
        pp_group = QGroupBox("AI Inpainting Parameters")
        pp_layout = QFormLayout(pp_group)

        self.ctx_spin = QSpinBox()
        self.ctx_spin.setRange(128, 512)
        self.ctx_spin.setSingleStep(16)
        self.ctx_spin.setValue(256)
        pp_layout.addRow("Context Window Size (px):", self.ctx_spin)

        self.dilation_spin = QSpinBox()
        self.dilation_spin.setRange(1, 24)
        self.dilation_spin.setValue(6)
        pp_layout.addRow("Mask Dilation (px):", self.dilation_spin)

        main_layout.addWidget(pp_group)

        # 5. Dialog Buttons
        btn_box = QHBoxLayout()
        btn_box.addStretch()

        self.save_btn = QPushButton("Save Settings")
        self.save_btn.setObjectName("primaryBtn")
        self.save_btn.clicked.connect(self._save_and_close)

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self.reject)

        btn_box.addWidget(self.cancel_btn)
        btn_box.addWidget(self.save_btn)
        main_layout.addLayout(btn_box)

    def _load_values(self):
        self.out_edit.setText(str(AppConfig.get_output_dir()))

        preset = AppConfig.get_quality_preset()
        if preset == "high":
            self.radio_high.setChecked(True)
        elif preset == "small":
            self.radio_small.setChecked(True)
        elif preset == "custom":
            self.radio_custom.setChecked(True)
        else:
            self.radio_balanced.setChecked(True)

        crf_val = AppConfig.get_crf()
        self.crf_spin.setValue(crf_val)
        self._on_quality_toggled()

        dev = AppConfig.get_device()
        idx = self.device_combo.findData(dev)
        if idx >= 0:
            self.device_combo.setCurrentIndex(idx)

        self.ctx_spin.setValue(AppConfig.get_ctx_size())
        self.dilation_spin.setValue(AppConfig.get_mask_dilation())

    def _on_quality_toggled(self):
        is_custom = self.radio_custom.isChecked()
        self.crf_slider.setEnabled(is_custom)
        self.crf_spin.setEnabled(is_custom)

    def _browse_output_dir(self):
        folder = QFileDialog.getExistingDirectory(
            self,
            "Select Output Folder",
            self.out_edit.text()
        )
        if folder:
            self.out_edit.setText(folder)

    def _save_and_close(self):
        # Save output dir
        p = Path(self.out_edit.text().strip())
        if p.exists() and p.is_dir():
            AppConfig.set_output_dir(p)

        # Save quality preset
        if self.radio_high.isChecked():
            AppConfig.set_quality_preset("high")
        elif self.radio_small.isChecked():
            AppConfig.set_quality_preset("small")
        elif self.radio_custom.isChecked():
            AppConfig.set_quality_preset("custom")
            AppConfig.set_custom_crf(self.crf_spin.value())
        else:
            AppConfig.set_quality_preset("balanced")

        # Save hardware device
        dev = self.device_combo.currentData()
        AppConfig.set_device(dev)

        # Save inpaint params
        AppConfig.set_ctx_size(self.ctx_spin.value())
        AppConfig.set_mask_dilation(self.dilation_spin.value())

        self.accept()
