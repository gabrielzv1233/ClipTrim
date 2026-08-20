from __future__ import annotations

import errno
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import cliptrim


def media_info(*, duration: float = 1.01, fps: float = 30.0) -> cliptrim.MediaInfo:
    return cliptrim.MediaInfo(
        path="example.mp4",
        duration=duration,
        video_duration=duration,
        fps=fps,
        width=1920,
        height=1080,
        video_codec="h264",
        audio_codec="aac",
        pix_fmt="yuv420p",
        color_primaries=None,
        color_transfer=None,
        color_space=None,
    )


class FrameBoundaryTests(unittest.TestCase):
    def test_fractional_final_frame_is_preserved(self):
        info = media_info(duration=1.01, fps=30.0)

        self.assertEqual(info.frame_count, 31)
        self.assertAlmostEqual(cliptrim.snap_out_boundary(info.duration, info), 1.01)
        self.assertAlmostEqual(
            cliptrim.trim_frames_to_times(info, 0, info.frame_count - 1)[1],
            1.01,
        )

    def test_exact_exclusive_boundary_does_not_add_a_frame(self):
        info = media_info(duration=2.0, fps=30.0)

        self.assertAlmostEqual(cliptrim.snap_out_boundary(0.5, info), 0.5)

    def test_partial_final_frame_can_be_the_only_selected_frame(self):
        info = media_info(duration=1.01, fps=30.0)

        final_frame_start = cliptrim.last_frame_start_before(info.video_duration, info)

        self.assertAlmostEqual(final_frame_start, 1.0)
        self.assertLess(final_frame_start, info.video_duration)
        self.assertLess(info.video_duration - final_frame_start, info.frame_duration)


class TempCleanupTests(unittest.TestCase):
    def test_live_run_directory_is_not_removed(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            live = root / "run-111-live"
            stale = root / "run-222-stale"
            malformed = root / f"run-{'9' * 100}-malformed"
            legacy = root / "legacy"
            live.mkdir()
            stale.mkdir()
            malformed.mkdir()
            legacy.mkdir()
            (root / "orphan.tmp").write_text("temporary", encoding="utf-8")

            with mock.patch.object(
                cliptrim,
                "_is_process_running",
                side_effect=lambda pid: pid == 111,
            ):
                cliptrim._remove_stale_temp_children(root)

            self.assertTrue(live.is_dir())
            self.assertFalse(stale.exists())
            self.assertTrue(malformed.is_dir())
            self.assertTrue(legacy.is_dir())
            self.assertTrue((root / "orphan.tmp").is_file())


class ScrubCacheShutdownTests(unittest.TestCase):
    def test_timed_out_cache_thread_is_retained_and_detached(self):
        class Worker:
            def cancel(self):
                pass

        class Thread:
            def isRunning(self):
                return True

            def requestInterruption(self):
                pass

            def quit(self):
                pass

            def wait(self, timeout_ms):
                return False

        worker = Worker()
        thread = Thread()
        owner = SimpleNamespace(
            _scrub_cache_worker=worker,
            _scrub_cache_thread=thread,
            _retired_scrub_caches={},
            _scrub_cache_dir=Path("cache"),
            _scrub_cache_generation=7,
            _scrub_cache_result=(True, "", 7, "cache"),
            _scrub_cache_fps=30.0,
            _scrub_ram={1: object()},
            _scrub_ram_bytes=1,
        )

        stopped = cliptrim.MainWindow._stop_scrub_cache(owner)

        self.assertFalse(stopped)
        self.assertIn(thread, owner._retired_scrub_caches)
        self.assertIsNone(owner._scrub_cache_worker)
        self.assertIsNone(owner._scrub_cache_thread)
        self.assertIsNone(owner._scrub_cache_dir)


class ExportFinalizationTests(unittest.TestCase):
    def test_direct_atomic_replace(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "completed.mp4"
            destination = root / "output.mp4"
            source.write_bytes(b"new export")
            destination.write_bytes(b"old export")

            cliptrim.finalize_export_file(source, destination)

            self.assertEqual(destination.read_bytes(), b"new export")
            self.assertFalse(source.exists())

    def test_cross_volume_fallback_keeps_copy_atomic(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "completed.mp4"
            destination = root / "output.mp4"
            source.write_bytes(b"new export")
            destination.write_bytes(b"old export")
            real_replace = os.replace
            calls = 0

            def replace_with_first_call_failure(src, dst):
                nonlocal calls
                calls += 1
                if calls == 1:
                    raise OSError(errno.EXDEV, "different filesystems")
                return real_replace(src, dst)

            with mock.patch.object(cliptrim.os, "replace", replace_with_first_call_failure):
                cliptrim.finalize_export_file(source, destination)

            self.assertEqual(destination.read_bytes(), b"new export")
            self.assertFalse(source.exists())
            self.assertEqual(list(root.glob("*.part")), [])

    def test_failed_staging_replace_preserves_existing_destination(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "completed.mp4"
            destination = root / "output.mp4"
            source.write_bytes(b"new export")
            destination.write_bytes(b"old export")

            with mock.patch.object(
                cliptrim.os,
                "replace",
                side_effect=[
                    OSError(errno.EXDEV, "different filesystems"),
                    OSError(errno.EACCES, "destination is locked"),
                ],
            ):
                with self.assertRaises(OSError):
                    cliptrim.finalize_export_file(source, destination)

            self.assertEqual(destination.read_bytes(), b"old export")
            self.assertEqual(source.read_bytes(), b"new export")
            self.assertEqual(list(root.glob(".*.part")), [])


class ExternalToolFailureTests(unittest.TestCase):
    def test_thumbnail_timeout_returns_an_empty_image(self):
        with (
            mock.patch.object(cliptrim, "FFMPEG", "ffmpeg"),
            mock.patch.object(
                cliptrim,
                "run_hidden",
                side_effect=subprocess.TimeoutExpired("ffmpeg", 12),
            ),
        ):
            image = cliptrim.make_thumbnail("example.mp4", 0.0)

        self.assertTrue(image.isNull())

    def test_keyframe_probe_timeout_falls_back_to_transcode(self):
        with (
            mock.patch.object(cliptrim, "FFPROBE", "ffprobe"),
            mock.patch.object(
                cliptrim,
                "run_hidden",
                side_effect=subprocess.TimeoutExpired("ffprobe", 15),
            ),
        ):
            self.assertFalse(cliptrim.is_keyframe_at("example.mp4", 1.0, 30.0))


if __name__ == "__main__":
    unittest.main()
