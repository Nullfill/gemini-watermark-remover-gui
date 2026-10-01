import os
import sys
from pathlib import Path

block_cipher = None

project_root = Path.cwd()

# Discover torchvision C-extension binaries (_C_stable.pyd, image_stable.pyd, etc.)
torchvision_binaries = []
try:
    import torchvision
    tv_dir = os.path.dirname(torchvision.__file__)
    for f in os.listdir(tv_dir):
        if f.endswith((".pyd", ".dll")):
            torchvision_binaries.append((os.path.join(tv_dir, f), "torchvision"))
except Exception as e:
    print(f"Warning discovering torchvision binaries: {e}")

datas = [
    (str(project_root / "NOTICE_PROPAINTER.txt"), "."),
    (str(project_root / "NOTICE_FFMPEG.txt"), "."),
    (str(project_root / "LICENSE"), "."),
    (str(project_root / "propainter"), "propainter"),
]

hiddenimports = [
    "PySide6",
    "PySide6.QtCore",
    "PySide6.QtGui",
    "PySide6.QtWidgets",
    "torch",
    "torchvision",
    "torchvision.transforms",
    "torchvision.transforms.functional",
    "cv2",
    "av",
    "scipy",
    "scipy.ndimage",
    "PIL",
    "PIL.Image",
    "einops",
    "addict",
    "yaml",
    "core",
    "core.config",
    "core.detection",
    "core.ffmpeg_runner",
    "core.logger",
    "core.models_manager",
    "core.processor",
    "core.video_info",
    "propainter",
    "propainter.inference",
    "inference",
    "model",
    "model.propainter",
    "model.recurrent_flow_completion",
    "RAFT",
    "RAFT.raft",
    "ui",
    "ui.main_window",
    "ui.preview_widget",
    "ui.settings_dialog",
    "ui.models_dialog",
    "ui.theme",
]

a = Analysis(
    ["app.py"],
    pathex=[str(project_root), str(project_root / "propainter")],
    binaries=torchvision_binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tensorflow", "tensorboard", "keras", "torch_xla",
        "sklearn", "pandas", "sqlalchemy", "transformers", "huggingface_hub",
        "selenium", "twisted", "trio", "uvicorn", "fastapi", "starlette",
        "telethon", "telegram", "pyarrow", "jinja2", "alembic", "redis",
        "lxml", "cryptography", "nacl", "pytest", "tkinter", "matplotlib",
        "IPython", "notebook", "tornado", "scrapy", "soundfile", "sounddevice"
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="WatermarkRemover",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    contents_directory="_internal",
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="WatermarkRemover",
)
