"""
ProPainter Video Inpainting Engine.
Integrated and patched for Windows Desktop Application.
"""
from pathlib import Path
import sys

# Ensure local modules (model, RAFT, core) can be resolved
_pkg_dir = Path(__file__).resolve().parent
if str(_pkg_dir) not in sys.path:
    sys.path.insert(0, str(_pkg_dir))
