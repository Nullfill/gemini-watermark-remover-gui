"""
Modern Dark Theme QSS Stylesheet and Palette for PySide6.
"""

DARK_THEME_QSS = """
/* Global Application Styles */
QWidget {
    background-color: #0d1117;
    color: #e6edf3;
    font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, Roboto, sans-serif;
    font-size: 13px;
    selection-background-color: #1f6feb;
    selection-color: #ffffff;
}

QMainWindow {
    background-color: #0d1117;
}

QDialog {
    background-color: #161b22;
}

/* ScrollArea */
QScrollArea {
    background-color: transparent;
    border: none;
}
QScrollArea > QWidget > QWidget {
    background-color: transparent;
}

/* GroupBox & Cards */
QGroupBox {
    background-color: #161b22;
    border: 1px solid #30363d;
    border-radius: 8px;
    margin-top: 24px;
    padding: 16px 12px 12px 12px;
    font-weight: 600;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 12px;
    padding: 2px 8px;
    color: #58a6ff;
    background-color: #161b22;
    border: 1px solid #30363d;
    border-radius: 4px;
}

/* Push Buttons */
QPushButton {
    background-color: #21262d;
    color: #c9d1d9;
    border: 1px solid #30363d;
    border-radius: 6px;
    padding: 7px 16px;
    font-weight: 500;
    min-height: 20px;
}
QPushButton:hover {
    background-color: #30363d;
    border-color: #8b949e;
    color: #ffffff;
}
QPushButton:pressed {
    background-color: #161b22;
}
QPushButton:disabled {
    background-color: #161b22;
    color: #484f58;
    border-color: #21262d;
}

/* Primary Action Button */
QPushButton#primaryBtn {
    background-color: #238636;
    color: #ffffff;
    border: 1px solid #2ea043;
    font-size: 14px;
    font-weight: 600;
    padding: 10px 20px;
}
QPushButton#primaryBtn:hover {
    background-color: #2ea043;
    border-color: #3fb950;
}
QPushButton#primaryBtn:pressed {
    background-color: #1a7f37;
}
QPushButton#primaryBtn:disabled {
    background-color: #194323;
    color: #6e7681;
    border-color: #21262d;
}

/* Danger / Cancel Button */
QPushButton#dangerBtn {
    background-color: #21262d;
    color: #f85149;
    border: 1px solid #da3633;
}
QPushButton#dangerBtn:hover {
    background-color: #b62324;
    color: #ffffff;
}
QPushButton#dangerBtn:pressed {
    background-color: #8e1519;
}

/* Secondary Button */
QPushButton#secondaryBtn {
    background-color: #1f6feb;
    color: #ffffff;
    border: 1px solid #388bfd;
}
QPushButton#secondaryBtn:hover {
    background-color: #388bfd;
}

/* Inputs & SpinBoxes */
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {
    background-color: #0d1117;
    color: #e6edf3;
    border: 1px solid #30363d;
    border-radius: 6px;
    padding: 6px 10px;
    min-height: 20px;
}
QLineEdit:focus, QSpinBox:focus, QComboBox:focus {
    border-color: #58a6ff;
    outline: none;
}
QComboBox::drop-down {
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 24px;
    border-left: 1px solid #30363d;
}
QComboBox QAbstractItemView {
    background-color: #161b22;
    border: 1px solid #30363d;
    selection-background-color: #1f6feb;
    selection-color: #ffffff;
    padding: 4px;
}

/* Radio Buttons */
QRadioButton {
    spacing: 8px;
    color: #c9d1d9;
}
QRadioButton::indicator {
    width: 16px;
    height: 16px;
    border-radius: 8px;
    border: 1px solid #30363d;
    background-color: #0d1117;
}
QRadioButton::indicator:checked {
    background-color: #1f6feb;
    border-color: #58a6ff;
}
QRadioButton:hover {
    color: #ffffff;
}

/* Progress Bar */
QProgressBar {
    background-color: #0d1117;
    border: 1px solid #30363d;
    border-radius: 6px;
    text-align: center;
    color: #ffffff;
    font-weight: 600;
    min-height: 18px;
}
QProgressBar::chunk {
    background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #1f6feb, stop:1 #238636);
    border-radius: 5px;
}

/* Sliders */
QSlider::groove:horizontal {
    height: 6px;
    background-color: #21262d;
    border-radius: 3px;
}
QSlider::sub-page:horizontal {
    background-color: #1f6feb;
    border-radius: 3px;
}
QSlider::handle:horizontal {
    background-color: #58a6ff;
    border: 2px solid #ffffff;
    width: 14px;
    margin-top: -5px;
    margin-bottom: -5px;
    border-radius: 7px;
}
QSlider::handle:horizontal:hover {
    background-color: #79c0ff;
}

/* Drop Zone Frame */
QFrame#dropZone {
    background-color: #161b22;
    border: 2px dashed #30363d;
    border-radius: 12px;
}
QFrame#dropZone:hover, QFrame#dropZone[dragOver="true"] {
    border-color: #58a6ff;
    background-color: #1a2230;
}

/* Status Labels & Badges */
QLabel#badge {
    background-color: #21262d;
    color: #8b949e;
    border: 1px solid #30363d;
    border-radius: 4px;
    padding: 2px 6px;
    font-size: 11px;
    font-weight: 600;
}
QLabel#badgeHighlight {
    background-color: rgba(56, 139, 253, 0.15);
    color: #58a6ff;
    border: 1px solid rgba(56, 139, 253, 0.4);
    border-radius: 4px;
    padding: 2px 6px;
    font-size: 11px;
    font-weight: 600;
}
QLabel#badgeWarning {
    background-color: rgba(210, 153, 34, 0.15);
    color: #d29922;
    border: 1px solid rgba(210, 153, 34, 0.4);
    border-radius: 4px;
    padding: 2px 6px;
    font-size: 11px;
    font-weight: 600;
}
"""
