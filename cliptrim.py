from __future__ import annotations

import atexit
import faulthandler
import json
import math
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import uuid
from collections import OrderedDict
from dataclasses import dataclass

if os.name == "nt":
    os.environ.setdefault("QT_MEDIA_BACKEND", "windows")

from fractions import Fraction
from pathlib import Path

def _resolve_app_dir() -> Path:
    try:
        compiled_dir = Path(__compiled__.containing_dir)
        return compiled_dir.parent if compiled_dir.name.casefold() == "runtime" else compiled_dir
    except NameError:
        return Path(__file__).resolve().parent

APP_DIR = _resolve_app_dir()
TMP_DIR = APP_DIR / ".tmp"
CONFIG_DIR = APP_DIR / "config"
LOG_DIR = APP_DIR / "logs"
BIN_DIR = APP_DIR / "bin"

TMP_DIR.mkdir(parents=True, exist_ok=True)
CONFIG_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)
BIN_DIR.mkdir(parents=True, exist_ok=True)

from PySide6.QtCore import QEvent, QObject, QPointF, QRectF, QSizeF, Qt, QThread, QTimer, QUrl, Signal
from PySide6.QtGui import QColor, QFont, QImage, QKeyEvent, QMouseEvent, QNativeGestureEvent, QPainter, QPen, QPixmap, QPolygonF, QTransform, QWheelEvent
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QGraphicsVideoItem
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QGraphicsPixmapItem,
    QGraphicsScene,
    QGraphicsView,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

APP_NAME = "ClipTrim"
RULER_H = 30
MIN_TIMELINE_H = 100
MAX_TIMELINE_H = 300

# ---------------------------------------------------------------------------
# USER CONFIG
#
# These are intentionally compact and structured so this block can later map
# cleanly to an external config file without exposing internal implementation
# constants. Area zoom is the base multiplier; touchpad pinch layers its global
# modifier on top.
# ---------------------------------------------------------------------------
CONFIG = {
    "touchpad": {
        "pinch_multiplier": 1.5,
    },
    "timeline": {
        "zoom_multiplier": 2.0,
    },
    "player": {
        "zoom_multiplier": 2.0,
    },
}
# Color values use #RRGGBB. Opacity values are 0-255.
THEME = {
    "app": {
        "background": "#000000",
        "text": "#b8b8b8",
        "text_dim": "#747474",
    },
    "launcher": {
        "background": "#0b0b0b",
        "hover_background": "#111111",
        "border": "#303030",
        "hover_border": "#595959",
        "prompt": "#d0d0d0",
    },
    "timeline": {
        "handle_width": 12,
        "background_opacity": 188,
        "full_clip": {
            "background": "#181818",
            "opacity": 220,
        },
        "trim_range": {
            "background": "#292929",
            "opacity": 224,
        },
        "markers": {
            "line": "#b3b3b3",
            "text": "#adadad",
            "ribbon_opacity": 150,
        },
        "playhead": "#9fb9c9",
        "handle": "#e3e3e3",
        "volume_line": "#ff9c9c",
        "trimmed_darkening": 145,
        "thumbnail_darkening": 42,
    },
}

HANDLE_W = int(THEME["timeline"]["handle_width"])
SIDE_PAD = HANDLE_W * 2

APP_BACKGROUND = QColor(THEME["app"]["background"])
PRIMARY_TEXT = QColor(THEME["app"]["text"])
SECONDARY_TEXT = QColor(THEME["app"]["text_dim"])
TIMELINE_FULL_CLIP_BACKGROUND = QColor(THEME["timeline"]["full_clip"]["background"])
TIMELINE_FULL_CLIP_BACKGROUND.setAlpha(THEME["timeline"]["full_clip"]["opacity"])
TIMELINE_SELECTED_RANGE_BACKGROUND = QColor(THEME["timeline"]["trim_range"]["background"])
TIMELINE_SELECTED_RANGE_BACKGROUND.setAlpha(THEME["timeline"]["trim_range"]["opacity"])
TIMELINE_TRIMMED_AREA_OVERLAY = QColor(0, 0, 0, THEME["timeline"]["trimmed_darkening"])
TIMELINE_MARKER_LINE = QColor(THEME["timeline"]["markers"]["line"])
TIMELINE_MARKER_TEXT = QColor(THEME["timeline"]["markers"]["text"])
TIMELINE_PLAYHEAD = QColor(THEME["timeline"]["playhead"])
TIMELINE_TRIM_HANDLE = QColor(THEME["timeline"]["handle"])
TIMELINE_VOLUME_LINE = QColor(THEME["timeline"]["volume_line"])

SCRUB_CACHE_MAX_SIDE = 512
SCRUB_CACHE_MAX_FPS = 30.0
SCRUB_CACHE_MAX_FRAMES = 9000
SCRUB_RAM_MAX_BYTES = 48 * 1024 * 1024

MEDIA_PROBE_TIMEOUT_SECONDS = 30
THUMBNAIL_TIMEOUT_SECONDS = 12
KEYFRAME_PROBE_TIMEOUT_SECONDS = 15

TRIM_METADATA_STREAM = "ClipTrim.TrimState"
TRIM_METADATA_VERSION = 1

def log(message: str, level: str = "INFO"):
    stamp = time.strftime("%H:%M:%S")
    thread_name = threading.current_thread().name
    stream = sys.stderr if level in {"ERROR", "WARN"} else sys.stdout
    if stream is not None:
        print(f"[{stamp}] [{level}] [{thread_name}] {message}", file=stream, flush=True)


def log_exception(context: str, exc: BaseException):
    log(f"{context}: {type(exc).__name__}: {exc}", "ERROR")
    if sys.stderr is not None:
        traceback.print_exception(type(exc), exc, exc.__traceback__, file=sys.stderr)
        sys.stderr.flush()


def _unhandled_exception(exc_type, exc, tb):
    log(f"UNHANDLED EXCEPTION: {exc_type.__name__}: {exc}", "ERROR")
    if sys.stderr is not None:
        traceback.print_exception(exc_type, exc, tb, file=sys.stderr)
        sys.stderr.flush()


def _thread_unhandled_exception(args):
    _unhandled_exception(args.exc_type, args.exc_value, args.exc_traceback)


sys.excepthook = _unhandled_exception
threading.excepthook = _thread_unhandled_exception

if sys.stderr is not None:
    try:
        faulthandler.enable(file=sys.stderr, all_threads=True)
        log("Python faulthandler enabled for fatal/native crash diagnostics", "DEBUG")
    except Exception as exc:
        log_exception("Could not enable Python faulthandler", exc)


def remove_tree(path: Path, context: str):
    try:
        shutil.rmtree(path)
        log(f"Removed {context}: {path}", "DEBUG")
    except FileNotFoundError:
        return
    except Exception as exc:
        log_exception(f"Failed to remove {context} {path}", exc)


def remove_file(path: Path, context: str):
    try:
        path.unlink(missing_ok=True)
    except Exception as exc:
        log_exception(f"Failed to remove {context} {path}", exc)


def _run_directory_pid(path: Path) -> int | None:
    """Return the owner PID encoded in a ``run-<pid>-<id>`` directory."""
    parts = path.name.split("-", 2)
    if len(parts) != 3 or parts[0] != "run" or not parts[1].isdigit():
        return None
    try:
        pid = int(parts[1])
    except (ValueError, OverflowError):
        return None
    maximum_pid = 0xFFFFFFFF if os.name == "nt" else 0x7FFFFFFF
    return pid if 0 < pid <= maximum_pid else None


def _is_process_running(pid: int) -> bool:
    """Conservatively report whether *pid* still identifies a live process."""
    if pid <= 0:
        return False
    if pid == os.getpid():
        return True

    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        synchronize = 0x00100000
        error_access_denied = 5
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.WaitForSingleObject.argtypes = (wintypes.HANDLE, wintypes.DWORD)
        kernel32.WaitForSingleObject.restype = wintypes.DWORD
        kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
        kernel32.CloseHandle.restype = wintypes.BOOL

        handle = kernel32.OpenProcess(synchronize, False, pid)
        if not handle:
            return ctypes.get_last_error() == error_access_denied
        try:
            # WAIT_OBJECT_0 (zero) is the only definitive evidence that the
            # process ended. Keep the directory on timeout or API failure.
            return kernel32.WaitForSingleObject(handle, 0) != 0
        finally:
            kernel32.CloseHandle(handle)

    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _remove_stale_temp_children(root: Path):
    """Remove abandoned temp data without touching another live app instance."""
    for child in root.iterdir():
        owner_pid = _run_directory_pid(child) if child.is_dir() else None
        if owner_pid is None:
            log(f"Keeping unrecognized temp entry: {child}", "DEBUG")
            continue
        if _is_process_running(owner_pid):
            log(f"Keeping temp directory owned by live process {owner_pid}: {child}", "DEBUG")
            continue
        remove_tree(child, "stale app temp directory")


def _prepare_temp_run_dir() -> Path:
    try:
        log(f"Preparing app temp root: {TMP_DIR}")
        TMP_DIR.mkdir(parents=True, exist_ok=True)
        _remove_stale_temp_children(TMP_DIR)
        run_dir = TMP_DIR / f"run-{os.getpid()}-{uuid.uuid4().hex[:8]}"
        run_dir.mkdir(parents=True, exist_ok=True)
        log(f"App temp run directory: {run_dir}")
        return run_dir
    except Exception as exc:
        log_exception(f"Could not prepare app-local temp directory {TMP_DIR}", exc)
        raise RuntimeError(f"ClipTrim cannot use its temp directory: {TMP_DIR}") from exc


def _cleanup_temp_run_dir():
    log("Application exit cleanup: app temp run directory")
    remove_tree(TEMP_RUN_DIR, "current app temp run directory")


TEMP_RUN_DIR = _prepare_temp_run_dir()
tempfile.tempdir = str(TEMP_RUN_DIR)
os.environ["TMP"] = str(TEMP_RUN_DIR)
os.environ["TEMP"] = str(TEMP_RUN_DIR)
os.environ["TMPDIR"] = str(TEMP_RUN_DIR)
SCRUB_RUN_DIR = TEMP_RUN_DIR / "scrub"
SCRUB_RUN_DIR.mkdir(parents=True, exist_ok=True)
EXPORT_TEMP_DIR = TEMP_RUN_DIR / "exports"
atexit.register(_cleanup_temp_run_dir)


def find_binary(name: str) -> str | None:
    local = BIN_DIR / (name + (".exe" if os.name == "nt" else ""))
    if local.exists():
        return str(local)
    return shutil.which(name)


FFMPEG = find_binary("ffmpeg")
FFPROBE = find_binary("ffprobe")


def run_hidden(args: list[str], **kwargs):
    kwargs.setdefault("stdin", subprocess.DEVNULL)
    if os.name == "nt":
        kwargs.setdefault("creationflags", subprocess.CREATE_NO_WINDOW)
    return subprocess.run(args, **kwargs)


def popen_hidden(args: list[str], **kwargs):
    kwargs.setdefault("stdin", subprocess.DEVNULL)
    if os.name == "nt":
        flags = subprocess.CREATE_NO_WINDOW
        flags |= getattr(subprocess, "BELOW_NORMAL_PRIORITY_CLASS", 0)
        kwargs.setdefault("creationflags", flags)
    return subprocess.Popen(args, **kwargs)


def parse_rate(value: str | None, default: float = 30.0) -> float:
    if not value or value in {"0/0", "N/A"}:
        return default
    try:
        return float(Fraction(value))
    except Exception as exc:
        log_exception(f"Could not parse frame rate {value!r}; falling back to {default}", exc)
        return default


@dataclass
class MediaInfo:
    path: str
    duration: float
    video_duration: float
    fps: float
    width: int
    height: int
    video_codec: str
    audio_codec: str | None
    pix_fmt: str | None
    color_primaries: str | None
    color_transfer: str | None
    color_space: str | None

    @property
    def frame_duration(self) -> float:
        return 1.0 / max(self.fps, 1e-6)

    @property
    def frame_count(self) -> int:
        return max(1, int(math.ceil(self.video_duration * self.fps - 1e-6)))

    
def _trim_metadata_path(path: str) -> str:
    return f"{path}:{TRIM_METADATA_STREAM}"


def _frame_index_for_time(t: float, info: MediaInfo) -> int:
    return max(0, min(info.frame_count - 1, int(round(t * max(info.fps, 1e-6)))))


def _out_frame_index_for_boundary(out_time: float, info: MediaInfo) -> int:
    fps = max(info.fps, 1e-6)
    frame = int(math.floor(max(0.0, out_time) * fps - 1e-6))
    return max(0, min(info.frame_count - 1, frame))


