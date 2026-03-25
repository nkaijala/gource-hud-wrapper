# gource_hud/video.py
from __future__ import annotations
import os
import shutil
import signal
import subprocess
from dataclasses import dataclass
from pathlib import Path

class DependencyError(RuntimeError):
    pass

class RenderError(RuntimeError):
    pass

@dataclass
class VideoConfig:
    log_file: Path
    overlay_dir: Path
    output_path: Path
    width: int = 1920
    height: int = 1080
    fps: int = 60
    seconds_per_day: float = 0.5
    title: str = "Repository Activity"
    tail_pause: float = 4.0
    crf: int = 18

def check_dependencies() -> None:
    for tool in ("gource", "ffmpeg"):
        if shutil.which(tool) is None:
            raise DependencyError(f"'{tool}' not found on PATH. Install it: sudo apt-get install {tool}")

def _build_gource_cmd(config: VideoConfig) -> list[str]:
    return [
        "gource", "--log-format", "custom", str(config.log_file),
        "--hide", "usernames,filenames,dirnames",
        "--seconds-per-day", str(config.seconds_per_day),
        "--camera-mode", "overview", "--stop-at-end",
        "--title", config.title,
        f"-{config.width}x{config.height}",
        "--output-ppm-stream", "-",
    ]

def _build_ffmpeg_cmd(config: VideoConfig, overlay_fps: float) -> list[str]:
    fps = config.fps
    filter_complex = (
        f"[0:v]fps={fps},settb=AVTB,setpts=N/({fps}*TB)[bg];"
        f"[1:v]fps={fps},format=rgba,settb=AVTB,setpts=N/({fps}*TB)[ov];"
        f"[bg][ov]overlay=x=0:y=0:format=auto,"
        f"tpad=stop_mode=clone:stop_duration={config.tail_pause}"
    )
    return [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-r", str(fps), "-f", "image2pipe", "-vcodec", "ppm", "-i", "-",
        "-framerate", str(overlay_fps), "-start_number", "0",
        "-i", str(config.overlay_dir / "overlay_%05d.png"),
        "-filter_complex", filter_complex,
        "-pix_fmt", "yuv420p", "-movflags", "+faststart",
        "-crf", str(config.crf), str(config.output_path),
    ]

def _count_overlay_frames(overlay_dir: Path) -> int:
    return len(list(overlay_dir.glob("overlay_*.png")))

def render_video(config: VideoConfig) -> Path:
    check_dependencies()
    if not config.log_file.exists():
        raise FileNotFoundError(f"Log file not found: {config.log_file}")
    if not config.overlay_dir.is_dir():
        raise FileNotFoundError(f"Overlay directory not found: {config.overlay_dir}")
    frame_count = _count_overlay_frames(config.overlay_dir)
    if frame_count == 0:
        raise FileNotFoundError(f"No overlay_*.png files in {config.overlay_dir}")
    config.output_path.parent.mkdir(parents=True, exist_ok=True)
    overlay_fps = 1.0 / config.seconds_per_day
    gource_cmd = _build_gource_cmd(config)
    ffmpeg_cmd = _build_ffmpeg_cmd(config, overlay_fps)
    gource_proc = None
    ffmpeg_proc = None
    original_sigint = signal.getsignal(signal.SIGINT)
    original_sigterm = signal.getsignal(signal.SIGTERM)
    def _cleanup_handler(signum, frame):
        for proc in (gource_proc, ffmpeg_proc):
            if proc and proc.poll() is None:
                proc.terminate()
        signal.signal(signum, signal.SIG_DFL)
        os.kill(os.getpid(), signum)
    try:
        signal.signal(signal.SIGINT, _cleanup_handler)
        signal.signal(signal.SIGTERM, _cleanup_handler)
        gource_proc = subprocess.Popen(gource_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        ffmpeg_proc = subprocess.Popen(ffmpeg_cmd, stdin=gource_proc.stdout, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        gource_proc.stdout.close()
        ffmpeg_stderr_lines = []
        for line in ffmpeg_proc.stderr:
            decoded = line.decode("utf-8", errors="replace").rstrip()
            ffmpeg_stderr_lines.append(decoded)
        ffmpeg_rc = ffmpeg_proc.wait()
        gource_rc = gource_proc.wait()
        gource_stderr = gource_proc.stderr.read().decode("utf-8", errors="replace")
        if gource_rc != 0:
            raise RenderError(f"gource failed (exit {gource_rc}):\n{gource_stderr}")
        if ffmpeg_rc != 0:
            raise RenderError(f"ffmpeg failed (exit {ffmpeg_rc}):\n" + "\n".join(ffmpeg_stderr_lines[-20:]))
    finally:
        signal.signal(signal.SIGINT, original_sigint)
        signal.signal(signal.SIGTERM, original_sigterm)
        for proc in (gource_proc, ffmpeg_proc):
            if proc and proc.poll() is None:
                proc.kill()
                proc.wait()
    return config.output_path
