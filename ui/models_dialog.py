"""
ProPainter AI Models Downloader Dialog.
"""
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QMessageBox, QProgressBar, QPushButton,
    QVBoxLayout, QWidget
)

from core.models_manager import ModelDownloadWorker, are_models_installed


class ModelsDialog(QDialog):

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle("AI Model Weights Setup")
        self.setFixedWidth(460)
        self.setModal(True)

        self._worker: Optional[ModelDownloadWorker] = None
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(14)
        layout.setContentsMargins(20, 20, 20, 20)

        title = QLabel("ProPainter AI Models")
        title.setStyleSheet("font-size: 16px; font-weight: 600; color: #58a6ff;")
        layout.addWidget(title)

        desc = QLabel(
            "AI Video Inpainting requires deep learning models (~196 MB total):\n"
            "• raft-things.pth (Optical Flow)\n"
            "• recurrent_flow_completion.pth (Motion Completion)\n"
            "• ProPainter.pth (Spatio-Temporal Transformer)\n\n"
            "Models are downloaded once and stored locally in the models folder."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #8b949e; line-height: 1.4;")
        layout.addWidget(desc)

        self.status_lbl = QLabel("Ready to download.")
        self.status_lbl.setStyleSheet("font-weight: 500;")
        layout.addWidget(self.status_lbl)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        layout.addWidget(self.progress_bar)

        # Buttons
        btn_box = QHBoxLayout()
        btn_box.addStretch()

        self.start_btn = QPushButton("Start Download")
        self.start_btn.setObjectName("primaryBtn")
        self.start_btn.clicked.connect(self._start_download)

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self._cancel_or_close)

        btn_box.addWidget(self.cancel_btn)
        btn_box.addWidget(self.start_btn)
        layout.addLayout(btn_box)

    def _start_download(self):
        self.start_btn.setEnabled(False)
        self.status_lbl.setText("Connecting to release servers...")
        self.progress_bar.setValue(0)

        self._worker = ModelDownloadWorker(self)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_finished)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _on_progress(self, model_name: str, pct: float, speed_txt: str):
        self.progress_bar.setValue(int(pct))
        self.status_lbl.setText(f"Downloading {model_name} ({speed_txt}) - {pct:.1f}%")

    def _on_finished(self):
        self.progress_bar.setValue(100)
        self.status_lbl.setText("✓ All models downloaded and verified successfully!")
        self.status_lbl.setStyleSheet("color: #3fb950; font-weight: 600;")
        self.start_btn.setEnabled(False)
        self.cancel_btn.setText("Close")
        QMessageBox.information(
            self,
            "Download Complete",
            "ProPainter AI models have been installed and are ready to use."
        )
        self.accept()

    def _on_error(self, err_msg: str):
        self.status_lbl.setText("Download failed.")
        self.status_lbl.setStyleSheet("color: #f85149; font-weight: 600;")
        self.start_btn.setEnabled(True)
        QMessageBox.critical(
            self,
            "Download Error",
            f"Failed to download models:\n{err_msg}\n\nPlease check your internet connection."
        )

    def _cancel_or_close(self):
        if self._worker and self._worker.isRunning():
            self._worker.cancel()
            self._worker.wait(2000)
        self.reject()