def read_embedded_trim_frames(path: str, info: MediaInfo) -> tuple[int, int] | None:
    """Read persisted trim frame indexes. Missing fields mean full-clip defaults."""
    if os.name != "nt":
        return None

    stream_path = _trim_metadata_path(path)
    try:
        with open(stream_path, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except FileNotFoundError:
        return None
    except Exception as exc:
        log_exception(f"Could not read ClipTrim metadata from {path}; using full clip", exc)
        return (0, info.frame_count - 1)

    if not isinstance(raw, dict):
        log(f"Invalid ClipTrim metadata in {path}: root is not an object; using full clip", "WARN")
        return (0, info.frame_count - 1)

    version = raw.get("version", TRIM_METADATA_VERSION)
    if version != TRIM_METADATA_VERSION:
        log(
            f"Unsupported ClipTrim metadata version {version!r} in {path}; using full clip",
            "WARN",
        )
        return (0, info.frame_count - 1)

    last = info.frame_count - 1
    invalid = False

    in_raw = raw.get("in_frame", 0)
    if isinstance(in_raw, bool) or not isinstance(in_raw, int) or not (0 <= in_raw <= last):
        log(f"Invalid ClipTrim in_frame={in_raw!r} in {path}; falling back to frame 0", "WARN")
        in_frame = 0
        invalid = True
    else:
        in_frame = in_raw

    out_raw = raw.get("out_frame", last)
    if isinstance(out_raw, bool) or not isinstance(out_raw, int) or not (0 <= out_raw <= last):
        log(f"Invalid ClipTrim out_frame={out_raw!r} in {path}; falling back to frame {last}", "WARN")
        out_frame = last
        invalid = True
    else:
        out_frame = out_raw

    if out_frame < in_frame:
        log(
            f"Invalid ClipTrim trim range in {path}: in={in_frame}, out={out_frame}; using full clip",
            "WARN",
        )
        return (0, last)

    if invalid:
        log(f"ClipTrim metadata for {path} contained invalid values but was safely recovered", "WARN")
    else:
        log(f"Loaded ClipTrim metadata: in_frame={in_frame}, out_frame={out_frame}", "DEBUG")
    return (in_frame, out_frame)


def write_embedded_trim_frames(path: str, info: MediaInfo, in_time: float, out_time: float) -> bool:
    """Persist current trim points immediately without modifying the media stream."""
    if os.name != "nt":
        log("Persistent trim metadata requires Windows/NTFS; keeping trim state in memory only", "WARN")
        return False

    last = info.frame_count - 1
    in_frame = _frame_index_for_time(in_time, info)
    out_frame = _out_frame_index_for_boundary(out_time, info)
    if out_frame < in_frame:
        log(
            f"Refusing to save invalid trim metadata for {path}: in={in_frame}, out={out_frame}",
            "ERROR",
        )
        return False

    stream_path = _trim_metadata_path(path)
    payload: dict[str, int] = {"version": TRIM_METADATA_VERSION}
    if in_frame != 0:
        payload["in_frame"] = in_frame
    if out_frame != last:
        payload["out_frame"] = out_frame

    try:
        if len(payload) == 1:
            try:
                os.remove(stream_path)
                log(f"Removed ClipTrim trim metadata because clip is at full-range defaults: {path}", "DEBUG")
            except FileNotFoundError:
                log(f"ClipTrim trim metadata already absent for full-range clip: {path}", "DEBUG")
            return True

        encoded = json.dumps(payload, separators=(",", ":"), sort_keys=True)
        with open(stream_path, "w", encoding="utf-8", newline="") as f:
            f.write(encoded)
            f.flush()
        log(f"Saved ClipTrim metadata immediately: {payload} -> {path}", "DEBUG")
        return True
    except Exception as exc:
        log_exception(
            f"Failed to save ClipTrim metadata for {path}; filesystem may not support NTFS alternate streams",
            exc,
        )
        return False


def trim_frames_to_times(info: MediaInfo, in_frame: int, out_frame: int) -> tuple[float, float]:
    fps = max(info.fps, 1e-6)
    in_time = in_frame / fps

    out_time = min(info.video_duration, (out_frame + 1) / fps)
    if out_time <= in_time:
        out_time = min(info.video_duration, in_time + info.frame_duration)
    return in_time, out_time


def probe_media(path: str) -> MediaInfo:
    if not FFPROBE:
        raise RuntimeError("ffprobe was not found. Install FFmpeg and restart ClipTrim.")
    try:
        cp = run_hidden(
            [FFPROBE, "-v", "error", "-show_streams", "-show_format", "-of", "json", path],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=MEDIA_PROBE_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            f"ffprobe did not finish within {MEDIA_PROBE_TIMEOUT_SECONDS} seconds."
        ) from exc
    except OSError as exc:
        raise RuntimeError(f"ffprobe could not be started: {exc}") from exc
    if cp.returncode:
        raise RuntimeError(cp.stderr.strip() or "ffprobe failed")
    data = json.loads(cp.stdout)
    video = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), None)
    audio = next((s for s in data.get("streams", []) if s.get("codec_type") == "audio"), None)
    if not video:
        raise RuntimeError("No video stream found.")
    format_duration = float(data.get("format", {}).get("duration") or 0)
    video_duration = float(video.get("duration") or 0)
    if video_duration <= 0:
        tag_duration = (video.get("tags") or {}).get("DURATION")
        if tag_duration:
            try:
                parts = str(tag_duration).split(":")
                if len(parts) == 3:
                    video_duration = float(parts[0]) * 3600.0 + float(parts[1]) * 60.0 + float(parts[2])
            except Exception as exc:
                log_exception(f"Could not parse video-stream DURATION tag {tag_duration!r}", exc)
                video_duration = 0.0

    fps = parse_rate(video.get("avg_frame_rate") or video.get("r_frame_rate"))
    duration = format_duration or video_duration
    if video_duration <= 0:
        video_duration = duration
    if duration <= 0:
        nb_frames = int(video.get("nb_frames") or 0)
        if nb_frames:
            duration = nb_frames / fps
            video_duration = duration
    if duration <= 0:
        raise RuntimeError("Could not determine clip duration.")
    if video_duration <= 0:
        video_duration = duration

    return MediaInfo(
        path=path,
        duration=duration,
        video_duration=min(duration, video_duration),
        fps=fps,
        width=int(video.get("width") or 1),
        height=int(video.get("height") or 1),
        video_codec=(video.get("codec_name") or "unknown").lower(),
        audio_codec=(audio.get("codec_name") or "").lower() if audio else None,
        pix_fmt=video.get("pix_fmt"),
        color_primaries=video.get("color_primaries"),
        color_transfer=video.get("color_transfer"),
        color_space=video.get("color_space"),
    )


def frame_snap(t: float, info: MediaInfo) -> float:
    frame = round(max(0.0, min(info.duration, t)) * info.fps)
    return max(0.0, min(info.duration, frame / info.fps))


def snap_out_boundary(t: float, info: MediaInfo) -> float:
    """Snap an exclusive Out boundary without dropping a partial final frame."""
    maximum = max(0.0, min(info.duration, info.video_duration))
    boundary = max(0.0, min(maximum, t))
    out_frame = _out_frame_index_for_boundary(boundary, info)
    return min(maximum, (out_frame + 1) * info.frame_duration)


def last_frame_start_before(boundary: float, info: MediaInfo) -> float:
    """Return the start time of the final actual frame before a boundary."""
    fps = max(info.fps, 1e-6)
    boundary = max(0.0, min(boundary, info.video_duration))
    frame_index = int(math.floor(boundary * fps - 1e-6))
    frame_index = max(0, min(info.frame_count - 1, frame_index))
    return frame_index / fps


