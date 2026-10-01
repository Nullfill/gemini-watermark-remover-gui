"""
Watermark Removal Pipeline Orchestrator.
Runs in a background QThread to keep the GUI fluid, providing cancellation,
stream preservation, color metadata propagation, and exact VFR timing.
"""
from dataclasses import dataclass
from datetime import datetime
import os
from pathlib import Path
import shutil
import sys
import time
from typing import Callable, List, Optional, Tuple
import uuid

from PySide6.QtCore import QObject, QThread, Signal
import torch

from core.config import AppConfig, MODELS_DIR, TEMP_DIR
from core.detection import calculate_crop_window
from core.ffmpeg_runner import FFmpegProcess, get_ffmpeg_path, is_ffmpeg_available
from core.logger import get_logger
from core.models_manager import are_models_installed
from core.video_info import VideoInfo, probe_video
from propainter.inference import inpaint_crop_video

logger = get_logger()


@dataclass
class ProcessingOptions:
    input_path: Path
    output_dir: Path
    method: str  # 'inpaint', 'delogo', 'crop'
    box: Tuple[int, int, int, int]  # x, y, w, h
    crf: int = 20
    x264_preset: str = "medium"
    device: str = "auto"  # 'auto', 'cuda', 'cpu'
    ctx_size: int = 256
    dilation: int = 6


def generate_safe_output_path(input_path: Path, output_dir: Path) -> Path:
    """Generate a clean output filename that never overwrites input or existing files."""
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = input_path.stem
    ext = input_path.suffix.lower()
    if ext not in (".mp4", ".mov", ".mkv"):
        ext = ".mp4"

    candidate = output_dir / f"{stem}_clean{ext}"
    if not candidate.exists() and candidate != input_path:
        return candidate

    counter = 1
    while True:
        candidate = output_dir / f"{stem}_clean_{counter}{ext}"
        if not candidate.exists() and candidate != input_path:
            return candidate
        counter += 1


