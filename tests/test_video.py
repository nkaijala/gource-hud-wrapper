# tests/test_video.py
import shutil
from pathlib import Path
from unittest.mock import patch
from gource_hud.video import (
    VideoConfig, DependencyError, RenderError,
    check_dependencies, _build_gource_cmd, _build_ffmpeg_cmd,
    _count_overlay_frames,
)

class TestVideoConfig:
    def test_defaults(self):
        c = VideoConfig(log_file=Path("/tmp/log"), overlay_dir=Path("/tmp/ovr"), output_path=Path("/tmp/out.mp4"))
        assert c.fps == 60
        assert c.seconds_per_day == 0.5
        assert c.crf == 18

class TestCheckDependencies:
    def test_raises_when_gource_missing(self):
        import pytest
        with patch("shutil.which", side_effect=lambda t: None if t == "gource" else "/usr/bin/ffmpeg"):
            with pytest.raises(DependencyError, match="gource"):
                check_dependencies()
    def test_raises_when_ffmpeg_missing(self):
        import pytest
        with patch("shutil.which", side_effect=lambda t: None if t == "ffmpeg" else "/usr/bin/gource"):
            with pytest.raises(DependencyError, match="ffmpeg"):
                check_dependencies()

class TestBuildGourceCmd:
    def test_default_config(self):
        c = VideoConfig(Path("/tmp/log"), Path("/tmp/ovr"), Path("/tmp/out.mp4"))
        cmd = _build_gource_cmd(c)
        assert "gource" == cmd[0]
        assert "--log-format" in cmd
        assert "--output-ppm-stream" in cmd
        assert "-1920x1080" in cmd
        assert "--auto-skip-seconds" not in " ".join(cmd)
    def test_uhd_config(self):
        c = VideoConfig(Path("/tmp/log"), Path("/tmp/ovr"), Path("/tmp/out.mp4"), width=3840, height=2160)
        cmd = _build_gource_cmd(c)
        assert "-3840x2160" in cmd

class TestBuildFfmpegCmd:
    def test_overlay_fps(self):
        c = VideoConfig(Path("/tmp/log"), Path("/tmp/ovr"), Path("/tmp/out.mp4"), seconds_per_day=0.5)
        cmd = _build_ffmpeg_cmd(c, overlay_fps=2.0)
        cmd_str = " ".join(cmd)
        assert "-framerate" in cmd_str
        assert "2.0" in cmd_str
    def test_filter_complex_content(self):
        c = VideoConfig(Path("/tmp/log"), Path("/tmp/ovr"), Path("/tmp/out.mp4"), fps=60, tail_pause=4.0)
        cmd = _build_ffmpeg_cmd(c, overlay_fps=2.0)
        fc_idx = cmd.index("-filter_complex") + 1
        fc = cmd[fc_idx]
        assert "fps=60" in fc
        assert "overlay=x=0:y=0:format=auto" in fc
        assert "tpad=stop_mode=clone:stop_duration=4.0" in fc
    def test_crf_value(self):
        c = VideoConfig(Path("/tmp/log"), Path("/tmp/ovr"), Path("/tmp/out.mp4"), crf=22)
        cmd = _build_ffmpeg_cmd(c, overlay_fps=2.0)
        assert "22" in cmd

class TestCountOverlayFrames:
    def test_counts_correctly(self, tmp_path):
        for i in range(5):
            (tmp_path / f"overlay_{i:05d}.png").touch()
        (tmp_path / "other.txt").touch()
        assert _count_overlay_frames(tmp_path) == 5
    def test_empty_dir(self, tmp_path):
        assert _count_overlay_frames(tmp_path) == 0
