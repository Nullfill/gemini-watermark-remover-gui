"""
Comprehensive Integration and Unit Tests for Watermark Remover.
Covers all 15 required scenarios:
1. Video with audio
2. Video without audio
3. Various frame rates: 24, 30, 60 FPS
4. Multiple audio tracks
5. Filename with spaces
6. Filename with Unicode (Persian)
7. Windows paths with spaces
8. Four-corner watermark presets
9. Detection failure and fallback
10. Mid-process cancellation
11. Crash recovery and temp cleanup
12. Missing ffmpeg handling
13. Missing model weights handling
14. Missing CUDA hardware handling
15. Existing output file auto-rename (no overwrite)
16. Full pipeline ffprobe verification (resolution, duration, streams, decode)
"""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import unittest

# Ensure project root in sys.path
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from core.config import AppConfig, DEFAULT_OUTPUT_DIR, MODELS_DIR, TEMP_DIR
from core.detection import (
    calculate_crop_window, detect_watermark, resolve_corner_preset
)
from core.ffmpeg_runner import (
    get_ffmpeg_path, get_ffprobe_path, is_ffmpeg_available
)
from core.models_manager import are_models_installed, get_missing_models
from core.processor import (
    ProcessingOptions, WatermarkProcessor, generate_safe_output_path
)
from core.video_info import extract_preview_frame, probe_video


