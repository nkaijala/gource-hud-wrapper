# gource-hud-wrapper

Almost too horrible to publish. But hey the HUD is nice!

## Install & Run

- Dependencies: `gource`, `ffmpeg`, `ImageMagick`, `python3` (Debian/Ubuntu)
- Install (Debian/Ubuntu):
  - `sudo apt-get update`
  - `sudo apt-get install gource ffmpeg imagemagick python3`
- Optional (for ASS caption overlay mode): `sudo apt-get install libass9`

- Basic usage (Full HD default):
  - `./gource_anon_hud.sh /path/to/repo [output.mp4]`
- 4K/UHD output:
  - `./gource_anon_hud.sh --uhd /path/to/repo [output.mp4]`

- Recommended options:
  - Use a crisp monospaced font (optional):
    - `HUD_FONT_FILE=/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf ./gource_anon_hud.sh /repo`
  - Speed up overlay rendering (multi-core):
    - `HUD_JOBS=16 ./gource_anon_hud.sh /repo`

Notes
- The script anonymizes users and paths, preserves hierarchy, and renders a stable bottom-left HUD with rolling stats and live graphs.
- Gource’s top date/time HUD stays visible.
- Tunables (window length, speed, pause, etc.) live near the top of `gource_anon_hud.sh`.
