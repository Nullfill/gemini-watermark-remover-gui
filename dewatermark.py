#!/usr/bin/env python3
"""
dewatermark — Command-line and GUI entry point for Watermark Remover.
Backwards-compatible with original CLI options while powered by the modernized robust core.
"""
import argparse
from pathlib import Path
import sys

# Ensure root directory is in sys.path
_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from core.config import AppConfig, DEFAULT_OUTPUT_DIR
from core.detection import detect_watermark, resolve_corner_preset
from core.ffmpeg_runner import is_ffmpeg_available
from core.logger import setup_logger
from core.models_manager import are_models_installed
from core.processor import ProcessingOptions, WatermarkProcessor
from core.video_info import extract_preview_frame, probe_video


def main_cli():
    logger = setup_logger("dewatermark_cli")

    parser = argparse.ArgumentParser(
        description="Remove visible watermark/logo overlay from a video (CLI & GUI)."
    )
    parser.add_argument(
        "input",
        nargs="?",
        help="Input video file path. If omitted, launches the Graphical User Interface."
    )
    parser.add_argument("-o", "--output", help="Output video path (default: output/<name>_clean.mp4)")
    parser.add_argument(
        "--method",
        choices=["inpaint", "delogo", "crop"],
        default="inpaint",
        help="Removal method: inpaint (AI flow-based, default), delogo (fast interpolation), crop (cut band)"
    )
    parser.add_argument(
        "--corner",
        choices=["br", "bl", "tr", "tl"],
        help="Force preset corner: br (bottom-right), bl (bottom-left), tr (top-right), tl (top-left)"
    )
    parser.add_argument("--box", help="Explicit bounding box 'X,Y,W,H' in pixels (skips auto-detection)")
    parser.add_argument("--crf", type=int, default=20, help="x264 quality factor (default 20, lower=better)")
    parser.add_argument(
        "--preset",
        default="medium",
        choices=["ultrafast", "superfast", "veryfast", "faster", "fast", "medium", "slow", "slower", "veryslow"],
        help="x264 encoding preset speed"
    )
    parser.add_argument(
        "--device",
        choices=["auto", "cuda", "cpu"],
        default="auto",
        help="Inpainting hardware compute device (default: auto)"
    )
    parser.add_argument("--ctx", type=int, default=256, help="Inpaint window size in px (multiple of 8, default 256)")
    parser.add_argument("--dilation", type=int, default=6, help="Mask dilation in px (default 6)")
    parser.add_argument("--preview", action="store_true", help="Generate a preview PNG with detected box and exit")
    parser.add_argument("--gui", action="store_true", help="Force launching the Graphical User Interface")

    args = parser.parse_args()

    # If no input provided or --gui flag passed, launch GUI
    if args.gui or not args.input:
        from app import main as gui_main
        gui_main()
        return

    if not is_ffmpeg_available():
        sys.exit("Error: FFmpeg or FFprobe executable not found. Please bundle or install FFmpeg.")

    src_path = Path(args.input).resolve()
    if not src_path.is_file():
        sys.exit(f"Error: Input video not found: {src_path}")

    # Probe video
    v_info = probe_video(src_path)
    print(f"Loaded: {src_path.name} | {v_info.resolution_str} | {v_info.fps_str} | {v_info.duration_str}")

    # Determine bounding box
    if args.box:
        try:
            parts = [int(v.strip()) for v in args.box.split(",")]
            if len(parts) != 4:
                raise ValueError
            box = tuple(parts)
            print(f"Using manual box: X={box[0]}, Y={box[1]}, W={box[2]}, H={box[3]}")
        except Exception:
            sys.exit("Error: --box must be in format 'X,Y,W,H' (e.g. 618,1634,462,286)")
    elif args.corner:
        box = resolve_corner_preset(args.corner, v_info.width, v_info.height)
        print(f"Using corner preset '{args.corner}': box={box}")
    else:
        print("Auto-detecting watermark location...")
        res = detect_watermark(src_path)
        box = res.box
        print(f"Detected watermark at {res.corner.upper()} (Confidence: {res.confidence:.1f}/10): box={box}")
        if not res.is_confident:
            print("  [!] Low confidence. Recommended to test with --preview or specify --corner.")

    # Preview mode
    if args.preview:
        out_prev = src_path.with_name(f"{src_path.stem}_preview.png")
        from core.ffmpeg_runner import get_ffmpeg_path
        import subprocess
        ff = get_ffmpeg_path()
        vf = f"drawbox=x={box[0]}:y={box[1]}:w={box[2]}:h={box[3]}:color=red@1.0:t=4"
        cmd = [str(ff), "-y", "-ss", "00:00:02", "-i", str(src_path), "-vf", vf, "-frames:v", "1", "-update", "1", str(out_prev)]
        subprocess.run(cmd, capture_output=True)
        print(f"Preview image generated: {out_prev}")
        return

    # Check AI models for inpaint
    if args.method == "inpaint" and not are_models_installed():
        sys.exit(
            "Error: ProPainter model weights not found in models/.\n"
            "Please run the GUI or download weights into the models directory before running CLI inpaint."
        )

    out_dir = Path(args.output).parent if args.output else DEFAULT_OUTPUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    opts = ProcessingOptions(
        input_path=src_path,
        output_dir=out_dir,
        method=args.method,
        box=box,
        crf=args.crf,
        x264_preset=args.preset,
        device=args.device,
        ctx_size=args.ctx,
        dilation=args.dilation
    )

    processor = WatermarkProcessor(opts)
    processor.stage_changed.connect(lambda s: print(f"[*] Stage: {s}"))
    processor.progress_changed.connect(lambda p, d: print(f"    Progress: {p:.1f}% ({d})"))
    processor.warning_occurred.connect(lambda w: print(f"    [WARNING] {w}"))
    processor.error_occurred.connect(lambda e: sys.exit(f"Error: {e}"))
    processor.finished.connect(lambda o: print(f"[✓] Completed successfully! Saved to:\n{o}"))

    processor.run()


if __name__ == "__main__":
    main_cli()
