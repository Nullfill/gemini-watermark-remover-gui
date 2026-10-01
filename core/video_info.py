"""
Video Metadata Extraction and Stream Inspection using ffprobe.
Detects VFR, HDR, audio/subtitle tracks, rotation, and color specifications.
"""
from dataclasses import dataclass, field
from fractions import Fraction
import json
from pathlib import Path
import subprocess
from typing import List, Optional, Tuple

from core.ffmpeg_runner import get_ffmpeg_path, run_ffprobe
from core.logger import get_logger

logger = get_logger()


@dataclass
class AudioStreamInfo:
    index: int
    codec_name: str
    channels: int
    channel_layout: str
    sample_rate: int
    bit_rate: Optional[int]
    language: str
    title: str


@dataclass
class SubtitleStreamInfo:
    index: int
    codec_name: str
    language: str
    title: str
    is_bitmap: bool


@dataclass
class VideoInfo:
    path: Path
    width: int
    height: int
    duration: float
    bit_rate: int
    video_codec: str
    pix_fmt: str
    bit_depth: int
    r_frame_rate: str
    avg_frame_rate: str
    fps: float
    is_vfr: bool
    time_base: str
    nb_frames: int
    color_primaries: Optional[str]
    color_transfer: Optional[str]
    color_space: Optional[str]
    color_range: Optional[str]
    is_hdr: bool
    rotation: int
    audio_streams: List[AudioStreamInfo] = field(default_factory=list)
    subtitle_streams: List[SubtitleStreamInfo] = field(default_factory=list)
    chapters_count: int = 0

    @property
    def resolution_str(self) -> str:
        return f"{self.width}x{self.height}"

    @property
    def duration_str(self) -> str:
        mins = int(self.duration // 60)
        secs = int(self.duration % 60)
        return f"{mins:02d}:{secs:02d}"

    @property
    def fps_str(self) -> str:
        vfr_tag = " (VFR)" if self.is_vfr else " (CFR)"
        return f"{self.fps:.2f} fps{vfr_tag}"


def _parse_fraction(s: str) -> float:
    try:
        if "/" in s:
            num, den = s.split("/")
            return float(num) / float(den) if float(den) != 0 else 0.0
        return float(s)
    except Exception:
        return 0.0


def probe_video(path: Path) -> VideoInfo:
    path = Path(path).resolve()
    if not path.is_file():
        raise FileNotFoundError(f"Video file not found: {path}")

    args = [
        "-v", "error",
        "-show_format",
        "-show_streams",
        "-show_chapters",
        "-of", "json",
        str(path)
    ]
    res = run_ffprobe(args)
    if res.returncode != 0:
        raise RuntimeError(f"ffprobe failed to analyze video:\n{res.stderr}")

    try:
        data = json.loads(res.stdout)
    except Exception as e:
        raise RuntimeError(f"Failed to parse ffprobe json output: {e}")

    streams = data.get("streams", [])
    format_data = data.get("format", {})
    duration = float(format_data.get("duration", 0.0) or 0.0)
    total_bit_rate = int(format_data.get("bit_rate", 0) or 0)
    chapters_count = len(data.get("chapters", []))

    # Find video stream
    v_stream = next((s for s in streams if s.get("codec_type") == "video"), None)
    if not v_stream:
        raise ValueError(f"No video stream found in {path.name}")

    width = int(v_stream.get("width", 0))
    height = int(v_stream.get("height", 0))
    video_codec = v_stream.get("codec_name", "unknown")
    pix_fmt = v_stream.get("pix_fmt", "yuv420p")
    time_base = v_stream.get("time_base", "1/1000")

    bit_depth = 8
    raw_bits = v_stream.get("bits_per_raw_sample")
    if raw_bits and str(raw_bits).isdigit():
        bit_depth = int(raw_bits)
    elif "10" in pix_fmt or "p10" in pix_fmt:
        bit_depth = 10
    elif "12" in pix_fmt or "p12" in pix_fmt:
        bit_depth = 12

    r_fps_str = v_stream.get("r_frame_rate", "0/0")
    avg_fps_str = v_stream.get("avg_frame_rate", "0/0")
    r_fps = _parse_fraction(r_fps_str)
    avg_fps = _parse_fraction(avg_fps_str)

    # Frame rate calculation & VFR detection
    fps = avg_fps if avg_fps > 0 else (r_fps if r_fps > 0 else 24.0)
    is_vfr = False
    if r_fps > 0 and avg_fps > 0:
        # If rates differ by more than 0.2 fps, it is Variable Frame Rate
        if abs(r_fps - avg_fps) > 0.2:
            is_vfr = True

    nb_frames = 0
    nb_frames_val = v_stream.get("nb_frames")
    if nb_frames_val and str(nb_frames_val).isdigit():
        nb_frames = int(nb_frames_val)
    elif duration > 0 and fps > 0:
        nb_frames = round(duration * fps)

    # Color metadata & HDR detection
    color_primaries = v_stream.get("color_primaries")
    color_transfer = v_stream.get("color_transfer")
    color_space = v_stream.get("color_space")
    color_range = v_stream.get("color_range")

    is_hdr = False
    if color_transfer in ("smpte2084", "arib-std-b67") or color_primaries == "bt2020" or bit_depth > 8:
        is_hdr = True

    # Rotation / Display matrix
    rotation = 0
    for side_data in v_stream.get("side_data_list", []):
        if "rotation" in side_data:
            rotation = int(side_data["rotation"])
            break
    if rotation == 0 and "tags" in v_stream:
        rot_tag = v_stream["tags"].get("rotate")
        if rot_tag and str(rot_tag).lstrip("-").isdigit():
            rotation = int(rot_tag)

    # Audio streams
    audio_streams: List[AudioStreamInfo] = []
    for s in streams:
        if s.get("codec_type") == "audio":
            tags = s.get("tags", {})
            br = int(s.get("bit_rate", 0)) if s.get("bit_rate") else None
            audio_streams.append(
                AudioStreamInfo(
                    index=int(s.get("index", 0)),
                    codec_name=s.get("codec_name", "unknown"),
                    channels=int(s.get("channels", 2) or 2),
                    channel_layout=s.get("channel_layout", "stereo"),
                    sample_rate=int(s.get("sample_rate", 44100) or 44100),
                    bit_rate=br,
                    language=tags.get("language", "und"),
                    title=tags.get("title", "")
                )
            )

    # Subtitle streams
    subtitle_streams: List[SubtitleStreamInfo] = []
    bitmap_sub_codecs = {"hdmv_pgs_subtitle", "dvd_subtitle", "xsub"}
    for s in streams:
        if s.get("codec_type") == "subtitle":
            tags = s.get("tags", {})
            cname = s.get("codec_name", "unknown")
            subtitle_streams.append(
                SubtitleStreamInfo(
                    index=int(s.get("index", 0)),
                    codec_name=cname,
                    language=tags.get("language", "und"),
                    title=tags.get("title", ""),
                    is_bitmap=(cname in bitmap_sub_codecs)
                )
            )

    info = VideoInfo(
        path=path,
        width=width,
        height=height,
        duration=duration,
        bit_rate=total_bit_rate,
        video_codec=video_codec,
        pix_fmt=pix_fmt,
        bit_depth=bit_depth,
        r_frame_rate=r_fps_str,
        avg_frame_rate=avg_fps_str,
        fps=fps,
        is_vfr=is_vfr,
        time_base=time_base,
        nb_frames=nb_frames,
        color_primaries=color_primaries,
        color_transfer=color_transfer,
        color_space=color_space,
        color_range=color_range,
        is_hdr=is_hdr,
        rotation=rotation,
        audio_streams=audio_streams,
        subtitle_streams=subtitle_streams,
        chapters_count=chapters_count
    )

    logger.info(
        "Probed video: %s | %dx%d | %.2f fps (VFR=%s) | HDR=%s | %d audio | %d subs",
        path.name, width, height, fps, is_vfr, is_hdr, len(audio_streams), len(subtitle_streams)
    )
    return info


def extract_preview_frame(video_path: Path, timestamp_sec: float = 1.0, out_image_path: Optional[Path] = None) -> Path:
    video_path = Path(video_path).resolve()
    ffmpeg = get_ffmpeg_path()
    if not ffmpeg:
        raise FileNotFoundError("FFmpeg executable not found.")

    if out_image_path is None:
        from core.config import TEMP_DIR
        out_image_path = TEMP_DIR / f"preview_{video_path.stem}.png"

    out_image_path.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        str(ffmpeg), "-y",
        "-ss", str(max(0.0, timestamp_sec)),
        "-i", str(video_path),
        "-frames:v", "1",
        "-update", "1",
        str(out_image_path)
    ]
    logger.debug("Extracting preview frame: %s", " ".join(cmd))
    res = subprocess.run(cmd, capture_output=True, text=True, errors="replace")
    if res.returncode != 0 or not out_image_path.exists():
        # Fallback without -ss
        cmd_fallback = [
            str(ffmpeg), "-y",
            "-i", str(video_path),
            "-frames:v", "1",
            "-update", "1",
            str(out_image_path)
        ]
        res_fallback = subprocess.run(cmd_fallback, capture_output=True, text=True, errors="replace")
        if res_fallback.returncode != 0 or not out_image_path.exists():
            raise RuntimeError(f"Failed to extract preview frame:\n{res.stderr}\n{res_fallback.stderr}")

    return out_image_path
