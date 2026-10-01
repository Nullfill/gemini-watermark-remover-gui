"""
Watermark Auto-Detection and Geometric Preset Computation.
Uses temporal stability edge persistence to robustly identify fixed-position overlays.
"""
from dataclasses import dataclass
from pathlib import Path
import subprocess
import sys
from typing import Callable, Dict, Optional, Tuple

import numpy as np

from core.ffmpeg_runner import get_ffmpeg_path
from core.logger import get_logger
from core.video_info import probe_video

logger = get_logger()


@dataclass
class DetectionResult:
    box: Tuple[int, int, int, int]  # x, y, w, h
    confidence: float              # 0.0 to 10.0
    corner: str                    # 'tl', 'tr', 'bl', 'br'
    is_confident: bool             # confidence >= 4.0
    scores: Dict[str, float]       # corner scores


def _neighbor_count(mask: np.ndarray) -> np.ndarray:
    """3x3 neighbor count of a boolean mask to remove isolated single-pixel noise."""
    p = np.pad(mask.astype(np.int16), 1)
    s = np.zeros_like(mask, dtype=np.int16)
    for dy in (0, 1, 2):
        for dx in (0, 1, 2):
            s += p[dy:dy + mask.shape[0], dx:dx + mask.shape[1]]
    return s


def sample_gray_frames(
    video_path: Path,
    W: int,
    H: int,
    duration: float,
    max_frames: int = 48,
    max_w: int = 480,
    cancel_check: Optional[Callable[[], bool]] = None
) -> Tuple[np.ndarray, int, int]:
    """Sample low-resolution grayscale frames for temporal edge analysis."""
    ffmpeg = get_ffmpeg_path()
    if not ffmpeg:
        raise FileNotFoundError("FFmpeg executable not found.")

    dw = min(W, max_w)
    dh = max(2, round(H * dw / W))
    dw -= dw % 2
    dh -= dh % 2

    fps = 3.0 if duration <= 0 else min(3.0, max(0.5, max_frames / duration))

    cmd = [
        str(ffmpeg), "-v", "error",
        "-i", str(video_path),
        "-vf", f"fps={fps},scale={dw}:{dh},format=gray",
        "-f", "rawvideo", "pipe:1"
    ]
    logger.debug("Sampling gray frames: %s", " ".join(cmd))

    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    if cancel_check and cancel_check():
        proc.kill()
        raise InterruptedError("Frame sampling cancelled.")

    stdout, stderr = proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(f"FFmpeg frame sampling failed:\n{stderr.decode('utf-8', errors='ignore')}")

    buf = np.frombuffer(stdout, dtype=np.uint8)
    n = buf.size // (dw * dh)
    if n < 2:
        raise ValueError(f"Could not sample sufficient frames from {video_path.name}")

    frames = buf[: n * dw * dh].reshape(n, dh, dw)
    return frames, dw, dh


def detect_watermark(
    video_path: Path,
    max_frames: int = 48,
    max_w: int = 480,
    cancel_check: Optional[Callable[[], bool]] = None
) -> DetectionResult:
    """
    Detect the watermark bounding box using temporal edge stability.
    """
    info = probe_video(video_path)
    W, H, dur = info.width, info.height, info.duration

    if cancel_check and cancel_check():
        raise InterruptedError("Detection cancelled.")

    frames, dw, dh = sample_gray_frames(video_path, W, H, dur, max_frames=max_frames, max_w=max_w, cancel_check=cancel_check)

    f = frames.astype(np.float32)
    n = f.shape[0]
    gx = np.abs(np.diff(f, axis=2, prepend=f[:, :, :1]))
    gy = np.abs(np.diff(f, axis=1, prepend=f[:, :1, :]))
    grad = gx + gy

    thr = np.percentile(grad.reshape(n, -1), 93, axis=1)[:, None, None]
    edges = grad > np.maximum(thr, 4.0)
    edge_freq = edges.mean(axis=0)

    cand = edge_freq > 0.80
    cand &= _neighbor_count(cand) >= 3
    weight = edge_freq * cand

    cw, ch = round(dw * 0.34), round(dh * 0.24)
    regions = {
        "tl": (slice(0, ch), slice(0, cw)),
        "tr": (slice(0, ch), slice(dw - cw, dw)),
        "bl": (slice(dh - ch, dh), slice(0, cw)),
        "br": (slice(dh - ch, dh), slice(dw - cw, dw)),
    }

    scores = {}
    best_corner = "br"
    best_score = -1.0

    for name, (ys, xs) in regions.items():
        score = float(weight[ys, xs].sum())
        scores[name] = score
        if score > best_score:
            best_score = score
            best_corner = name

    ys, xs = regions[best_corner]
    sub = cand[ys, xs]
    yy, xx = np.where(sub)

    scale = W / dw
    if yy.size < 4:
        # Fallback to standard preset if no dense edges found
        box = resolve_corner_preset(best_corner, W, H)
        conf = 0.0
        logger.warning("Low edge density in detection; falling back to preset %s", best_corner)
    else:
        x0, x1 = np.percentile(xx, 2), np.percentile(xx, 98)
        y0, y1 = np.percentile(yy, 2), np.percentile(yy, 98)
        x0 += xs.start
        x1 += xs.start
        y0 += ys.start
        y1 += ys.start

        pad_x = (x1 - x0) * 0.30 + 4
        pad_y = (y1 - y0) * 0.30 + 4

        fx = max(0, round((x0 - pad_x) * scale))
        fy = max(0, round((y0 - pad_y) * scale))
        fw = min(W - fx, round((x1 - x0 + 2 * pad_x) * scale))
        fh = min(H - fy, round((y1 - y0 + 2 * pad_y) * scale))

        box = (fx, fy, fw, fh)
        conf = float(weight[ys, xs][sub].mean()) * 10.0

    logger.info("Watermark detected: box=%s, confidence=%.2f, corner=%s", box, conf, best_corner)

    return DetectionResult(
        box=box,
        confidence=conf,
        corner=best_corner,
        is_confident=(conf >= 4.0),
        scores=scores
    )


def resolve_corner_preset(
    corner: str,
    W: int,
    H: int,
    size_frac: float = 0.16,
    margin_frac: float = 0.02
) -> Tuple[int, int, int, int]:
    """Calculate bounding box for corner presets: 'tl', 'tr', 'bl', 'br'."""
    bw = round(W * size_frac)
    bh = min(round(W * size_frac * (W / H)), round(H * 0.30))
    m = round(min(W, H) * margin_frac)

    corners = {
        "br": (W - bw - m, H - bh - m),
        "bl": (m, H - bh - m),
        "tr": (W - bw - m, m),
        "tl": (m, m),
    }

    x, y = corners.get(corner.lower(), corners["br"])
    return (max(0, x), max(0, y), bw, bh)


def calculate_crop_window(
    box: Tuple[int, int, int, int],
    W: int,
    H: int,
    ctx: int = 256
) -> Tuple[int, int, int]:
    """
    Calculate a square context window around the watermark (multiple of 8).
    Inpainting only this window keeps memory bounded while retaining ample surrounding context.
    """
    x, y, w, h = box
    needed = max(w, h) + 48
    size = max(ctx, needed)
    size = min(size, W, H)
    size -= (size % 8)

    cx = int(round(x + w / 2 - size / 2))
    cy = int(round(y + h / 2 - size / 2))

    cx = max(0, min(cx, W - size))
    cy = max(0, min(cy, H - size))

    return cx, cy, size