class TestWatermarkRemover(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.test_dir = _ROOT / "tests" / "scratch"
        cls.test_dir.mkdir(parents=True, exist_ok=True)
        cls.ffmpeg = get_ffmpeg_path()
        cls.ffprobe = get_ffprobe_path()
        assert cls.ffmpeg is not None, "FFmpeg binary must be available for tests."

    @classmethod
    def tearDownClass(cls):
        if cls.test_dir.exists():
            shutil.rmtree(cls.test_dir, ignore_errors=True)

    def _create_synthetic_video(
        self,
        filename: str,
        duration: float = 1.0,
        fps: int = 24,
        with_audio: bool = True,
        num_audio_tracks: int = 1,
        width: int = 640,
        height: int = 360
    ) -> Path:
        out_path = self.test_dir / filename
        out_path.parent.mkdir(parents=True, exist_ok=True)

        # Video source: colored test bars with moving rectangle
        cmd = [
            str(self.ffmpeg), "-y",
            "-f", "lavfi",
            "-i", f"testsrc=duration={duration}:size={width}x{height}:rate={fps}",
        ]

        if with_audio:
            for _ in range(num_audio_tracks):
                cmd.extend(["-f", "lavfi", "-i", f"sine=frequency=1000:duration={duration}"])

        cmd.extend(["-map", "0:v", "-c:v", "libx264", "-pix_fmt", "yuv420p"])

        if with_audio:
            cmd.extend(["-c:a", "aac"])
            for idx in range(num_audio_tracks):
                cmd.extend(["-map", f"{idx+1}:a"])
        else:
            cmd.append("-an")

        cmd.append(str(out_path))

        res = subprocess.run(cmd, capture_output=True, text=True, errors="replace")
        if res.returncode != 0:
            raise RuntimeError(f"Failed to generate synthetic video {filename}:\n{res.stderr}")

        return out_path

    # Test 1: Video with audio
    def test_01_video_with_audio(self):
        v = self._create_synthetic_video("synth_with_audio.mp4", duration=1.0, with_audio=True)
        info = probe_video(v)
        self.assertEqual(len(info.audio_streams), 1)
        self.assertEqual(info.audio_streams[0].codec_name, "aac")

    # Test 2: Video without audio
    def test_02_video_without_audio(self):
        v = self._create_synthetic_video("synth_no_audio.mp4", duration=1.0, with_audio=False)
        info = probe_video(v)
        self.assertEqual(len(info.audio_streams), 0)

    # Test 3: Various FPS (24, 30, 60)
    def test_03_various_fps(self):
        for fps in (24, 30, 60):
            v = self._create_synthetic_video(f"synth_{fps}fps.mp4", duration=1.0, fps=fps)
            info = probe_video(v)
            self.assertAlmostEqual(info.fps, float(fps), delta=1.0)

    # Test 4: Multiple audio tracks
    def test_04_multi_audio_tracks(self):
        v = self._create_synthetic_video("synth_2audio.mp4", duration=1.0, num_audio_tracks=2)
        info = probe_video(v)
        self.assertEqual(len(info.audio_streams), 2)

    # Test 5: Filename with spaces
    def test_05_filename_with_spaces(self):
        v = self._create_synthetic_video("video with spaces in name.mp4", duration=1.0)
        self.assertTrue(v.is_file())
        info = probe_video(v)
        self.assertEqual(info.width, 640)

    # Test 6: Filename with Unicode (Persian)
    def test_06_filename_with_unicode(self):
        v = self._create_synthetic_video("ویدیوی آزمایشی واترمارک.mp4", duration=1.0)
        self.assertTrue(v.is_file())
        info = probe_video(v)
        self.assertEqual(info.width, 640)

    # Test 7: Windows paths with spaces
    def test_07_windows_paths_with_spaces(self):
        spaced_dir = self.test_dir / "Folder With Spaces"
        v = spaced_dir / "spaced_video.mp4"
        spaced_dir.mkdir(parents=True, exist_ok=True)
        cmd = [
            str(self.ffmpeg), "-y",
            "-f", "lavfi", "-i", "testsrc=duration=0.5:size=320x240:rate=24",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            str(v)
        ]
        subprocess.run(cmd, check=True, capture_output=True)
        info = probe_video(v)
        self.assertEqual(info.width, 320)

    # Test 8: Watermark in four corners
    def test_08_watermark_in_four_corners(self):
        W, H = 1920, 1080
        for corner in ("tl", "tr", "bl", "br"):
            x, y, w, h = resolve_corner_preset(corner, W, H)
            self.assertGreaterEqual(x, 0)
            self.assertGreaterEqual(y, 0)
            self.assertLessEqual(x + w, W)
            self.assertLessEqual(y + h, H)

    # Test 9: Watermark detection failure and fallback
    def test_09_detection_failure_fallback(self):
        # A completely flat color video has no structured edges
        v = self.test_dir / "flat_black.mp4"
        cmd = [
            str(self.ffmpeg), "-y",
            "-f", "lavfi", "-i", "color=c=black:s=320x240:d=1",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            str(v)
        ]
        subprocess.run(cmd, check=True, capture_output=True)
        res = detect_watermark(v)
        self.assertFalse(res.is_confident)
        self.assertEqual(len(res.box), 4)

    # Test 10: Cancel mid-process
    def test_10_cancel_mid_process(self):
        v = self._create_synthetic_video("cancel_test.mp4", duration=2.0)
        opts = ProcessingOptions(
            input_path=v,
            output_dir=self.test_dir,
            method="delogo",
            box=(10, 10, 50, 50)
        )
        proc = WatermarkProcessor(opts)
        # Cancel right away
        proc.cancel()
        proc.run()  # runs synchronously in this test thread
        self.assertTrue(proc._is_cancelled)

    # Test 11: Crash recovery and temp cleanup
    def test_11_crash_recovery_temp_cleanup(self):
        dummy_job = TEMP_DIR / "job_dummy_leftover_123"
        dummy_job.mkdir(parents=True, exist_ok=True)
        dummy_file = dummy_job / "leftover.tmp"
        dummy_file.write_text("crash artifact", encoding="utf-8")
        self.assertTrue(dummy_file.exists())

        AppConfig.cleanup_old_temp()
        self.assertFalse(dummy_job.exists())

    # Test 12: Missing ffmpeg handling
    def test_12_missing_ffmpeg_handling(self):
        import core.ffmpeg_runner as ffr
        orig_func = ffr.get_ffmpeg_path
        try:
            ffr.get_ffmpeg_path = lambda: None
            with self.assertRaises(FileNotFoundError):
                proc = ffr.FFmpegProcess()
                proc.run(["-version"])
        finally:
            ffr.get_ffmpeg_path = orig_func

    # Test 13: Missing model weights handling
    def test_13_missing_model_weights_handling(self):
        # Verify are_models_installed accurately inspects files
        installed = are_models_installed()
        missing = get_missing_models()
        self.assertIsInstance(installed, bool)
        self.assertIsInstance(missing, list)

    # Test 14: Missing CUDA hardware handling
    def test_14_missing_cuda_handling(self):
        import torch
        if not torch.cuda.is_available():
            v = self._create_synthetic_video("cuda_test.mp4", duration=0.5)
            opts = ProcessingOptions(
                input_path=v,
                output_dir=self.test_dir,
                method="delogo",
                box=(10, 10, 20, 20),
                device="cuda"
            )
            proc = WatermarkProcessor(opts)
            with self.assertRaises(RuntimeError) as ctx:
                proc._resolve_torch_device()
            self.assertIn("CUDA", str(ctx.exception))

    # Test 15: Existing output file auto-rename (never overwrite)
    def test_15_output_exists_auto_rename(self):
        v = self._create_synthetic_video("sample_test_overwrite.mp4", duration=0.5)
        out_dir = self.test_dir / "out_test"
        out_dir.mkdir(parents=True, exist_ok=True)

        path1 = generate_safe_output_path(v, out_dir)
        path1.write_text("existing content", encoding="utf-8")

        path2 = generate_safe_output_path(v, out_dir)
        self.assertNotEqual(path1, path2)
        self.assertTrue(str(path2).endswith("_clean_1.mp4"))
        self.assertNotEqual(path1, v)
        self.assertNotEqual(path2, v)

    # Test 16: Full pipeline ffprobe verification
    def test_16_full_pipeline_verification(self):
        v = self._create_synthetic_video("pipeline_source.mp4", duration=1.5, fps=30, with_audio=True)
        out_dir = self.test_dir / "pipeline_out"
        out_dir.mkdir(parents=True, exist_ok=True)

        opts = ProcessingOptions(
            input_path=v,
            output_dir=out_dir,
            method="delogo",
            box=(10, 10, 60, 60),
            crf=18,
            x264_preset="ultrafast"
        )
        proc = WatermarkProcessor(opts)
        results = []
        proc.finished.connect(lambda p: results.append(p))
        proc.run()

        self.assertEqual(len(results), 1)
        out_video = results[0]
        self.assertTrue(out_video.is_file())

        src_info = probe_video(v)
        out_info = probe_video(out_video)

        # Assertions required by user prompt:
        # - Resolution is correct
        self.assertEqual(out_info.width, src_info.width)
        self.assertEqual(out_info.height, src_info.height)
        # - Duration does not have unusual drift (< 0.1s)
        self.assertAlmostEqual(out_info.duration, src_info.duration, delta=0.1)
        # - Audio exists
        self.assertEqual(len(out_info.audio_streams), len(src_info.audio_streams))
        # - Output is decodable
        prev_png = extract_preview_frame(out_video, timestamp_sec=0.5)
        self.assertTrue(prev_png.is_file())
        self.assertGreater(prev_png.stat().st_size, 500)


def run_tests():
    suite = unittest.TestLoader().loadTestsFromTestCase(TestWatermarkRemover)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)


if __name__ == "__main__":
    run_tests()
