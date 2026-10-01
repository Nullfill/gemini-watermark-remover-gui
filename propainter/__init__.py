"""
ProPainter Video Inpainting Engine.
Integrated and patched for Windows Desktop Application.
"""
from pathlib import Path
import sys

# Ensure local package directory and subdirectories can be resolved
_pkg_dir = Path(__file__).resolve().parent
if str(_pkg_dir) not in sys.path:
    sys.path.insert(0, str(_pkg_dir))

# Import local inference module so propainter.inference is always populated
try:
    from . import inference
    from .inference import inpaint_crop_video
except Exception:
    import inference
    from inference import inpaint_crop_video

__all__ = ["inpaint_crop_video", "inference"]
