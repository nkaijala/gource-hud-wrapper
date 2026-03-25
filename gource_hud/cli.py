# gource_hud/cli.py
from __future__ import annotations
import argparse
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from gource_hud.git_log import Anonymizer, parse_git_log, write_gource_log
from gource_hud.overlay import render_overlays
from gource_hud.stats import compute_all_metrics
from gource_hud.video import VideoConfig, check_dependencies, render_video

def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="gource-hud", description="Generate a gource visualization with a rich HUD overlay.")
    p.add_argument("repo", nargs="?", default=None, help="Git repo path (default: cwd)")
    p.add_argument("output", nargs="?", default=None, help="Output .mp4 path")
    res = p.add_argument_group("resolution")
    res.add_argument("--uhd", "--4k", action="store_true", default=False, help="3840x2160")
    res.add_argument("--fhd", action="store_true", default=False, help="1920x1080 (default, no-op)")
    p.add_argument("--no-anon", action="store_true", default=False, help="Show real names/paths")
    tun = p.add_argument_group("tunables")
    tun.add_argument("--window", default="4 months ago", help="Git log time window")
    tun.add_argument("--speed", type=float, default=0.5, help="Seconds per simulated day")
    tun.add_argument("--fps", type=int, default=60)
    tun.add_argument("--title", default="Repository Activity")
    tun.add_argument("--tail-pause", type=float, default=4.0)
    tun.add_argument("--crf", type=int, default=18)
    hud = p.add_argument_group("HUD appearance")
    hud.add_argument("--font-file", default=None)
    hud.add_argument("--font-size", type=int, default=14)
    hud.add_argument("--panel-width", type=int, default=640)
    p.add_argument("--jobs", type=int, default=0)
    return p.parse_args(argv)

def main() -> None:
    args = parse_args()
    repo_path = args.repo or "."
    repo = Path(repo_path).resolve()
    if not (repo / ".git").is_dir():
        print(f"Not a git repo: {repo}", file=sys.stderr)
        sys.exit(1)
    width = 3840 if args.uhd else 1920
    height = 2160 if args.uhd else 1080
    scale = 2.0 if args.uhd else 1.0
    if args.output:
        output_path = Path(args.output).resolve()
    else:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = repo / f"gource_anon_{width}x{height}_{ts}.mp4"
    check_dependencies()
    with tempfile.TemporaryDirectory(prefix="gource_hud_") as tmpdir:
        tmp = Path(tmpdir)
        print("Parsing git log...", file=sys.stderr)
        commits = parse_git_log(str(repo), args.window)
        if not commits:
            print("No commits found in the given time window.", file=sys.stderr)
            sys.exit(1)
        if not args.no_anon:
            print("Anonymizing...", file=sys.stderr)
            anonymizer = Anonymizer()
            commits = anonymizer.anonymize_commits(commits)
        log_file = tmp / "repo.anon.log"
        write_gource_log(commits, log_file)
        print("Computing stats...", file=sys.stderr)
        metrics = compute_all_metrics(commits)
        print("Rendering overlays...", file=sys.stderr)
        render_overlays(
            metrics, str(tmp), width, height,
            font_path=args.font_file, panel_width=args.panel_width,
            font_size=args.font_size, jobs=args.jobs, scale=scale,
        )
        print("Rendering video...", file=sys.stderr)
        config = VideoConfig(
            log_file=log_file, overlay_dir=tmp, output_path=output_path,
            width=width, height=height, fps=args.fps,
            seconds_per_day=args.speed, title=args.title,
            tail_pause=args.tail_pause, crf=args.crf,
        )
        render_video(config)
    print(f"Wrote: {output_path}")
