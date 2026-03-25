# tests/test_cli.py
from gource_hud.cli import parse_args

class TestParseArgs:
    def test_defaults(self):
        args = parse_args([])
        assert args.repo is None
        assert args.output is None
        assert args.no_anon is False
        assert args.speed == 0.5
        assert args.fps == 60
        assert args.window == "4 months ago"
        assert args.uhd is False
    def test_repo_path(self):
        args = parse_args(["/some/repo"])
        assert args.repo == "/some/repo"
    def test_repo_and_output(self):
        args = parse_args(["/some/repo", "out.mp4"])
        assert args.repo == "/some/repo"
        assert args.output == "out.mp4"
    def test_uhd_flag(self):
        args = parse_args(["--uhd"])
        assert args.uhd is True
    def test_4k_alias(self):
        args = parse_args(["--4k"])
        assert args.uhd is True
    def test_fhd_no_op(self):
        args = parse_args(["--fhd"])
        assert args.uhd is False
    def test_no_anon(self):
        args = parse_args(["--no-anon"])
        assert args.no_anon is True
    def test_tunables(self):
        args = parse_args(["--speed", "0.3", "--fps", "30", "--crf", "22"])
        assert args.speed == 0.3
        assert args.fps == 30
        assert args.crf == 22