class WatermarkProcessor(QThread):
    stage_changed = Signal(str)            # stage name
    progress_changed = Signal(float, str)  # percent, details text
    warning_occurred = Signal(str)         # non-fatal warning
    error_occurred = Signal(str)           # fatal error description
    finished = Signal(Path)                # final output path

    def __init__(self, options: ProcessingOptions, parent: Optional[QObject] = None):
        super().__init__(parent)
        self.options = options
        self._is_cancelled = False
        self._ffmpeg_proc: Optional[FFmpegProcess] = None
        self._work_dir: Optional[Path] = None

    def cancel(self):
        """Request immediate cooperative cancellation."""
        logger.info("Cancellation requested by user.")
        self._is_cancelled = True
        if self._ffmpeg_proc:
            self._ffmpeg_proc.cancel()

    def run(self):
        try:
            self._execute()
        except InterruptedError:
            logger.info("Pipeline stopped by cancellation.")
            self._cleanup_temp()
        except Exception as e:
            logger.exception("Pipeline failed with exception: %s", e)
            self._cleanup_temp()
            self.error_occurred.emit(str(e))

    def _cleanup_temp(self):
        if self._work_dir and self._work_dir.exists():
            try:
                shutil.rmtree(self._work_dir, ignore_errors=True)
            except Exception as e:
                logger.warning("Failed to clean up temp dir %s: %e", self._work_dir, e)

    def _check_cancel(self):
        if self._is_cancelled:
            raise InterruptedError("Operation cancelled.")

    def _resolve_torch_device(self) -> torch.device:
        dev_choice = self.options.device.lower()
        if dev_choice == "cuda":
            if not torch.cuda.is_available():
                raise RuntimeError(
                    "NVIDIA GPU (CUDA) was selected, but PyTorch cannot detect a CUDA-compatible GPU. "
                    "Please install the CUDA version of PyTorch or select CPU."
                )
            return torch.device("cuda")
        elif dev_choice == "cpu":
            return torch.device("cpu")
        else:  # 'auto'
            if torch.cuda.is_available():
                logger.info("Auto device: selected NVIDIA CUDA (%s)", torch.cuda.get_device_name(0))
                return torch.device("cuda")
            logger.info("Auto device: selected CPU")
            return torch.device("cpu")

    def _build_stream_mapping_args(self, video_info: VideoInfo) -> List[str]:
        """
        Build explicit FFmpeg stream mapping to preserve all audio, subtitles, chapters, and metadata.
        """
        args = [
            "-map", "[v]",
            "-map_metadata", "0",
            "-map_chapters", "0"
        ]

        # Audio streams
        if len(video_info.audio_streams) > 0:
            args.extend(["-map", "0:a?"])
            # Check compatibility with MP4
            compatible_audio = {"aac", "mp3", "ac3", "eac3", "opus", "flac", "alac"}
            has_incompatible = any(s.codec_name not in compatible_audio for s in video_info.audio_streams)
            if has_incompatible:
                logger.info("Incompatible audio codec found for MP4; transcoding audio to AAC.")
                args.extend(["-c:a", "aac", "-b:a", "192k"])
            else:
                args.extend(["-c:a", "copy"])

        # Subtitle streams
        if len(video_info.subtitle_streams) > 0:
            has_bitmap = any(s.is_bitmap for s in video_info.subtitle_streams)
            if has_bitmap:
                self.warning_occurred.emit(
                    "Notice: Bitmap subtitles (PGS/DVD) cannot be losslessly packaged into MP4 and were skipped."
                )
            else:
                args.extend(["-map", "0:s?"])
                args.extend(["-c:s", "mov_text"])

        # Data streams if any
        args.extend(["-map", "0:d?"])

        # Color metadata preservation
        if video_info.color_primaries:
            args.extend(["-color_primaries", video_info.color_primaries])
        if video_info.color_transfer:
            args.extend(["-color_trc", video_info.color_transfer])
        if video_info.color_space:
            args.extend(["-colorspace", video_info.color_space])
        if video_info.color_range:
            args.extend(["-color_range", video_info.color_range])

        return args

    def _execute(self):
        opts = self.options
        if not is_ffmpeg_available():
            raise FileNotFoundError("FFmpeg is missing. Please bundle or install FFmpeg before proceeding.")

        if not opts.input_path.is_file():
            raise FileNotFoundError(f"Input video does not exist: {opts.input_path}")

        # Step 1: Probe video
        self.stage_changed.emit("Analyzing video stream")
        self.progress_changed.emit(5.0, "Probing streams and container...")
        self._check_cancel()

        v_info = probe_video(opts.input_path)

        # Check HDR
        if v_info.is_hdr:
            self.warning_occurred.emit(
                "HDR / 10-bit Video Detected: AI Inpainting processes textures in standard 8-bit color space. "
                "The reconstructed watermark patch will be rendered in SDR tonality. "
                "If full 10-bit HDR dynamic range is strictly required, the 'Delogo' method is recommended."
            )

        if v_info.is_vfr:
            logger.info("VFR detected on input: exact frame-by-frame PTS timestamps will be maintained.")

        # Resolve output destination
        final_output_path = generate_safe_output_path(opts.input_path, opts.output_dir)

        # Setup temporary isolated scratch directory
        job_id = f"job_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
        self._work_dir = TEMP_DIR / job_id
        self._work_dir.mkdir(parents=True, exist_ok=True)

        W, H = v_info.width, v_info.height
        bx, by, bw, bh = opts.box

        # Dispatch method
        if opts.method == "inpaint":
            self._run_inpaint_pipeline(v_info, final_output_path)
        elif opts.method == "delogo":
            self._run_delogo_pipeline(v_info, final_output_path)
        elif opts.method == "crop":
            self._run_crop_pipeline(v_info, final_output_path)
        else:
            raise ValueError(f"Unknown removal method: {opts.method}")

        # Step Final: Verification
        if not final_output_path.is_file() or final_output_path.stat().st_size < 1000:
            raise RuntimeError("Pipeline failed to create a valid output video file.")

        self._cleanup_temp()
        self.stage_changed.emit("Finished")
        self.progress_changed.emit(100.0, f"Saved clean video to {final_output_path.name}")
        self.finished.emit(final_output_path)

    def _run_inpaint_pipeline(self, v_info: VideoInfo, output_path: Path):
        opts = self.options
        if not are_models_installed():
            raise FileNotFoundError(
                "ProPainter AI models are not downloaded. Please download the model weights first."
            )

        device = self._resolve_torch_device()
        W, H = v_info.width, v_info.height
        bx, by, bw, bh = opts.box

        cx, cy, size = calculate_crop_window(opts.box, W, H, ctx=opts.ctx_size)
        logger.info("Inpaint window: %dx%d at (%d, %d)", size, size, cx, cy)

        crop_vid = self._work_dir / "crop.mp4"
        mask_img = self._work_dir / "mask.png"
        patch_vid = self._work_dir / "patch.mp4"

        # 1. Crop window with exact PTS
        self.stage_changed.emit("Preparing video patch")
        self.progress_changed.emit(10.0, "Extracting localized watermark window...")
        self._check_cancel()

        self._ffmpeg_proc = FFmpegProcess()
        crop_args = [
            "-y", "-i", str(opts.input_path),
            "-vf", f"crop={size}:{size}:{cx}:{cy}",
            "-c:v", "libx264", "-crf", "0", "-preset", "ultrafast",
            "-fps_mode", "passthrough",
            "-an", str(crop_vid)
        ]
        self._ffmpeg_proc.run(
            crop_args,
            total_duration=v_info.duration,
            progress_callback=lambda pct, spd, t: self.progress_changed.emit(10.0 + pct * 0.1, f"Cropping window ({spd})"),
            cancel_check=lambda: self._is_cancelled
        )
        self._check_cancel()

        # 2. Generate mask in local window coordinates
        mx, my = bx - cx, by - cy
        mask_args = [
            "-y", "-f", "lavfi",
            "-i", f"color=c=black:s={size}x{size}",
            "-vf", f"drawbox=x={mx}:y={my}:w={bw}:h={bh}:color=white:t=fill",
            "-frames:v", "1",
            "-update", "1",
            str(mask_img)
        ]
        self._ffmpeg_proc = FFmpegProcess()
        self._ffmpeg_proc.run(mask_args)
        self._check_cancel()

        # 3. ProPainter AI Inpainting
        self.stage_changed.emit("Running AI inpainting")

        def inpaint_prog(stage_str, current, total):
            pct = 20.0 + (current / max(1, total)) * 60.0
            self.progress_changed.emit(pct, stage_str)

        inpaint_crop_video(
            video_path=crop_vid,
            mask_path=mask_img,
            output_path=patch_vid,
            models_dir=MODELS_DIR,
            device=device,
            dilation=opts.dilation,
            progress_callback=inpaint_prog,
            cancel_check=lambda: self._is_cancelled
        )
        self._check_cancel()

        # 4. Composite overlay back onto original with full stream preservation
        self.stage_changed.emit("Encoding final video")
        self.progress_changed.emit(82.0, "Compositing patch and multiplexing streams...")

        filter_complex = f"[0:v][1:v]overlay={cx}:{cy}:format=auto[v]"
        mapping_args = self._build_stream_mapping_args(v_info)

        mux_args = [
            "-y",
            "-i", str(opts.input_path),
            "-i", str(patch_vid),
            "-filter_complex", filter_complex
        ] + mapping_args + [
            "-c:v", "libx264",
            "-crf", str(opts.crf),
            "-preset", opts.x264_preset,
            str(output_path)
        ]

        self._ffmpeg_proc = FFmpegProcess()
        self._ffmpeg_proc.run(
            mux_args,
            total_duration=v_info.duration,
            progress_callback=lambda pct, spd, t: self.progress_changed.emit(82.0 + pct * 0.17, f"Muxing streams ({spd})"),
            cancel_check=lambda: self._is_cancelled
        )

    def _run_delogo_pipeline(self, v_info: VideoInfo, output_path: Path):
        opts = self.options
        W, H = v_info.width, v_info.height
        bx, by, bw, bh = opts.box

        # Delogo requires box to be at least 1px away from borders
        dx = max(1, bx)
        dy = max(1, by)
        dw = min(bw, W - dx - 1)
        dh = min(bh, H - dy - 1)

        self.stage_changed.emit("Encoding with Delogo filter")
        self.progress_changed.emit(10.0, "Interpolating watermark area...")

        filter_complex = f"[0:v]delogo=x={dx}:y={dy}:w={dw}:h={dh}[v]"
        mapping_args = self._build_stream_mapping_args(v_info)

        mux_args = [
            "-y",
            "-i", str(opts.input_path),
            "-filter_complex", filter_complex
        ] + mapping_args + [
            "-c:v", "libx264",
            "-crf", str(opts.crf),
            "-preset", opts.x264_preset,
            str(output_path)
        ]

        self._ffmpeg_proc = FFmpegProcess()
        self._ffmpeg_proc.run(
            mux_args,
            total_duration=v_info.duration,
            progress_callback=lambda pct, spd, t: self.progress_changed.emit(10.0 + pct * 0.88, f"Processing ({spd})"),
            cancel_check=lambda: self._is_cancelled
        )

    def _run_crop_pipeline(self, v_info: VideoInfo, output_path: Path):
        opts = self.options
        W, H = v_info.width, v_info.height
        bx, by, bw, bh = opts.box

        self.stage_changed.emit("Encoding with Crop filter")
        self.progress_changed.emit(10.0, "Cropping overlay band...")

        if by > H - (by + bh):
            # Watermark nearer to bottom
            crop_vf = f"[0:v]crop={W}:{by}:0:0,scale={W}:{H}[v]"
        else:
            # Watermark nearer to top
            cut = by + bh
            crop_vf = f"[0:v]crop={W}:{H - cut}:0:{cut},scale={W}:{H}[v]"

        mapping_args = self._build_stream_mapping_args(v_info)

        mux_args = [
            "-y",
            "-i", str(opts.input_path),
            "-filter_complex", crop_vf
        ] + mapping_args + [
            "-c:v", "libx264",
            "-crf", str(opts.crf),
            "-preset", opts.x264_preset,
            str(output_path)
        ]

        self._ffmpeg_proc = FFmpegProcess()
        self._ffmpeg_proc.run(
            mux_args,
            total_duration=v_info.duration,
            progress_callback=lambda pct, spd, t: self.progress_changed.emit(10.0 + pct * 0.88, f"Processing ({spd})"),
            cancel_check=lambda: self._is_cancelled
        )