def is_keyframe_at(path: str, t: float, fps: float) -> bool:
    if not FFPROBE:
        return False
    if t <= 0.5 / fps:
        return True
    start = max(0.0, t - max(0.5, 8.0 / fps))
    length = max(1.0, 16.0 / fps)
    try:
        cp = run_hidden(
            [
                FFPROBE,
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-skip_frame",
                "nokey",
                "-read_intervals",
                f"{start:.9f}%+{length:.9f}",
                "-show_entries",
                "frame=best_effort_timestamp_time,pts_time",
                "-of",
                "json",
                path,
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=KEYFRAME_PROBE_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        log_exception(f"Keyframe probe failed for {path} at {t:.6f}s", exc)
        return False
    if cp.returncode:
        return False
    try:
        frames = json.loads(cp.stdout).get("frames", [])
        values = []
        for f in frames:
            raw = f.get("best_effort_timestamp_time") or f.get("pts_time")
            if raw is not None:
                values.append(float(raw))
        tolerance = max(0.00075, 0.55 / fps)
        return any(abs(v - t) <= tolerance for v in values)
    except Exception as exc:
        log_exception(f"Failed to parse keyframe probe output for {path} at {t:.6f}s", exc)
        return False


def make_thumbnail(path: str, t: float) -> QImage:
    if not FFMPEG:
        return QImage()
    try:
        cp = run_hidden(
            [
                FFMPEG,
                "-v",
                "error",
                "-ss",
                f"{t:.9f}",
                "-i",
                path,
                "-map",
                "0:v:0",
                "-frames:v",
                "1",
                "-vf",
                "scale=640:-2",
                "-f",
                "image2pipe",
                "-vcodec",
                "png",
                "-",
            ],
            capture_output=True,
            timeout=THUMBNAIL_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        log_exception(f"Thumbnail extraction failed for {path} at {t:.6f}s", exc)
        return QImage()
    img = QImage()
    if cp.returncode == 0:
        img.loadFromData(cp.stdout, "PNG")
    return img


def finalize_export_file(temp_output: Path, output_path: Path):
    """Install a completed export without exposing a partially copied destination."""
    try:
        os.replace(temp_output, output_path)
        return
    except OSError as exc:
        log(
            f"Could not atomically move completed export to {output_path}: {exc}; "
            "copying through a destination-side staging file",
            "WARN",
        )

    staged_output = output_path.with_name(f".{output_path.name}.{uuid.uuid4().hex}.part")
    try:
        shutil.copy2(temp_output, staged_output)
        os.replace(staged_output, output_path)
        remove_file(temp_output, "copied export intermediate")
    finally:
        remove_file(staged_output, "incomplete destination export")


class ExportWorker(QObject):
    finished = Signal(str, str)
    failed = Signal(str)

    def __init__(self, info: MediaInfo, start: float, end: float, output: str):
        super().__init__()
        self.info = info
        self.start = start
        self.end = end
        self.output = output

    def run(self):
        temp_output: Path | None = None
        try:
            if not FFMPEG or not FFPROBE:
                raise RuntimeError("FFmpeg/ffprobe not found.")

            source_path = Path(self.info.path).resolve()
            output_path = Path(self.output).resolve()
            if os.path.normcase(str(source_path)) == os.path.normcase(str(output_path)):
                raise RuntimeError("Export output cannot overwrite the source clip.")

            EXPORT_TEMP_DIR.mkdir(parents=True, exist_ok=True)
            temp_output = EXPORT_TEMP_DIR / f"export-{uuid.uuid4().hex}.mp4"

            duration = max(self.info.frame_duration, self.end - self.start)
            video_copyable = self.info.video_codec == "h264" and self.info.pix_fmt in {"yuv420p", "yuvj420p"}
            audio_copyable = self.info.audio_codec in {None, "aac"}
            start_is_key = is_keyframe_at(self.info.path, self.start, self.info.fps)
            copy_compatible_streams = video_copyable and audio_copyable and start_is_key

            def transcode_args() -> list[str]:
                args = [
                    FFMPEG,
                    "-hide_banner",
                    "-y",
                    "-ss",
                    f"{self.start:.9f}",
                    "-i",
                    self.info.path,
                    "-t",
                    f"{duration:.9f}",
                    "-map",
                    "0:v:0",
                    "-map",
                    "0:a:0?",
                    "-c:v",
                    "libx264",
                    "-preset",
                    "slow",
                    "-crf",
                    "10",
                    "-profile:v",
                    "high",
                    "-pix_fmt",
                    "yuv420p",
                    "-tag:v",
                    "avc1",
                    "-fps_mode",
                    "passthrough",
                ]
                for key, value in (
                    ("-color_primaries", self.info.color_primaries),
                    ("-color_trc", self.info.color_transfer),
                    ("-colorspace", self.info.color_space),
                ):
                    if value and value not in {"unknown", "reserved"}:
                        args += [key, value]
                if self.info.audio_codec:
                    args += ["-c:a", "aac", "-profile:a", "aac_low", "-b:a", "320k"]
                args += [
                    "-map_metadata",
                    "0",
                    "-avoid_negative_ts",
                    "make_zero",
                    "-movflags",
                    "+faststart",
                    str(temp_output),
                ]
                return args

            if copy_compatible_streams:
                args = [
                    FFMPEG,
                    "-hide_banner",
                    "-y",
                    "-ss",
                    f"{self.start:.9f}",
                    "-i",
                    self.info.path,
                    "-t",
                    f"{duration:.9f}",
                    "-map",
                    "0:v:0",
                    "-map",
                    "0:a:0?",
                    "-c",
                    "copy",
                    "-tag:v",
                    "avc1",
                    "-map_metadata",
                    "0",
                    "-avoid_negative_ts",
                    "make_zero",
                    "-movflags",
                    "+faststart",
                    str(temp_output),
                ]
                mode_parts = ["video copied", "audio copied" if self.info.audio_codec else "no audio"]
            else:
                args = transcode_args()
                mode_parts = ["video -> H.264 High (CRF 10)", "audio -> AAC-LC 320 kb/s" if self.info.audio_codec else "no audio"]

            cp = run_hidden(args, capture_output=True, text=True, encoding="utf-8", errors="replace")
            if cp.returncode:
                if not copy_compatible_streams:
                    raise RuntimeError(cp.stderr.strip()[-2400:] or "FFmpeg export failed.")
                log("Compatible stream-copy export failed; retrying with H.264/AAC transcode", "WARN")
                args = transcode_args()
                cp = run_hidden(args, capture_output=True, text=True, encoding="utf-8", errors="replace")
                if cp.returncode:
                    raise RuntimeError(cp.stderr.strip()[-2400:] or "FFmpeg export failed.")
                mode_parts = ["video -> H.264 High (CRF 10)", "audio -> AAC-LC 320 kb/s" if self.info.audio_codec else "no audio"]

            finalize_export_file(temp_output, output_path)
            self.finished.emit(self.output, ", ".join(mode_parts))
        except Exception as exc:
            log_exception("Export worker failed", exc)
            self.failed.emit(str(exc))
        finally:
            if temp_output is not None:
                remove_file(temp_output, "export intermediate")


class ScrubCacheWorker(QObject):
    done = Signal(bool, str, int, str)

    def __init__(self, info: MediaInfo, cache_dir: Path, cache_fps: float, generation: int):
        super().__init__()
        self.info = info
        self.cache_dir = cache_dir
        self.cache_fps = cache_fps
        self.generation = generation
        self._cancelled = False
        self._process: subprocess.Popen | None = None

    def cancel(self):
        self._cancelled = True
        process = self._process
        if not process or process.poll() is not None:
            log(f"Scrub cache worker generation {self.generation}: cancel requested with no live FFmpeg process")
            return
        log(f"Scrub cache worker generation {self.generation}: terminating FFmpeg pid={process.pid}", "WARN")
        try:
            process.terminate()
            try:
                process.wait(timeout=0.75)
            except subprocess.TimeoutExpired as exc:
                log_exception("FFmpeg scrub-cache process did not terminate promptly; killing it", exc)
                process.kill()
                process.wait(timeout=1.0)
        except Exception as exc:
            log_exception("Failed to stop FFmpeg scrub-cache process cleanly", exc)
            if process.poll() is None:
                try:
                    process.kill()
                    log(f"Force-killed scrub cache FFmpeg pid={process.pid}", "WARN")
                except Exception as kill_exc:
                    log_exception("Failed to force-kill FFmpeg scrub-cache process", kill_exc)

    def run(self):
        log(
            f"Scrub cache worker generation {self.generation} started: "
            f"source={self.info.path!r}, fps={self.cache_fps:.4f}, dir={self.cache_dir}"
        )
        if not FFMPEG:
            log("Scrub cache worker cannot start because ffmpeg was not found", "ERROR")
            self.done.emit(False, "ffmpeg not found", self.generation, str(self.cache_dir))
            return
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            vf = (
                f"fps={self.cache_fps:.8f},"
                f"scale=w='min({SCRUB_CACHE_MAX_SIDE},iw)':"
                f"h='min({SCRUB_CACHE_MAX_SIDE},ih)':"
                "force_original_aspect_ratio=decrease:force_divisible_by=2:flags=fast_bilinear"
            )
            args = [
                FFMPEG,
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-threads",
                "2",
                "-filter_threads",
                "1",
                "-i",
                self.info.path,
                "-map",
                "0:v:0",
                "-an",
                "-vf",
                vf,
                "-q:v",
                "8",
                "-frames:v",
                str(SCRUB_CACHE_MAX_FRAMES),
                "-start_number",
                "0",
                str(self.cache_dir / "frame_%08d.jpg"),
            ]
            log(f"Starting scrub-cache FFmpeg: {' '.join(args)}", "DEBUG")
            self._process = popen_hidden(
                args,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            _, stderr = self._process.communicate()
            rc = self._process.returncode
            pid = self._process.pid
            self._process = None
            frame_count = 0
            try:
                frame_count = sum(1 for _ in self.cache_dir.glob("frame_*.jpg"))
            except Exception as exc:
                log_exception("Could not count generated scrub-cache frames", exc)
            log(
                f"Scrub-cache FFmpeg exited: pid={pid}, rc={rc}, cancelled={self._cancelled}, "
                f"frames={frame_count}"
            )
            if self._cancelled:
                self.done.emit(False, "", self.generation, str(self.cache_dir))
            elif rc:
                self.done.emit(
                    False,
                    (stderr or "scrub cache generation failed").strip()[-1200:],
                    self.generation,
                    str(self.cache_dir),
                )
            else:
                self.done.emit(True, "", self.generation, str(self.cache_dir))
        except Exception as exc:
            self._process = None
            log_exception(f"Scrub cache worker generation {self.generation} failed", exc)
            self.done.emit(
                False,
                "cancelled" if self._cancelled else str(exc),
                self.generation,
                str(self.cache_dir),
            )


class VideoCanvas(QGraphicsView):
    """Video preview transformed as one graphics item, never resized as a video output."""
    PIXEL_ZOOM_GAIN = 0.0072
    ANGLE_ZOOM_GAIN = 0.0018
    NATIVE_ZOOM_GAIN = 1.8
    MAX_ZOOM = 24.0

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setFrameStyle(0)
        self.setStyleSheet(f"QGraphicsView {{ background: {THEME['app']['background']}; border: 0; }}")
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.setInteractive(False)
        self.setOptimizationFlag(QGraphicsView.OptimizationFlag.DontSavePainterState, True)

        self.scene_obj = QGraphicsScene(self)
        self.setScene(self.scene_obj)
        self.video_item = QGraphicsVideoItem()
        self.video_item.setAspectRatioMode(Qt.AspectRatioMode.IgnoreAspectRatio)
        self.scene_obj.addItem(self.video_item)
        self.scrub_item = QGraphicsPixmapItem()
        self.scrub_item.setTransformationMode(Qt.TransformationMode.SmoothTransformation)
        self.scrub_item.setZValue(10)
        self.scrub_item.setVisible(False)
        self.scene_obj.addItem(self.scrub_item)

        self.source_w = 16
        self.source_h = 9
        self.has_media = False
        self.zoom = 1.0
        self.pan = QPointF(0, 0)
        self.dragging = False
        self.last_mouse = QPointF()

        self._pending_log_zoom = 0.0
        self._pending_zoom_pos = QPointF()
        self._zoom_timer = QTimer(self)
        self._zoom_timer.setInterval(8)
        self._zoom_timer.timeout.connect(self._flush_zoom)
        self._native_zoom_active = False
        self._native_zoom_until = 0.0

    def set_source_size(self, width: int, height: int):
        self.source_w = max(1, int(width))
        self.source_h = max(1, int(height))
        self.has_media = True
        self.video_item.setSize(QSizeF(self.source_w, self.source_h))
        self.reset_view()

    def clear_media(self):
        self.has_media = False
        self.video_item.setSize(QSizeF(1, 1))
        self.video_item.setTransform(QTransform())
        self.video_item.setPos(0, 0)
        self.scrub_item.setVisible(False)
        self.scrub_item.setPixmap(QPixmap())
        self.zoom = 1.0
        self.pan = QPointF(0, 0)
        self.viewport().update()

    def _base_scale(self) -> float:
        if not self.has_media:
            return 1.0
        vw = max(1.0, float(self.viewport().width()))
        vh = max(1.0, float(self.viewport().height()))
        return max(1e-6, min(vw / self.source_w, vh / self.source_h))

    def _layout_video(self):
        if not self.has_media:
            return
        vw = max(1.0, float(self.viewport().width()))
        vh = max(1.0, float(self.viewport().height()))
        scale = self._base_scale() * self.zoom
        w = self.source_w * scale
        h = self.source_h * scale
        center = QPointF(vw / 2.0 + self.pan.x(), vh / 2.0 + self.pan.y())

        self.scene_obj.setSceneRect(0.0, 0.0, vw, vh)
        transform = QTransform()
        transform.scale(scale, scale)
        self.video_item.setTransform(transform)
        self.video_item.setPos(center.x() - w / 2.0, center.y() - h / 2.0)

        if self.scrub_item.isVisible() and not self.scrub_item.pixmap().isNull():
            pix = self.scrub_item.pixmap()
            scrub_transform = QTransform()
            scrub_transform.scale(
                scale * self.source_w / max(1, pix.width()),
                scale * self.source_h / max(1, pix.height()),
            )
            self.scrub_item.setTransform(scrub_transform)
            self.scrub_item.setPos(center.x() - w / 2.0, center.y() - h / 2.0)

        self.viewport().update()

    def set_scrub_frame(self, image: QImage):
        if image.isNull():
            return
        self.scrub_item.setPixmap(QPixmap.fromImage(image))
        self.scrub_item.setVisible(True)
        self._layout_video()

    def clear_scrub_frame(self):
        if not self.scrub_item.isVisible() and self.scrub_item.pixmap().isNull():
            return
        self.scrub_item.setVisible(False)
        self.scrub_item.setPixmap(QPixmap())
        self.viewport().update()

    def reset_view(self):
        if not self.has_media:
            return
        self._pending_log_zoom = 0.0
        self.zoom = 1.0
        self.pan = QPointF(0, 0)
        self._layout_video()

    def pan_by_pixels(self, delta: QPointF):
        if not self.has_media:
            return

        self.pan += QPointF(delta.x(), delta.y())
        self._layout_video()

    def _queue_zoom(self, log_factor: float, pos: QPointF):
        if not self.has_media or not math.isfinite(log_factor) or abs(log_factor) < 1e-9:
            return
        self._pending_log_zoom += max(-0.9, min(0.9, log_factor))
        self._pending_zoom_pos = QPointF(pos)
        if not self._zoom_timer.isActive():
            self._zoom_timer.start()

    def _flush_zoom(self):
        if abs(self._pending_log_zoom) < 1e-9:
            self._zoom_timer.stop()
            return
        log_factor = self._pending_log_zoom
        pos = QPointF(self._pending_zoom_pos)
        self._pending_log_zoom = 0.0
        self.zoom_at(math.exp(log_factor), pos)

    def zoom_at(self, factor: float, pos: QPointF):
        if not self.has_media or factor <= 0 or not math.isfinite(factor):
            return
        old_zoom = self.zoom
        new_zoom = max(1.0, min(self.MAX_ZOOM, old_zoom * factor))
        if abs(new_zoom - old_zoom) < 1e-8:
            return

        ratio = new_zoom / old_zoom
        center = QPointF(self.viewport().width() / 2.0, self.viewport().height() / 2.0)
        self.pan = (self.pan + (center - pos)) * ratio - (center - pos)
        self.zoom = new_zoom
        self._layout_video()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._layout_video()

    def _log_zoom_source_once(self, source: str, multiplier: float):
        if getattr(self, "_last_logged_zoom_source", None) == source:
            return
        self._last_logged_zoom_source = source
        log(f"Player zoom input: {source}; effective multiplier={multiplier:g}x")

    def wheelEvent(self, e: QWheelEvent):
        mods = e.modifiers()
        pixel = e.pixelDelta()
        angle = e.angleDelta()

        if mods & (Qt.KeyboardModifier.AltModifier | Qt.KeyboardModifier.ControlModifier):

            if (
                mods & Qt.KeyboardModifier.ControlModifier
                and (self._native_zoom_active or time.monotonic() < self._native_zoom_until)
            ):
                e.accept()
                return

            player_zoom = float(CONFIG["player"]["zoom_multiplier"])
            if mods & Qt.KeyboardModifier.AltModifier:
                multiplier = player_zoom
                self._log_zoom_source_once("Alt+scroll", multiplier)
            else:
                multiplier = player_zoom * float(CONFIG["touchpad"]["pinch_multiplier"])
                device = e.device()
                device_type = device.type() if device is not None else None
                device_name = getattr(device_type, "name", str(device_type))
                self._log_zoom_source_once(
                    f"Ctrl+wheel / synthesized pinch ({device_name})", multiplier
                )

            if not pixel.isNull():
                raw = pixel.y() if pixel.y() != 0 else pixel.x()
                log_factor = raw * self.PIXEL_ZOOM_GAIN * multiplier
            else:
                raw = angle.y() if angle.y() != 0 else angle.x()
                log_factor = raw * self.ANGLE_ZOOM_GAIN * multiplier
            self._queue_zoom(log_factor, e.position())
        else:
            if not pixel.isNull():
                dx = float(pixel.x())
                dy = float(pixel.y())
            else:
                dx = float(angle.x()) / 3.0
                dy = float(angle.y()) / 3.0
            self.pan_by_pixels(QPointF(dx, dy))
        e.accept()

    def event(self, e):
        if e.type() == QEvent.Type.NativeGesture and isinstance(e, QNativeGestureEvent):
            kind = e.gestureType()
            if kind == Qt.NativeGestureType.BeginNativeGesture:
                self._native_zoom_active = True
            elif kind == Qt.NativeGestureType.EndNativeGesture:
                self._native_zoom_active = False
                self._native_zoom_until = time.monotonic() + 0.14
            elif kind == Qt.NativeGestureType.ZoomNativeGesture:
                self._native_zoom_active = True
                self._native_zoom_until = time.monotonic() + 0.14
                value = max(-0.95, float(e.value()))
                multiplier = (
                    float(CONFIG["player"]["zoom_multiplier"])
                    * float(CONFIG["touchpad"]["pinch_multiplier"])
                )
                self._log_zoom_source_once("native touchpad pinch", multiplier)
                self._queue_zoom(
                    math.log1p(value) * self.NATIVE_ZOOM_GAIN * multiplier,
                    e.position(),
                )
                e.accept()
                return True

        return super().event(e)

    def mousePressEvent(self, e: QMouseEvent):
        if e.button() == Qt.MouseButton.LeftButton:
            self.dragging = True
            self.last_mouse = e.position()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            e.accept()
            return
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e: QMouseEvent):
        if self.dragging:
            self.pan_by_pixels(e.position() - self.last_mouse)
            self.last_mouse = e.position()
            e.accept()
            return
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e: QMouseEvent):
        if e.button() == Qt.MouseButton.LeftButton:
            self.dragging = False
            self.unsetCursor()
            e.accept()
            return
        super().mouseReleaseEvent(e)

    def mouseDoubleClickEvent(self, e: QMouseEvent):
        if e.button() == Qt.MouseButton.LeftButton:
            self.reset_view()
            e.accept()
            return
        super().mouseDoubleClickEvent(e)


class Timeline(QWidget):
    seekRequested = Signal(float)
    scrubStarted = Signal(float)
    scrubMoved = Signal(float)
    scrubEnded = Signal(float)
    inChanged = Signal(float, bool)
    outChanged = Signal(float, bool)
    resizeRequested = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAutoFillBackground(False)
        self.info: MediaInfo | None = None
        self.in_time = 0.0
        self.out_time = 1.0
        self.playhead = 0.0
        self.volume = 100
        self.muted = False
        self.pps = 80.0
        self.scroll_px = 0.0
        self.thumbnail = QImage()
        self.drag_mode: str | None = None
        self.drag_offset = 0.0
        self.resize_start_y = 0.0
        self.resize_start_h = 0
        self._last_width = max(1, self.width())
        self._last_native_zoom = 0.0
        self._manual_view_until = 0.0

    @property
    def track_top(self):
        return 0

    @property
    def half_handle(self) -> float:
        return HANDLE_W / 2.0

    @property
    def frame_origin_x(self) -> float:
        return SIDE_PAD + self.half_handle

    def full_last_frame_index(self) -> int:
        if not self.info:
            return 0
        return max(0, self.info.frame_count - 1)

    def full_last_frame_time(self) -> float:
        if not self.info:
            return 0.0
        return self.full_last_frame_index() / max(self.info.fps, 1e-6)

    def last_frame_before(self, boundary: float) -> float:
        """Return the timestamp of the final actual video frame before boundary."""
        if not self.info:
            return 0.0
        return last_frame_start_before(boundary, self.info)

    def fit_pps_for_width(self, width: int | None = None) -> float:
        if not self.info:
            return 1.0
        w = self.width() if width is None else width
        available = max(1.0, float(w) - 2.0 * SIDE_PAD - HANDLE_W)

        visual_span = max(self.full_last_frame_time(), self.info.frame_duration)
        return available / visual_span

    def set_media(self, info: MediaInfo, in_time=0.0, out_time=None):
        self.info = info
        self.in_time = min(frame_snap(in_time, info), self.full_last_frame_time())
        self.out_time = snap_out_boundary(
            out_time if out_time is not None else info.video_duration,
            info,
        )
        if self.out_time <= self.in_time:
            self.out_time = min(info.video_duration, self.in_time + info.frame_duration)
        self.playhead = self.in_time
        self.pps = self.fit_pps_for_width()
        self.scroll_px = 0.0
        self.thumbnail = QImage()
        self._last_width = max(1, self.width())
        self.update()

    def set_thumbnail(self, img: QImage):
        self.thumbnail = img
        self.update()

    def playhead_bounds(self) -> tuple[float, float]:
        """Return the playable bounds of the selected In/Out range."""
        if not self.info:
            return 0.0, 0.0
        first = self.in_time
        last = self.last_frame_before(self.out_time)
        return first, max(first, last)

    def full_playhead_bounds(self) -> tuple[float, float]:
        """Return every valid source-frame position available to the cursor."""
        if not self.info:
            return 0.0, 0.0
        return 0.0, self.full_last_frame_time()

    def playhead_to_x(self, t: float) -> float:
        if not self.info:
            return self.frame_origin_x
        return self.time_to_x(self.clamp_playhead_time(t))

    def clamp_playhead_time(self, t: float) -> float:
        if not self.info:
            return 0.0
        first, last = self.full_playhead_bounds()
        return max(first, min(last, frame_snap(t, self.info)))

    def set_playhead(self, t: float):
        if not self.info:
            return
        self.playhead = self.clamp_playhead_time(t)
        if time.monotonic() >= self._manual_view_until:
            self.ensure_visible(self.playhead)
        self.update()

    def set_volume(self, volume: int, muted: bool):
        self.volume = max(0, min(100, volume))
        self.muted = muted
        self.update()

    def content_width(self):
        return self.full_last_frame_time() * self.pps if self.info else 0.0

    def max_scroll(self):
        visible_frame_width = max(1.0, self.width() - 2.0 * SIDE_PAD - HANDLE_W)
        return max(0.0, self.content_width() - visible_frame_width)

    def clamp_scroll(self):
        self.scroll_px = max(0.0, min(self.max_scroll(), self.scroll_px))

    def time_to_x(self, t: float) -> float:

        return self.frame_origin_x + t * self.pps - self.scroll_px

    def x_to_time(self, x: float) -> float:
        if not self.info:
            return 0.0
        return max(0.0, min(self.info.duration, (x - self.frame_origin_x + self.scroll_px) / self.pps))

    def in_handle_center_x(self) -> float:
        return self.time_to_x(self.in_time) - self.half_handle

    def out_handle_center_x(self) -> float:
        return self.time_to_x(self.playhead_bounds()[1]) + self.half_handle

    def ensure_visible(self, t: float):
        x = self.time_to_x(t)
        left = self.frame_origin_x
        right = self.width() - self.frame_origin_x
        if x < left:
            self.scroll_px -= left - x
            self.clamp_scroll()
        elif x > right:
            self.scroll_px += x - right
            self.clamp_scroll()

    def marker_frame_intervals(self) -> tuple[int, int]:
        """Return (large marker frames, small marker frames) for the current zoom."""
        if not self.info:
            return 300, 30
        nominal_fps = max(1, int(round(self.info.fps)))
        ppf = self.pps / max(self.info.fps, 1e-6)
        if ppf >= 12.0:
            return 5, 1
        if self.pps >= 70.0:
            small = 15 if nominal_fps >= 15 else max(1, nominal_fps // 2)
            return nominal_fps, small
        if self.pps >= 14.0:
            return nominal_fps * 5, nominal_fps
        return nominal_fps * 10, nominal_fps

    def snap_marker(self, t: float, large: bool, direction: int = 0, exclude_current: bool = False) -> float:
        if not self.info:
            return t
        big_frames, small_frames = self.marker_frame_intervals()
        interval = big_frames if large else small_frames
        current_frame = max(0.0, min(self.info.frame_count, t * self.info.fps))
        eps = 1e-7 if exclude_current else 0.0
        if direction < 0:
            idx = math.floor((current_frame - eps) / interval)
        elif direction > 0:
            idx = math.ceil((current_frame + eps) / interval)
        else:
            idx = round(current_frame / interval)
        frame = max(0, min(self.info.frame_count, idx * interval))
        return min(self.info.duration, frame / self.info.fps)

    def snap_drag_time(self, t: float, mods: Qt.KeyboardModifier) -> float:
        if not self.info:
            return t
        if mods & Qt.KeyboardModifier.ShiftModifier:
            return self.snap_marker(t, True)
        if mods & Qt.KeyboardModifier.ControlModifier:
            return self.snap_marker(t, False)
        return frame_snap(t, self.info)

    def format_tick_frame(self, frame_index: int) -> str:
        if not self.info:
            return "00:00"
        nominal_fps = max(1, int(round(self.info.fps)))
        total_seconds, frame = divmod(max(0, int(frame_index)), nominal_fps)
        minutes, seconds = divmod(total_seconds, 60)
        if frame == 0:
            return f"{minutes:02}:{seconds:02}"
        return f"{minutes:02}:{seconds:02};{frame:02}"

    def zoom_at(self, factor: float, x: float):
        if not self.info:
            return
        anchor_time = self.x_to_time(x)
        old = self.pps
        min_pps = self.fit_pps_for_width()
        max_pps = max(min_pps, 240.0, self.info.fps * 32.0)
        self.pps = max(min_pps, min(max_pps, self.pps * factor))
        if abs(self.pps - old) < 1e-7:
            return
        if self.pps <= min_pps * 1.000001:
            self.pps = min_pps
            self.scroll_px = 0.0
        else:
            self.scroll_px = self.frame_origin_x + anchor_time * self.pps - x
            self.clamp_scroll()
        self._manual_view_until = time.monotonic() + 0.22
        self.update()

    def resizeEvent(self, e):
        if self.info:
            old_fit = self.fit_pps_for_width(self._last_width)
            was_fit = self.pps <= old_fit * 1.001
            new_fit = self.fit_pps_for_width(self.width())
            if was_fit:
                self.pps = new_fit
                self.scroll_px = 0.0
            elif self.pps < new_fit:
                self.pps = new_fit
                self.scroll_px = 0.0
            else:
                self.clamp_scroll()
        self._last_width = max(1, self.width())
        super().resizeEvent(e)

    _TIMELINE_WHEEL_ZOOM_BASE_GAIN = 0.0018
    _TIMELINE_NATIVE_PINCH_BASE_GAIN = 1.8

    def _log_zoom_source_once(self, source: str, multiplier: float):
        if getattr(self, "_last_logged_zoom_source", None) == source:
            return
        self._last_logged_zoom_source = source
        log(f"Timeline zoom input: {source}; effective multiplier={multiplier:g}x")

    def wheelEvent(self, e: QWheelEvent):
        if not self.info:
            return

        pixel = e.pixelDelta()
        angle = e.angleDelta()
        mods = e.modifiers()

        if mods & (Qt.KeyboardModifier.AltModifier | Qt.KeyboardModifier.ControlModifier):
            if mods & Qt.KeyboardModifier.ControlModifier and time.monotonic() - self._last_native_zoom < 0.08:
                e.accept()
                return

            if not pixel.isNull():
                dy = float(pixel.y() or pixel.x())
            else:
                dy = float(angle.y() or angle.x()) / 4.0

            if mods & Qt.KeyboardModifier.AltModifier:
                multiplier = float(CONFIG["timeline"]["zoom_multiplier"])
                self._log_zoom_source_once("Alt+scroll", multiplier)
            else:
                multiplier = float(CONFIG["timeline"]["zoom_multiplier"] * CONFIG["touchpad"]["pinch_multiplier"])
                device = e.device()
                device_type = device.type() if device is not None else None
                device_name = getattr(device_type, "name", str(device_type))
                self._log_zoom_source_once(f"Ctrl+wheel / synthesized pinch ({device_name})", multiplier)

            log_factor = dy * self._TIMELINE_WHEEL_ZOOM_BASE_GAIN * multiplier
            self.zoom_at(math.exp(log_factor), e.position().x())
        else:
            if not pixel.isNull():
                delta = pixel.x() + pixel.y()
            else:
                delta = (angle.x() + angle.y()) / 2.0
            self.scroll_px -= delta
            self.clamp_scroll()
            self._manual_view_until = time.monotonic() + 0.22
            self.update()
        e.accept()

    def event(self, e):
        if e.type() == QEvent.Type.NativeGesture and isinstance(e, QNativeGestureEvent):
            if e.gestureType() == Qt.NativeGestureType.ZoomNativeGesture:
                self._last_native_zoom = time.monotonic()
                multiplier = float(CONFIG["timeline"]["zoom_multiplier"] * CONFIG["touchpad"]["pinch_multiplier"])
                self._log_zoom_source_once("native touchpad pinch", multiplier)
                log_factor = float(e.value()) * self._TIMELINE_NATIVE_PINCH_BASE_GAIN * multiplier
                self.zoom_at(math.exp(log_factor), e.position().x())
                e.accept()
                return True
            if e.gestureType() == Qt.NativeGestureType.PanNativeGesture:
                delta = e.delta()
                self.scroll_px -= delta.x() + delta.y()
                self.clamp_scroll()
                self._manual_view_until = time.monotonic() + 0.22
                self.update()
                e.accept()
                return True
        return super().event(e)

    def paintEvent(self, _):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(0, 0, 0, THEME["timeline"]["background_opacity"]))
        if not self.info:
            return
        p.setClipRect(self.rect())

        track_left = self.time_to_x(0)
        track_right = self.time_to_x(self.full_last_frame_time())
        selected_left = self.time_to_x(self.in_time)
        selected_right = self.time_to_x(self.playhead_bounds()[1])
        xi = self.in_handle_center_x()
        xo = self.out_handle_center_x()
        half_handle = self.half_handle
        track_h = self.height() - self.track_top

        if track_right > track_left:
            p.fillRect(QRectF(track_left, self.track_top, track_right - track_left, track_h), TIMELINE_FULL_CLIP_BACKGROUND)
        if selected_right > selected_left:
            p.fillRect(QRectF(selected_left, self.track_top, selected_right - selected_left, track_h), TIMELINE_SELECTED_RANGE_BACKGROUND)

        if not self.thumbnail.isNull() and selected_right > selected_left:
            h = max(1.0, track_h)
            w = h * self.thumbnail.width() / max(1, self.thumbnail.height())
            draw_w = min(w, selected_right - selected_left)
            if draw_w > 0:
                src_w = self.thumbnail.width() * (draw_w / w)
                p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
                p.drawImage(
                    QRectF(selected_left, self.track_top, draw_w, h),
                    self.thumbnail,
                    QRectF(0, 0, src_w, self.thumbnail.height()),
                )
                p.fillRect(QRectF(selected_left, self.track_top, draw_w, h), QColor(0, 0, 0, THEME["timeline"]["thumbnail_darkening"]))

        before_right = selected_left
        after_left = selected_right
        if before_right > track_left:
            p.fillRect(QRectF(track_left, self.track_top, before_right - track_left, track_h), TIMELINE_TRIMMED_AREA_OVERLAY)
        if track_right > after_left:
            p.fillRect(QRectF(after_left, self.track_top, track_right - after_left, track_h), TIMELINE_TRIMMED_AREA_OVERLAY)

        vol = 0 if self.muted else self.volume
        volume_top_y = RULER_H + 1
        volume_bottom_y = max(float(volume_top_y), float(self.height() - 1))
        vol_y = volume_bottom_y - (volume_bottom_y - volume_top_y) * (vol / 100.0)
        p.setPen(QPen(TIMELINE_VOLUME_LINE, 1))
        p.drawLine(QPointF(max(track_left, -10000), vol_y), QPointF(min(track_right, self.width() + 10000), vol_y))

        p.fillRect(QRectF(0, 0, self.width(), RULER_H), QColor(0, 0, 0, THEME["timeline"]["markers"]["ribbon_opacity"]))

        big_frames, small_frames = self.marker_frame_intervals()
        full_last_frame = self.full_last_frame_index()
        start_frame = max(0, int(math.floor(self.x_to_time(0) * self.info.fps)) - 2)
        end_frame = min(full_last_frame, int(math.ceil(self.x_to_time(self.width()) * self.info.fps)) + 2)
        p.setFont(QFont("Segoe UI", 8))

        first_small = max(0, (start_frame // small_frames) * small_frames)
        frame = first_small
        while frame <= end_frame:
            x = self.time_to_x(frame / self.info.fps)
            p.setPen(QPen(TIMELINE_MARKER_LINE, 1))
            p.drawLine(QPointF(x, RULER_H), QPointF(x, RULER_H - 8))
            frame += small_frames

        big_marker_frames = {0, full_last_frame}
        first_big = max(0, (start_frame // big_frames) * big_frames)
        frame = first_big
        while frame <= end_frame:
            big_marker_frames.add(frame)
            frame += big_frames

        font_metrics = p.fontMetrics()
        label_top = 0.0
        label_baseline = label_top + font_metrics.ascent()
        for frame in sorted(big_marker_frames):
            if frame < start_frame or frame > end_frame:
                continue
            x = self.time_to_x(frame / self.info.fps)
            p.setPen(QPen(TIMELINE_MARKER_LINE, 1))
            p.drawLine(QPointF(x, RULER_H), QPointF(x, RULER_H - 16))

            text = self.format_tick_frame(frame)
            text_w = float(font_metrics.horizontalAdvance(text))
            if frame == 0:
                text_x = x + 1.0
            elif frame == full_last_frame:
                text_x = x - text_w - 1.0
            else:
                text_x = x - text_w / 2.0
            p.setPen(TIMELINE_MARKER_TEXT)
            p.drawText(QPointF(text_x, label_baseline), text)

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(TIMELINE_TRIM_HANDLE)
        handle_top = self.track_top
        handle_h = self.height() - self.track_top
        p.drawRoundedRect(QRectF(xi - half_handle, handle_top, HANDLE_W, handle_h), 2, 2)
        p.drawRoundedRect(QRectF(xo - half_handle, handle_top, HANDLE_W, handle_h), 2, 2)

        xp = self.playhead_to_x(self.playhead)
        p.setPen(QPen(TIMELINE_PLAYHEAD, 1))
        p.drawLine(QPointF(xp, 0), QPointF(xp, self.height()))
        p.setBrush(TIMELINE_PLAYHEAD)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawPolygon(QPolygonF([QPointF(xp - 5, 0), QPointF(xp + 5, 0), QPointF(xp, 7)]))

    def mousePressEvent(self, e: QMouseEvent):
        if not self.info or e.button() != Qt.MouseButton.LeftButton:
            return
        if e.position().y() <= 6:
            self.drag_mode = "resize"
            self.resize_start_y = e.globalPosition().y()
            self.resize_start_h = self.height()
            self.setCursor(Qt.CursorShape.SizeVerCursor)
            e.accept()
            return

        x = e.position().x()
        xi = self.in_handle_center_x()
        xo = self.out_handle_center_x()
        if abs(x - xi) <= HANDLE_W:
            self.drag_mode = "in"
            self.drag_offset = x - xi
            self.setCursor(Qt.CursorShape.SizeHorCursor)
        elif abs(x - xo) <= HANDLE_W:
            self.drag_mode = "out"
            self.drag_offset = x - xo
            self.setCursor(Qt.CursorShape.SizeHorCursor)
        else:
            self.drag_mode = "playhead"
            t = self.clamp_playhead_time(self.x_to_time(x))
            self.playhead = t
            self.update()
            self.scrubStarted.emit(t)
        e.accept()

    def mouseMoveEvent(self, e: QMouseEvent):
        if not self.info:
            return
        if self.drag_mode == "resize":
            delta = self.resize_start_y - e.globalPosition().y()
            self.resizeRequested.emit(int(self.resize_start_h + delta))
            e.accept()
            return
        if self.drag_mode in {"in", "out"}:
            handle_center_x = e.position().x() - self.drag_offset
            boundary_x = (
                handle_center_x + self.half_handle
                if self.drag_mode == "in"
                else handle_center_x - self.half_handle
            )
            t = self.x_to_time(boundary_x)
            t = self.snap_drag_time(t, e.modifiers())
            fd = self.info.frame_duration
            if self.drag_mode == "in":
                t = min(t, self.last_frame_before(self.out_time))
                t = max(0.0, t)
                self.in_time = t
                self.inChanged.emit(t, False)
            else:
                last_frame_t = max(t, self.in_time)
                t = min(self.info.video_duration, last_frame_t + fd)
                self.out_time = t
                self.outChanged.emit(t, False)
            self.update()
            e.accept()
            return
        if self.drag_mode == "playhead":
            t = self.clamp_playhead_time(self.x_to_time(e.position().x()))
            self.playhead = t
            self.update()
            self.scrubMoved.emit(t)
            e.accept()
            return

        if e.position().y() <= 6:
            self.setCursor(Qt.CursorShape.SizeVerCursor)
        else:
            xi = self.in_handle_center_x()
            xo = self.out_handle_center_x()
            if abs(e.position().x() - xi) <= HANDLE_W or abs(e.position().x() - xo) <= HANDLE_W:
                self.setCursor(Qt.CursorShape.SizeHorCursor)
            else:
                self.unsetCursor()

    def mouseReleaseEvent(self, e: QMouseEvent):
        if not self.info or e.button() != Qt.MouseButton.LeftButton:
            return
        mode = self.drag_mode
        self.drag_mode = None
        self.unsetCursor()
        if mode == "in":
            self.inChanged.emit(self.in_time, True)
        elif mode == "out":
            self.outChanged.emit(self.out_time, True)
        elif mode == "playhead":
            self.scrubEnded.emit(self.playhead)
        e.accept()


class PlaybackSurface(QWidget):
    """Isolated playback region. The timeline is never parented into this widget."""

    def __init__(self, canvas: VideoCanvas, hud: QWidget, parent=None):
        super().__init__(parent)
        self.canvas = canvas
        self.hud = hud
        self.setMinimumHeight(1)

        self.canvas.setParent(self)
        self.hud.setParent(self)
        self.relayout()

    def relayout(self):
        w = max(1, self.width())
        h = max(1, self.height())
        self.canvas.setGeometry(0, 0, w, h)
        self.hud.setGeometry(0, 0, w, self.hud.height())
        self.canvas.lower()
        self.hud.raise_()

    def resizeEvent(self, e):
        self.relayout()
        super().resizeEvent(e)

class DropOpenArea(QWidget):
    filesDropped = Signal(list)
    clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumSize(420, 210)
        self.hovered = False

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.fillRect(self.rect(), APP_BACKGROUND)
        r = QRectF(16, 16, self.width() - 32, self.height() - 32)
        p.setBrush(QColor(THEME["launcher"]["background"]) if not self.hovered else QColor(THEME["launcher"]["hover_background"]))
        pen = QPen(QColor(THEME["launcher"]["border"]) if not self.hovered else QColor(THEME["launcher"]["hover_border"]), 1)
        pen.setStyle(Qt.PenStyle.DashLine)
        p.setPen(pen)
        p.drawRoundedRect(r, 12, 12)

        p.setPen(QColor(THEME["launcher"]["prompt"]))
        p.setFont(QFont("Segoe UI", 14, QFont.Weight.DemiBold))
        p.drawText(r.adjusted(0, 0, 0, -18), Qt.AlignmentFlag.AlignCenter, "Drop video files here")
        p.setPen(SECONDARY_TEXT)
        p.setFont(QFont("Segoe UI", 10))
        p.drawText(r.adjusted(0, 34, 0, 0), Qt.AlignmentFlag.AlignCenter, "or click to choose")

    def enterEvent(self, e):
        self.hovered = True
        self.update()
        super().enterEvent(e)

    def leaveEvent(self, e):
        self.hovered = False
        self.update()
        super().leaveEvent(e)

    def mouseReleaseEvent(self, e: QMouseEvent):
        if e.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
            e.accept()
            return
        super().mouseReleaseEvent(e)

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls() and any(u.isLocalFile() for u in e.mimeData().urls()):
            self.hovered = True
            self.update()
            e.acceptProposedAction()

    def dragLeaveEvent(self, e):
        self.hovered = False
        self.update()
        super().dragLeaveEvent(e)

    def dropEvent(self, e):
        self.hovered = False
        self.update()
        paths = [u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()]
        if paths:
            self.filesDropped.emit(paths)
            e.acceptProposedAction()


class LauncherWindow(QMainWindow):
    filesChosen = Signal(list)
    quitRequested = Signal()

    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.resize(560, 320)
        self.setMinimumSize(460, 270)

        title = QLabel("ClipTrim")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setFont(QFont("Segoe UI", 20, QFont.Weight.DemiBold))
        subtitle = QLabel("Open a clip. Trim it. Export it. Nothing else.")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setStyleSheet("color: #6f6f6f;")

        self.drop_area = DropOpenArea()
        self._file_dialog_open = False
        self.drop_area.clicked.connect(self.open_dialog)
        self.drop_area.filesDropped.connect(self.filesChosen.emit)

        root = QWidget()
        layout = QVBoxLayout(root)
        layout.setContentsMargins(22, 20, 22, 22)
        layout.setSpacing(8)
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addSpacing(6)
        layout.addWidget(self.drop_area, 1)
        self.setCentralWidget(root)

        self.setStyleSheet(
            """
            QMainWindow, QWidget { background: #000; color: #aaa; }
            QLabel { background: transparent; }
            """
        )

    def keyPressEvent(self, e: QKeyEvent):
        if e.key() == Qt.Key.Key_Escape:
            log("Escape pressed on launcher; closing ClipTrim")
            self.quitRequested.emit()
            e.accept()
            return
        super().keyPressEvent(e)

    def closeEvent(self, e):
        self.quitRequested.emit()
        e.ignore()

    def open_dialog(self):
        if self._file_dialog_open:
            log("File selector is already open", "DEBUG")
            return

        self._file_dialog_open = True
        try:
            paths, _ = QFileDialog.getOpenFileNames(
                self,
                "Open clips",
                str(Path.home() / "Downloads"),
                "Video files (*.mp4 *.mov *.mkv *.m4v *.avi *.webm *.mts *.m2ts *.mpg *.mpeg);;All files (*.*)",
            )
        finally:
            self._file_dialog_open = False

        if paths:
            self.filesChosen.emit(paths)
        else:
            log("File selector cancelled/escaped; returning to launcher", "DEBUG")
            self.show()
            self.raise_()
            self.activateWindow()


class MainWindow(QMainWindow):
    backRequested = Signal()
    quitRequested = Signal()

    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.resize(1280, 820)
        self.setMinimumSize(800, 520)
        self.setAcceptDrops(False)

        self.files: list[str] = []
        self.file_index = -1
        self.states: dict[str, tuple[float, float, int, bool]] = {}
        self.info: MediaInfo | None = None
        self.export_thread: QThread | None = None
        self.export_worker: ExportWorker | None = None
        self._fullscreen = False

        self._pressed_transport_keys: set[int] = set()
        self._pressed_direction_keys: list[int] = []
        self._k_used_for_shuttle = False
        self._shuttle_active = False
        self._shuttle_direction = 0
        self._shuttle_rate = 1.0
        self._shuttle_mode: str | None = None
        self._reverse_shuttle_anchor_frame = 0
        self._reverse_shuttle_started_at = 0.0
        self._reverse_shuttle_last_frame = -1
        self._handle_preview_return_time: float | None = None

        self._scrubbing = False
        self._resume_after_scrub = False
        self._resume_pending = False
        self._playback_ended_at_out = False
        self._scrub_target: float | None = None
        self._last_scrub_seek_ms: int | None = None
        self._scrub_settle_ms: int | None = None
        self._pending_proxy_hide_ms: int | None = None
        self._scrub_interval_ms = 17
        self._scrub_last_motion_t: float | None = None
        self._scrub_last_motion_wall: float | None = None
        self._scrub_velocity = 0.0
        self._scrub_timer = QTimer(self)
        self._scrub_timer.setSingleShot(True)
        self._scrub_timer.timeout.connect(self._flush_scrub_preview)

        self._scrub_cache_dir: Path | None = None
        self._scrub_cache_fps = 0.0
        self._scrub_cache_thread: QThread | None = None
        self._scrub_cache_worker: ScrubCacheWorker | None = None
        self._retired_scrub_caches: dict[
            QThread, tuple[ScrubCacheWorker | None, Path | None]
        ] = {}
        self._scrub_cache_generation = 0
        self._scrub_cache_result: tuple[bool, str, int, str] | None = None
        self._scrub_ram: OrderedDict[int, QImage] = OrderedDict()
        self._scrub_ram_bytes = 0

        self.audio = QAudioOutput(self)
        self.audio.setVolume(1.0)
        self.player = QMediaPlayer(self)
        self.player.setAudioOutput(self.audio)
        self.canvas = VideoCanvas()
        self.player.setVideoOutput(self.canvas.video_item)
        self._proxy_hide_timer = QTimer(self)
        self._proxy_hide_timer.setSingleShot(True)
        self._proxy_hide_timer.setInterval(40)
        self._proxy_hide_timer.timeout.connect(self.canvas.clear_scrub_frame)
        self._reverse_shuttle_timer = QTimer(self)
        self._reverse_shuttle_timer.setInterval(10)
        self._reverse_shuttle_timer.timeout.connect(self._advance_reverse_shuttle)

        self.timeline = Timeline()
        self.timeline.setFixedHeight(MIN_TIMELINE_H)
        self.timeline.seekRequested.connect(self.seek)
        self.timeline.scrubStarted.connect(self.on_scrub_started)
        self.timeline.scrubMoved.connect(self.on_scrub_moved)
        self.timeline.scrubEnded.connect(self.on_scrub_ended)
        self.timeline.inChanged.connect(self.on_in_dragged)
        self.timeline.outChanged.connect(self.on_out_dragged)
        self.timeline.resizeRequested.connect(self.resize_timeline)

        self.time_label = QLabel("00:00:000 / 00:00:000 · 0 fps")
        self.time_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        self.top_overlay = QWidget()
        self.top_overlay.setFixedHeight(30)
        self.top_overlay.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        top_l = QHBoxLayout(self.top_overlay)
        top_l.setContentsMargins(8, 4, 10, 4)
        top_l.setSpacing(0)
        top_l.addStretch(1)
        top_l.addWidget(self.time_label)

        self.playback_surface = PlaybackSurface(self.canvas, self.top_overlay)
        root = QWidget()
        editor_layout = QVBoxLayout(root)
        editor_layout.setContentsMargins(0, 0, 0, 0)
        editor_layout.setSpacing(0)
        editor_layout.addWidget(self.playback_surface, 1)
        editor_layout.addWidget(self.timeline, 0)
        self.setCentralWidget(root)

        self.setStyleSheet(
            """
            QMainWindow, QWidget { background: #000; color: #aaa; }
            QLabel { background: transparent; }
            """
        )
        self.top_overlay.setStyleSheet(
            """
            QWidget { background: transparent; }
            QLabel {
                background: rgba(0, 0, 0, 96);
                color: #a8a8a8;
                padding: 2px 6px;
                border-radius: 3px;
            }
            """
        )

        self.player.positionChanged.connect(self.on_position)
        self.player.mediaStatusChanged.connect(self.on_media_status)
        self.player.errorOccurred.connect(self.on_player_error)

    def load_files(self, paths: list[str]) -> bool:
        clean = [str(Path(p).resolve()) for p in paths if Path(p).is_file()]
        if not clean:
            return False
        self._reset_scrub_state()
        self._stop_scrub_cache()
        self.player.stop()
        self.player.setSource(QUrl())
        self.canvas.clear_media()
        self.info = None
        self.states.clear()
        self.files = clean
        self.file_index = 0
        return self.load_current_file()

    def save_state(self):
        if self.info:
            self.states[self.info.path] = (
                self.timeline.in_time,
                self.timeline.out_time,
                self.timeline.volume,
                self.timeline.muted,
            )

    def change_file(self, delta: int):
        if not self.files:
            return
        new_index = self.file_index + delta
        if not (0 <= new_index < len(self.files)):
            return
        self.save_state()
        self.file_index = new_index
        self.load_current_file()

    def load_current_file(self, ignore_embedded_trim: bool = False, force_reload: bool = False) -> bool:
        if not (0 <= self.file_index < len(self.files)):
            return False
        self._reset_scrub_state()
        self._stop_scrub_cache()
        path = self.files[self.file_index]

        if force_reload:
            log(f"Force-reloading clip: {path}")
            self.player.stop()
            self.player.setSource(QUrl())
            self.canvas.clear_media()
            self.info = None
            QApplication.processEvents()
        else:
            log(f"Loading clip: {path}")

        try:
            info = probe_media(path)
        except Exception as exc:
            log_exception(f"Failed to probe clip {path}", exc)
            QMessageBox.critical(self, APP_NAME, str(exc))
            return False
        self.info = info

        state = self.states.get(path)
        volume = state[2] if state is not None else 100
        muted = state[3] if state is not None else False

        if ignore_embedded_trim:
            in_time, out_time = 0.0, info.video_duration
            log("Reload requested: embedded In/Out metadata ignored for this load")
        elif state is not None:
            in_time, out_time = state[0], state[1]
        else:
            saved_frames = read_embedded_trim_frames(path, info)
            if saved_frames is None:
                in_time, out_time = 0.0, info.video_duration
            else:
                in_time, out_time = trim_frames_to_times(info, *saved_frames)

        self.timeline.set_media(info, in_time, out_time)
        self.timeline.set_volume(volume, muted)
        self.audio.setVolume(volume / 100.0)
        self.audio.setMuted(muted)
        self.canvas.set_source_size(info.width, info.height)
        self._start_scrub_cache(info)
        self.player.setSource(QUrl.fromLocalFile(path))
        self.player.pause()
        self.timeline.set_playhead(self.timeline.in_time)
        self.refresh_thumbnail(self.timeline.in_time)
        self.canvas.reset_view()
        self.update_time_label(self.timeline.in_time)
        return True

    def persist_trim_metadata(self):
        if not self.info:
            return


        self.states[self.info.path] = (
            self.timeline.in_time,
            self.timeline.out_time,
            self.timeline.volume,
            self.timeline.muted,
        )
        write_embedded_trim_frames(
            self.info.path,
            self.info,
            self.timeline.in_time,
            self.timeline.out_time,
        )

    def reload_current_clip(self):
        if not self.info or self.export_thread:
            return
        answer = QMessageBox.question(
            self,
            "Reload clip",
            "Reload this clip from scratch?\n\n"
            "This resets In/Out for this reload, rebuilds the scrub cache, and resets "
            "preview/timeline zoom and pan. Existing embedded In/Out metadata will be ignored "
            "for this reload.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            log("Reload cancelled", "DEBUG")
            return

        path = self.info.path
        volume, muted = self.timeline.volume, self.timeline.muted

        self.states[path] = (0.0, self.info.video_duration, volume, muted)
        self.load_current_file(ignore_embedded_trim=True, force_reload=True)

    def refresh_thumbnail(self, t: float):
        if not self.info:
            return
        self.timeline.set_thumbnail(make_thumbnail(self.info.path, t))

    def resize_timeline(self, requested: int):
        max_h = min(MAX_TIMELINE_H, int(self.height() * 0.48))
        self.timeline.setFixedHeight(max(MIN_TIMELINE_H, min(max_h, requested)))

    def _reset_scrub_state(self):
        self._scrub_timer.stop()
        if hasattr(self, "_proxy_hide_timer"):
            self._proxy_hide_timer.stop()
        if hasattr(self, "_reverse_shuttle_timer"):
            self._reverse_shuttle_timer.stop()
        if hasattr(self, "player"):
            self.player.setPlaybackRate(1.0)
        self._scrubbing = False
        self._resume_after_scrub = False
        self._resume_pending = False
        self._playback_ended_at_out = False
        self._scrub_target = None
        self._scrub_settle_ms = None
        self._pending_proxy_hide_ms = None
        self._last_scrub_seek_ms = None
        self._scrub_last_motion_t = None
        self._scrub_last_motion_wall = None
        self._scrub_velocity = 0.0
        self._pressed_transport_keys.clear()
        self._pressed_direction_keys.clear()
        self._k_used_for_shuttle = False
        self._shuttle_active = False
        self._shuttle_direction = 0
        self._shuttle_rate = 1.0
        self._shuttle_mode = None
        self._reverse_shuttle_last_frame = -1
        self._handle_preview_return_time = None
        if hasattr(self, "canvas"):
            self.canvas.clear_scrub_frame()

    def _stop_scrub_cache(self) -> bool:
        """Cancel the current cache, retaining a rare slow thread until it exits."""
        worker = self._scrub_cache_worker
        thread = self._scrub_cache_thread
        cache_dir = self._scrub_cache_dir
        old_generation = self._scrub_cache_generation
        self._scrub_cache_generation += 1
        self._scrub_cache_result = None

        if worker:
            log(f"Stopping scrub cache generation {old_generation}")
            worker.cancel()

        if thread:
            if thread.isRunning():
                log(f"Waiting for scrub cache QThread generation {old_generation} to stop")
                thread.requestInterruption()
                thread.quit()
                if not thread.wait(3000):
                    log(
                        f"Scrub cache QThread generation {old_generation} did not stop within 3 seconds; "
                        "waiting once more after FFmpeg cancellation",
                        "WARN",
                    )
                    if worker:
                        worker.cancel()
                    thread.quit()
                    if not thread.wait(3000):
                        log(
                            f"Scrub cache QThread generation {old_generation} is still running. "
                            "Retiring it until its finished signal arrives.",
                            "ERROR",
                        )
                        self._retired_scrub_caches[thread] = (worker, cache_dir)
                        self._scrub_cache_worker = None
                        self._scrub_cache_thread = None
                        self._scrub_cache_dir = None
                        self._scrub_cache_fps = 0.0
                        self._scrub_ram.clear()
                        self._scrub_ram_bytes = 0
                        return False
            log(f"Scrub cache QThread generation {old_generation} stopped")

        self._scrub_cache_worker = None
        self._scrub_cache_thread = None
        self._scrub_cache_dir = None
        self._scrub_cache_fps = 0.0
        self._scrub_ram.clear()
        self._scrub_ram_bytes = 0
        if cache_dir:
            remove_tree(cache_dir, "clip scrub cache")
        return True

    def _wait_for_retired_scrub_caches(self, timeout_ms: int) -> bool:
        """Wait a bounded time for every retained cache thread to finish."""
        deadline = time.monotonic() + max(0, timeout_ms) / 1000.0
        for thread, (worker, cache_dir) in list(self._retired_scrub_caches.items()):
            if worker:
                worker.cancel()
            thread.requestInterruption()
            thread.quit()
            remaining_ms = max(0, int((deadline - time.monotonic()) * 1000))
            if thread.isRunning() and (remaining_ms <= 0 or not thread.wait(remaining_ms)):
                return False
            self._retired_scrub_caches.pop(thread, None)
            if cache_dir:
                remove_tree(cache_dir, "retired clip scrub cache")
        return True

    def _start_scrub_cache(self, info: MediaInfo):
        self._stop_scrub_cache()
        cache_fps = max(
            1.0,
            min(
                float(info.fps),
                SCRUB_CACHE_MAX_FPS,
                SCRUB_CACHE_MAX_FRAMES / max(info.duration, 1e-6),
            ),
        )
        generation = self._scrub_cache_generation
        cache_dir = SCRUB_RUN_DIR / f"clip-{uuid.uuid4().hex}"
        self._scrub_cache_dir = cache_dir
        self._scrub_cache_fps = cache_fps
        self._scrub_cache_result = None
        cache_dir.mkdir(parents=True, exist_ok=True)

        log(
            f"Starting scrub cache generation {generation}: "
            f"{cache_fps:.2f} fps @ <= {SCRUB_CACHE_MAX_SIDE}px, dir={cache_dir}"
        )

        thread = QThread(self)
        thread.setObjectName(f"ScrubCache-{generation}")
        worker = ScrubCacheWorker(info, cache_dir, cache_fps, generation)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.done.connect(self._on_scrub_cache_done)
        worker.done.connect(thread.quit)
        worker.done.connect(worker.deleteLater)
        thread.finished.connect(lambda gen=generation, th=thread: self._on_scrub_cache_thread_finished(gen, th))
        thread.finished.connect(thread.deleteLater)
        self._scrub_cache_thread = thread
        self._scrub_cache_worker = worker
        thread.start()
        log(f"Scrub cache QThread generation {generation} started")

    def _on_scrub_cache_done(self, ok: bool, message: str, generation: int, cache_dir: str):
        cache_path = Path(cache_dir)
        log(
            f"Scrub cache done signal received: generation={generation}, ok={ok}, "
            f"current_generation={self._scrub_cache_generation}, dir={cache_path}"
        )
        if generation != self._scrub_cache_generation or cache_path != self._scrub_cache_dir:
            log(f"Ignoring stale scrub cache result for generation {generation}", "WARN")
            return
        self._scrub_cache_result = (ok, message, generation, cache_dir)
        log(f"Scrub cache generation {generation} finished FFmpeg work; waiting for QThread shutdown")

    def _on_scrub_cache_thread_finished(self, generation: int, thread: QThread):
        log(
            f"Scrub cache QThread finished signal: generation={generation}, "
            f"is_current={thread is self._scrub_cache_thread}"
        )
        retired = self._retired_scrub_caches.pop(thread, None)
        if retired is not None:
            _, cache_dir = retired
            if cache_dir:
                remove_tree(cache_dir, "retired clip scrub cache")
            log(f"Retired scrub QThread generation {generation} stopped")
            return

        if thread is not self._scrub_cache_thread:
            log(f"Finished scrub QThread generation {generation} is no longer current", "WARN")
            return

        result = self._scrub_cache_result
        self._scrub_cache_worker = None
        self._scrub_cache_thread = None
        self._scrub_cache_result = None

        if result is None:
            log(f"Scrub cache QThread generation {generation} ended without a done result", "ERROR")
            return

        ok, message, result_generation, cache_dir = result
        cache_path = Path(cache_dir)
        if result_generation != self._scrub_cache_generation or cache_path != self._scrub_cache_dir:
            log(
                f"Scrub cache QThread generation {generation} completed with stale result "
                f"generation={result_generation}",
                "WARN",
            )
            return

        if ok:
            try:
                frame_count = sum(1 for _ in cache_path.glob("frame_*.jpg"))
                total_bytes = sum(p.stat().st_size for p in cache_path.glob("frame_*.jpg"))
                log(
                    f"Scrub cache ready: {self._scrub_cache_fps:.2f} fps @ <= {SCRUB_CACHE_MAX_SIDE}px; "
                    f"frames={frame_count}, disk={total_bytes / (1024 * 1024):.1f} MiB"
                )
            except Exception as exc:
                log_exception("Scrub cache completed but cache statistics failed", exc)
                log(f"Scrub cache ready: {self._scrub_cache_fps:.2f} fps @ <= {SCRUB_CACHE_MAX_SIDE}px")
        else:
            log(f"Scrub cache disabled: {message or 'unknown error'}", "ERROR")

    def _scrub_cache_image(self, t: float) -> QImage | None:
        if not self._scrub_cache_dir or self._scrub_cache_fps <= 0:
            return None
        index = max(0, int(round(t * self._scrub_cache_fps)))

        candidates = (index, index - 1, index + 1, index - 2, index + 2)
        for candidate in candidates:
            if candidate < 0:
                continue
            cached = self._scrub_ram.pop(candidate, None)
            if cached is not None:
                self._scrub_ram[candidate] = cached
                return cached
            path = self._scrub_cache_dir / f"frame_{candidate:08d}.jpg"
            try:
                if not path.is_file() or path.stat().st_size < 128:
                    continue
            except OSError as exc:
                log_exception(f"Could not inspect scrub cache frame {path}", exc)
                continue
            image = QImage(str(path))
            if image.isNull():
                continue
            size = max(1, int(image.sizeInBytes()))
            self._scrub_ram[candidate] = image
            self._scrub_ram_bytes += size
            while self._scrub_ram and self._scrub_ram_bytes > SCRUB_RAM_MAX_BYTES:
                _, evicted = self._scrub_ram.popitem(last=False)
                self._scrub_ram_bytes -= max(1, int(evicted.sizeInBytes()))
            return image
        return None

    def seek(self, t: float):
        if not self.info:
            return
        self._playback_ended_at_out = False
        t = self.timeline.clamp_playhead_time(t)
        if not self._scrubbing:
            self._scrub_settle_ms = None
            self._pending_proxy_hide_ms = None
            self.canvas.clear_scrub_frame()
        self.player.setPosition(int(round(t * 1000)))
        self.timeline.set_playhead(t)
        self.update_time_label(t)

    def _flush_scrub_preview(self):
        if not self.info or self._scrub_target is None:
            return
        target = frame_snap(self._scrub_target, self.info)
        image = self._scrub_cache_image(target)
        if image is not None:
            self.canvas.set_scrub_frame(image)
            return

        self.canvas.clear_scrub_frame()
        ms = int(round(target * 1000.0))
        if ms != self._last_scrub_seek_ms:
            self._last_scrub_seek_ms = ms
            self.player.setPosition(ms)

    def _update_scrub_rate(self, target: float):
        now = time.monotonic()
        if self._scrub_last_motion_t is not None and self._scrub_last_motion_wall is not None:
            wall_dt = max(1e-4, now - self._scrub_last_motion_wall)
            media_speed = abs(target - self._scrub_last_motion_t) / wall_dt

            desired_hz = max(15.0, min(60.0, 60.0 / math.sqrt(max(1.0, media_speed))))

            self._scrub_velocity = self._scrub_velocity * 0.65 + media_speed * 0.35
            smoothed_hz = max(15.0, min(60.0, 60.0 / math.sqrt(max(1.0, self._scrub_velocity))))
            desired_hz = (desired_hz + smoothed_hz) * 0.5
            self._scrub_interval_ms = max(17, min(67, int(round(1000.0 / desired_hz))))
        else:
            self._scrub_velocity = 0.0
            self._scrub_interval_ms = 17
        self._scrub_last_motion_t = target
        self._scrub_last_motion_wall = now

    def on_scrub_started(self, t: float):
        if not self.info:
            return
        self._playback_ended_at_out = False
        self._scrub_timer.stop()
        self._proxy_hide_timer.stop()
        self._scrubbing = True
        self._scrub_settle_ms = None
        self._pending_proxy_hide_ms = None
        self._resume_after_scrub = self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState
        self._resume_pending = False
        self.player.pause()
        self._scrub_target = frame_snap(t, self.info)
        self._scrub_last_motion_t = None
        self._scrub_last_motion_wall = None
        self._update_scrub_rate(self._scrub_target)
        self.update_time_label(self._scrub_target)
        self._flush_scrub_preview()

    def on_scrub_moved(self, t: float):
        if not self.info:
            return
        self._scrub_target = frame_snap(t, self.info)
        self._update_scrub_rate(self._scrub_target)
        self.update_time_label(self._scrub_target)
        if not self._scrub_timer.isActive():
            self._scrub_timer.start(self._scrub_interval_ms)

    def on_scrub_ended(self, t: float):
        if not self.info:
            return
        self._scrub_timer.stop()
        target = frame_snap(t, self.info)
        self._scrub_target = target

        image = self._scrub_cache_image(target)
        if image is not None:
            self.canvas.set_scrub_frame(image)
        target_ms = int(round(target * 1000.0))
        tolerance = max(2, int(round(750.0 / max(self.info.fps, 1e-6))))
        already_at_target = abs(self.player.position() - target_ms) <= tolerance
        self._scrubbing = False
        self._scrub_settle_ms = target_ms
        self._pending_proxy_hide_ms = target_ms
        self._last_scrub_seek_ms = target_ms
        self.player.setPosition(target_ms)
        self.timeline.set_playhead(target)
        self.update_time_label(target)
        if self._resume_after_scrub:
            self._resume_after_scrub = False
            self._resume_pending = True
        if already_at_target:

            self._scrub_settle_ms = None
            self._pending_proxy_hide_ms = None
            if image is not None:
                self._proxy_hide_timer.start()
            if self._resume_pending:
                self._resume_pending = False
                self.player.play()

    def on_in_dragged(self, t: float, released: bool):
        if not self.info:
            return
        self._playback_ended_at_out = False
        self.timeline.in_time = t
        if not released:
            self._preview_handle_position(t)
            return

        self.persist_trim_metadata()
        self._finish_handle_preview()
        self.refresh_thumbnail(t)

    def on_out_dragged(self, t: float, released: bool):
        if not self.info:
            return
        self._playback_ended_at_out = False
        self.timeline.out_time = t
        preview_t = self.timeline.last_frame_before(t)
        if not released:
            self._preview_handle_position(preview_t)
            return

        self.persist_trim_metadata()
        self._finish_handle_preview()

    def _preview_handle_position(self, t: float):
        if not self.info:
            return
        if self._handle_preview_return_time is None:
            self._handle_preview_return_time = self.timeline.playhead
            self.on_scrub_started(t)
        else:
            self.on_scrub_moved(t)

    def _finish_handle_preview(self):
        if not self.info:
            return
        if self._handle_preview_return_time is None:
            target = self.timeline.clamp_playhead_time(self.timeline.playhead)
            if abs(target - self.timeline.playhead) > 1e-9:
                self.seek(target)
            else:
                self.update_time_label(target)
            return

        target = self.timeline.clamp_playhead_time(self._handle_preview_return_time)
        self._handle_preview_return_time = None
        self.on_scrub_ended(target)

    def _last_visible_frame_time(self) -> float:
        if not self.info:
            return 0.0

        return self.timeline.playhead_bounds()[1]

    def _hold_on_last_frame(self, reason: str):
        if not self.info:
            return

        last_t = self._last_visible_frame_time()
        last_ms = int(round(last_t * 1000.0))
        self._playback_ended_at_out = True
        self._resume_pending = False
        self._resume_after_scrub = False
        self.player.pause()

        if abs(self.player.position() - last_ms) > 1:
            self.player.setPosition(last_ms)
        self.timeline.set_playhead(last_t)
        self.update_time_label(last_t)
        log(
            f"Playback reached Out ({reason}); holding last visible frame at "
            f"{last_t:.6f}s (out={self.timeline.out_time:.6f}s, "
            f"video_duration={self.info.video_duration:.6f}s)"
        )

    def on_position(self, ms: int):
        if not self.info:
            return

        if self._scrubbing:
            return
        tolerance = max(2, int(round(750.0 / max(self.info.fps, 1e-6))))
        if self._scrub_settle_ms is not None:
            if abs(ms - self._scrub_settle_ms) > tolerance:
                return
            self._scrub_settle_ms = None
        if self._pending_proxy_hide_ms is not None and abs(ms - self._pending_proxy_hide_ms) <= tolerance:
            self._pending_proxy_hide_ms = None



            self._proxy_hide_timer.start()
            if self._resume_pending:
                self._resume_pending = False
                self.player.play()
        t = ms / 1000.0
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            last_t = self._last_visible_frame_time()
            if t >= last_t:
                self._hold_on_last_frame("position reached final frame")
                return
        self.timeline.set_playhead(t)
        self.update_time_label(t)

    def on_media_status(self, status):
        log(f"Qt media status changed: {status}", "DEBUG")
        if status == QMediaPlayer.MediaStatus.LoadedMedia and self.info:
            if self._playback_ended_at_out:
                log("Ignoring LoadedMedia transition while holding the final frame", "DEBUG")
            else:
                self.player.pause()
                self.seek(self.timeline.in_time)
        elif status == QMediaPlayer.MediaStatus.EndOfMedia and self.info:
            self._hold_on_last_frame("Qt EndOfMedia")

    def on_player_error(self, error, error_string):
        if error != QMediaPlayer.Error.NoError:
            log(f"Qt playback error {error}: {error_string}", "ERROR")

    def update_time_label(self, t: float):
        if not self.info:
            self.time_label.setText("00:00:000 / 00:00:000 · 0 fps")
            return
        fps_text = f"{self.info.fps:.2f}".rstrip("0").rstrip(".")
        self.time_label.setText(
            f"{self.format_overlay_time(t)} / {self.format_overlay_time(self.info.duration)} · {fps_text} fps"
        )

    @staticmethod
    def format_overlay_time(t: float) -> str:
        total_ms = max(0, int(round(t * 1000.0)))
        minutes, rem = divmod(total_ms, 60_000)
        seconds, millis = divmod(rem, 1000)
        return f"{minutes:02}:{seconds:02}:{millis:03}"

    def toggle_play(self):
        if not self.info:
            return
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
            return

        if self._playback_ended_at_out:
            log(f"Resuming after Out; restarting playback from In at {self.timeline.in_time:.6f}s")
            self.seek(self.timeline.in_time)
            self.player.play()
            return

        pos = self.player.position() / 1000.0
        if pos < self.timeline.in_time or pos > self._last_visible_frame_time():
            self.seek(self.timeline.in_time)
        self.player.play()

    def set_in_from_playhead(self):
        if not self.info:
            return
        self._playback_ended_at_out = False
        t = frame_snap(self.player.position() / 1000.0, self.info)
        t = min(t, self.timeline.last_frame_before(self.timeline.out_time))
        self.timeline.in_time = max(0.0, t)
        self.persist_trim_metadata()
        self.refresh_thumbnail(self.timeline.in_time)
        self.timeline.update()

    def set_out_from_playhead(self):
        if not self.info:
            return
        self._playback_ended_at_out = False
        t = frame_snap(self.player.position() / 1000.0, self.info)
        t = max(t, self.timeline.in_time)
        self.timeline.out_time = min(self.info.video_duration, t + self.info.frame_duration)
        self.timeline.update()
        self.persist_trim_metadata()

    def step_frame(self, delta: int):
        if not self.info:
            return
        self.player.pause()

        fps = max(self.info.fps, 1e-6)
        first, last = self.timeline.full_playhead_bounds()
        first_frame = int(round(first * fps))
        last_frame = int(round(last * fps))
        current_frame = int(round(self.timeline.playhead * fps))
        target_frame = max(first_frame, min(last_frame, current_frame + delta))
        self.seek(target_frame / fps)

    def jump_marker(self, direction: int, large: bool):
        if not self.info:
            return
        self.player.pause()
        t = self.timeline.playhead
        target = self.timeline.snap_marker(t, large, direction=direction, exclude_current=True)
        self.seek(target)

    def move_transport(self, direction: int, mods: Qt.KeyboardModifier):
        if mods & Qt.KeyboardModifier.ShiftModifier:
            self.jump_marker(direction, True)
        elif mods & Qt.KeyboardModifier.ControlModifier:
            self.jump_marker(direction, False)
        else:
            self.step_frame(direction)

    def jump_to_number_position(self, number: int, relative_to_trim: bool):
        if not self.info or not 1 <= number <= 9:
            return
        self.player.pause()
        if relative_to_trim:
            first, last = self.timeline.playhead_bounds()
        else:
            first, last = self.timeline.full_playhead_bounds()
        fraction = (number - 1) / 8.0
        self.seek(first + (last - first) * fraction)

    @staticmethod
    def _number_for_key(key: int) -> int | None:
        number_keys = {
            Qt.Key.Key_1: 1,
            Qt.Key.Key_2: 2,
            Qt.Key.Key_3: 3,
            Qt.Key.Key_4: 4,
            Qt.Key.Key_5: 5,
            Qt.Key.Key_6: 6,
            Qt.Key.Key_7: 7,
            Qt.Key.Key_8: 8,
            Qt.Key.Key_9: 9,
        }
        return number_keys.get(key)

    @staticmethod
    def _direction_for_key(key: int) -> int:
        if key in {Qt.Key.Key_Left, Qt.Key.Key_J}:
            return -1
        if key in {Qt.Key.Key_Right, Qt.Key.Key_L}:
            return 1
        return 0

    def _active_direction_key(self) -> int | None:
        for key in reversed(self._pressed_direction_keys):
            if key in self._pressed_transport_keys:
                return key
        return None

    @staticmethod
    def _shuttle_speed(slow: bool, mods: Qt.KeyboardModifier) -> float:
        if slow:
            if mods & Qt.KeyboardModifier.ShiftModifier:
                return 0.10
            if mods & Qt.KeyboardModifier.ControlModifier:
                return 0.50
            return 0.25
        if mods & Qt.KeyboardModifier.ShiftModifier:
            return 2.0
        if mods & Qt.KeyboardModifier.ControlModifier:
            return 1.25
        return 1.5

    def _update_shuttle_from_keys(self, mods: Qt.KeyboardModifier):
        direction_key = self._active_direction_key()
        if direction_key is None:
            self._stop_shuttle()
            return

        slow = Qt.Key.Key_K in self._pressed_transport_keys
        fast = bool(mods & Qt.KeyboardModifier.AltModifier)
        if not slow and not fast:
            self._stop_shuttle()
            return
        if slow:
            self._k_used_for_shuttle = True

        direction = self._direction_for_key(direction_key)
        rate = self._shuttle_speed(slow, mods)
        mode = "slow" if slow else "fast"
        self._start_or_update_shuttle(direction, rate, mode)

    def _start_or_update_shuttle(self, direction: int, rate: float, mode: str):
        if not self.info:
            return
        if (
            self._shuttle_active
            and self._shuttle_direction == direction
            and self._shuttle_mode == mode
        ):
            if abs(self._shuttle_rate - rate) < 1e-9:
                return
            self._shuttle_rate = rate
            if direction > 0:
                self.player.setPlaybackRate(rate)
            else:
                self._anchor_reverse_shuttle()
            return

        if self._shuttle_active:
            self._stop_shuttle()

        self._shuttle_active = True
        self._shuttle_direction = direction
        self._shuttle_rate = rate
        self._shuttle_mode = mode
        self._playback_ended_at_out = False

        first, last = self.timeline.playhead_bounds()
        if self.timeline.playhead < first:
            self.seek(first)
        elif self.timeline.playhead > last:
            self.seek(last)

        if direction > 0:
            self._reverse_shuttle_timer.stop()
            self._scrubbing = False
            if self.timeline.playhead >= self._last_visible_frame_time():
                self.seek(self.timeline.in_time)
            self.player.setPlaybackRate(rate)
            self.player.play()
        else:
            self.player.pause()
            self.player.setPlaybackRate(1.0)
            self._scrubbing = True
            self._resume_after_scrub = False
            self._resume_pending = False
            self._proxy_hide_timer.stop()
            self._anchor_reverse_shuttle()
            self._reverse_shuttle_timer.start()

        log(f"Transport shuttle started: direction={direction:+d}, rate={rate:g}x, mode={mode}", "DEBUG")

    def _anchor_reverse_shuttle(self):
        if not self.info:
            return
        fps = max(self.info.fps, 1e-6)
        self._reverse_shuttle_anchor_frame = int(round(self.timeline.playhead * fps))
        self._reverse_shuttle_started_at = time.monotonic()
        self._reverse_shuttle_last_frame = self._reverse_shuttle_anchor_frame

    def _advance_reverse_shuttle(self):
        if not self.info or not self._shuttle_active or self._shuttle_direction >= 0:
            self._reverse_shuttle_timer.stop()
            return

        fps = max(self.info.fps, 1e-6)
        elapsed = max(0.0, time.monotonic() - self._reverse_shuttle_started_at)
        frames_back = int(math.floor(elapsed * fps * self._shuttle_rate + 1e-9))
        first, _ = self.timeline.playhead_bounds()
        first_frame = int(round(first * fps))
        target_frame = max(first_frame, self._reverse_shuttle_anchor_frame - frames_back)
        if target_frame == self._reverse_shuttle_last_frame:
            return

        self._reverse_shuttle_last_frame = target_frame
        target = target_frame / fps
        self.timeline.set_playhead(target)
        self.update_time_label(target)
        self._scrub_target = target
        image = self._scrub_cache_image(target)
        if image is not None:
            self.canvas.set_scrub_frame(image)
        else:
            self.canvas.clear_scrub_frame()
            self.player.setPosition(int(round(target * 1000.0)))

        if target_frame <= first_frame:
            self._stop_shuttle()

    def _stop_shuttle(self):
        if not self._shuttle_active:
            return
        was_reverse = self._shuttle_direction < 0
        target = self.timeline.playhead
        self._shuttle_active = False
        self._shuttle_direction = 0
        self._shuttle_rate = 1.0
        self._shuttle_mode = None
        self._reverse_shuttle_timer.stop()
        self.player.pause()
        self.player.setPlaybackRate(1.0)
        if was_reverse and self.info:
            self._resume_after_scrub = False
            self.on_scrub_ended(target)
        log("Transport shuttle stopped", "DEBUG")

    def change_volume(self, delta: int):
        if not self.info:
            return
        vol = max(0, min(100, self.timeline.volume + delta))
        self.timeline.set_volume(vol, self.timeline.muted)
        self.audio.setVolume(vol / 100.0)

    def toggle_mute(self):
        if not self.info:
            return
        muted = not self.timeline.muted
        self.timeline.set_volume(self.timeline.volume, muted)
        self.audio.setMuted(muted)

    def export_current(self):
        if not self.info or self.export_thread:
            return
        self.save_state()
        downloads = Path.home() / "Downloads"
        if not downloads.is_dir():
            downloads = Path.home()
        default_name = f"clipped_{Path(self.info.path).stem}.mp4"
        output, _ = QFileDialog.getSaveFileName(
            self,
            "Export clipped video",
            str(downloads / default_name),
            "MPEG-4 Video (*.mp4)",
        )
        if not output:
            return
        output_path = Path(output)
        if output_path.suffix.lower() != ".mp4":
            output_path = output_path.with_suffix(".mp4")
        output = str(output_path)
        print(f"Exporting {output}")
        self.export_thread = QThread(self)
        self.export_worker = ExportWorker(self.info, self.timeline.in_time, self.timeline.out_time, output)
        self.export_worker.moveToThread(self.export_thread)
        self.export_thread.started.connect(self.export_worker.run)

        self.export_worker.finished.connect(self._on_export_succeeded)
        self.export_worker.failed.connect(self._on_export_failed)
        self.export_worker.finished.connect(self.export_thread.quit)
        self.export_worker.failed.connect(self.export_thread.quit)
        self.export_worker.finished.connect(self.export_worker.deleteLater)
        self.export_worker.failed.connect(self.export_worker.deleteLater)
        self.export_thread.finished.connect(self._on_export_thread_finished)
        self.export_thread.finished.connect(self.export_thread.deleteLater)
        self.export_thread.start()

    def _on_export_succeeded(self, path: str, mode: str):
        print(f"Saved {path} ({mode})")

    def _on_export_failed(self, message: str):
        QMessageBox.critical(self, "Export failed", message)
        print(f"Export failed: {message}", file=sys.stderr)

    def _on_export_thread_finished(self):
        self.export_thread = None
        self.export_worker = None


    def toggle_fullscreen(self):
        self._fullscreen = not self._fullscreen
        if self._fullscreen:
            self.showFullScreen()
        else:
            self.showNormal()

    def toggle_hud(self):
        self.top_overlay.setVisible(not self.top_overlay.isVisible())

    def keyPressEvent(self, e: QKeyEvent):
        if e.isAutoRepeat() and e.key() in {
            Qt.Key.Key_I,
            Qt.Key.Key_O,
            Qt.Key.Key_BracketLeft,
            Qt.Key.Key_BracketRight,
            Qt.Key.Key_M,
            Qt.Key.Key_H,
            Qt.Key.Key_R,
        }:
            return
        key = e.key()
        mods = e.modifiers()
        direction = self._direction_for_key(key)
        number_position = self._number_for_key(key)

        if not e.isAutoRepeat() and (direction or key == Qt.Key.Key_K):
            self._pressed_transport_keys.add(key)
            if direction:
                if key in self._pressed_direction_keys:
                    self._pressed_direction_keys.remove(key)
                self._pressed_direction_keys.append(key)

        if key == Qt.Key.Key_F11 or (
            key in {Qt.Key.Key_Return, Qt.Key.Key_Enter}
            and bool(mods & Qt.KeyboardModifier.AltModifier)
        ):
            self.toggle_fullscreen()
        elif key in {Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_E}:
            self.export_current()
        elif key == Qt.Key.Key_Escape:
            if not self.export_thread:
                self.player.pause()
                self._reset_scrub_state()
                self._stop_scrub_cache()
                self.backRequested.emit()
        elif key == Qt.Key.Key_Space:
            if self._shuttle_active:
                self._stop_shuttle()
            else:
                self.toggle_play()
        elif key == Qt.Key.Key_K:
            if e.isAutoRepeat():
                e.accept()
                return


            if self._active_direction_key() is not None:
                self._update_shuttle_from_keys(mods)
        elif key in {Qt.Key.Key_I, Qt.Key.Key_BracketLeft}:
            self.set_in_from_playhead()
        elif key in {Qt.Key.Key_O, Qt.Key.Key_BracketRight}:
            self.set_out_from_playhead()
        elif number_position is not None:
            self.jump_to_number_position(
                number_position,
                bool(mods & Qt.KeyboardModifier.ShiftModifier),
            )
        elif direction:
            if Qt.Key.Key_K in self._pressed_transport_keys or mods & Qt.KeyboardModifier.AltModifier:
                if not e.isAutoRepeat():
                    self._update_shuttle_from_keys(mods)
            else:
                self.move_transport(direction, mods)
        elif key == Qt.Key.Key_Up:
            if mods & Qt.KeyboardModifier.ControlModifier:
                amount = 10
            elif mods & Qt.KeyboardModifier.ShiftModifier:
                amount = 1
            else:
                amount = 5
            self.change_volume(amount)
        elif key == Qt.Key.Key_Down:
            if mods & Qt.KeyboardModifier.ControlModifier:
                amount = 10
            elif mods & Qt.KeyboardModifier.ShiftModifier:
                amount = 1
            else:
                amount = 5
            self.change_volume(-amount)
        elif key == Qt.Key.Key_M:
            self.toggle_mute()
        elif key == Qt.Key.Key_H:
            self.toggle_hud()
        elif key == Qt.Key.Key_R:
            self.reload_current_clip()
        elif key == Qt.Key.Key_0:
            self.canvas.reset_view()
        elif key in {Qt.Key.Key_Shift, Qt.Key.Key_Control, Qt.Key.Key_Alt} and self._shuttle_active:
            self._update_shuttle_from_keys(mods)
        else:
            super().keyPressEvent(e)

    def keyReleaseEvent(self, e: QKeyEvent):
        if e.isAutoRepeat():
            e.accept()
            return

        key = e.key()
        mods = e.modifiers()
        direction = self._direction_for_key(key)
        if direction or key == Qt.Key.Key_K:
            self._pressed_transport_keys.discard(key)
        if direction and key in self._pressed_direction_keys:
            self._pressed_direction_keys.remove(key)

        if key == Qt.Key.Key_K:
            used_for_shuttle = self._k_used_for_shuttle
            self._update_shuttle_from_keys(mods)
            self._k_used_for_shuttle = False
            if not used_for_shuttle:
                self.toggle_play()
            e.accept()
            return

        if direction or key in {Qt.Key.Key_Shift, Qt.Key.Key_Control, Qt.Key.Key_Alt}:
            if self._shuttle_active:
                self._update_shuttle_from_keys(mods)
            e.accept()
            return

        super().keyReleaseEvent(e)

    def closeEvent(self, e):
        if self.export_thread:
            QMessageBox.warning(self, APP_NAME, "An export is still running. Close again after it finishes.")
            e.ignore()
            return
        self.quitRequested.emit()
        e.ignore()


def main():
    log(f"{APP_NAME} starting; pid={os.getpid()}, Python={sys.version.split()[0]}, platform={sys.platform}")
    log(f"App directory={APP_DIR}; temp directory={TMP_DIR}; runtime temp={TEMP_RUN_DIR}")
    log(f"FFmpeg={FFMPEG!r}; ffprobe={FFPROBE!r}")
    startup_paths = sys.argv[1:]
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setStyle("Fusion")
    app.setQuitOnLastWindowClosed(False)
    if not FFMPEG or not FFPROBE:
        QMessageBox.critical(
            None,
            APP_NAME,
            "FFmpeg was not found.\n\nInstall it so both ffmpeg and ffprobe are on PATH, then restart ClipTrim.",
        )
        return 1
    launcher = LauncherWindow()
    editor = MainWindow()

    def open_editor(paths: list[str]):
        if not editor.load_files(paths):
            launcher.show()
            launcher.raise_()
            launcher.activateWindow()
            return
        editor.show()
        editor.raise_()
        editor.activateWindow()
        launcher.hide()

    def back_to_launcher():
        editor.hide()
        launcher.show()
        launcher.raise_()
        launcher.activateWindow()

    sigint_pump = QTimer()
    sigint_pump.setInterval(100)
    sigint_pump.timeout.connect(lambda: None)
    sigint_pump.start()

    previous_sigint = signal.getsignal(signal.SIGINT)
    quit_after_export = False

    def request_clean_quit():
        nonlocal quit_after_export
        export_thread = editor.export_thread
        if export_thread and export_thread.isRunning():
            if not quit_after_export:
                quit_after_export = True
                export_thread.finished.connect(request_clean_quit)
                if not export_thread.isRunning():
                    QTimer.singleShot(0, request_clean_quit)
                log("Waiting for the active export before closing ClipTrim", "WARN")
            return
        editor._reset_scrub_state()
        editor._stop_scrub_cache()
        if editor._wait_for_retired_scrub_caches(1000):
            app.quit()
            return
        log("Waiting for a retired scrub-cache thread before quitting", "WARN")
        QTimer.singleShot(250, request_clean_quit)

    def handle_sigint(signum, frame):
        log("Ctrl+C received; requesting clean ClipTrim shutdown")
        request_clean_quit()

    signal.signal(signal.SIGINT, handle_sigint)
    launcher.filesChosen.connect(open_editor)
    launcher.quitRequested.connect(request_clean_quit)
    editor.backRequested.connect(back_to_launcher)
    editor.quitRequested.connect(request_clean_quit)

    def about_to_quit():
        log("Qt application shutdown requested", "DEBUG")
        try:
            editor.player.stop()
            editor._reset_scrub_state()
            editor._stop_scrub_cache()
            if not editor._wait_for_retired_scrub_caches(15000):
                log("A scrub-cache thread did not stop before Qt shutdown", "ERROR")
        except Exception as exc:
            log_exception("Error during Qt shutdown cleanup", exc)
        signal.signal(signal.SIGINT, previous_sigint)

    app.aboutToQuit.connect(about_to_quit)

    if startup_paths:
        log(f"Opening {len(startup_paths)} command-line path(s) directly")
        QTimer.singleShot(0, lambda paths=startup_paths: open_editor(paths))
    else:
        launcher.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
