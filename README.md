# gource-hud

Generate gource visualizations with a rich stats HUD overlay.

Anonymizes users and paths by default, renders a bottom-left panel with rolling metrics (1d/7d/30d) and live graphs, then composites everything into a single MP4.

## Install

Requires `gource` and `ffmpeg` on your system:

```bash
# Debian/Ubuntu
sudo apt-get install gource ffmpeg

# macOS
brew install gource ffmpeg
```

Then install gource-hud:

```bash
uv tool install .
# or
pip install .
```

## Usage

```bash
# From inside a git repo (FHD, anonymized)
gource-hud

# Point at a repo, specify output
gource-hud /path/to/repo output.mp4

# 4K output
gource-hud --uhd

# Show real usernames and file paths
gource-hud --no-anon

# Custom time window and speed
gource-hud --window "6 months ago" --speed 0.3
```

## Options

```
gource-hud [options] [repo] [output.mp4]

Resolution:
  --uhd, --4k           3840x2160 (default: 1920x1080)

Anonymization:
  --no-anon             Show real usernames and file paths

Tunables:
  --window WINDOW       Git log time window (default: "4 months ago")
  --speed SPEED         Seconds per simulated day (default: 0.5)
  --fps FPS             Video framerate (default: 60)
  --title TITLE         Video title (default: "Repository Activity")
  --tail-pause SECS     Linger on final frame (default: 4)
  --crf CRF             FFmpeg quality, lower=better (default: 18)

HUD appearance:
  --font-file PATH      Path to a monospaced TTF/OTF font
  --font-size SIZE      Base font size at 1080p (default: 14)
  --panel-width WIDTH   HUD panel width at 1080p (default: 640)

Performance:
  --jobs N              Overlay render workers (default: auto)
```

## What the HUD shows

- LOC added/deleted with net (1d, 7d, 30d rolling windows)
- Peak LOC activity (running maxima)
- Commit count and unique author count
- Files changed, added, deleted
- Churn and efficiency percentages
- Week-over-week trend arrows
- Top 3 languages by LOC share (7d)
- Change size distribution (median, p90)
- Three live graphs: cumulative LOC delta, cumulative files delta, 7d add/delete flow
- Peak markers on the LOC graph: gold dot = new 7d record, magenta dot = new 30d record

## Development

```bash
pip install -e ".[dev]"
pytest
```
