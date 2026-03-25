# Gource HUD Wrapper: Python Rewrite Design

## Overview

Rewrite the `gource_anon_hud.sh` bash/embedded-python script as a pure Python package (`gource_hud`) with clean module boundaries, full test coverage, and `pip install`-able CLI entry point.

**Scope:** PNG overlay mode only. Caption and ASS subtitle modes are dropped.

## Requirements

- 100% TDD
- Industry-standard Python project practices (pyproject.toml, pytest, src-less flat package)
- Host-machine gource and ffmpeg as runtime dependencies
- Pillow replaces ImageMagick for overlay rendering
- CLI flags with defaults (no config files)
- Anonymization on by default, `--no-anon` to disable

## Project Structure

```
gource_hud/
    __init__.py
    cli.py
    git_log.py
    stats.py
    overlay.py
    video.py
pyproject.toml
tests/
    test_git_log.py
    test_stats.py
    test_overlay.py
    test_video.py
```

After `pip install -e .`, users get a `gource-hud` command. Defaults to current directory if no repo path given.

## CLI Interface

```
gource-hud [options] [repo_path] [output.mp4]

Positional:
  repo_path              Git repo path (default: cwd)
  output                 Output file (default: {repo}/gource_anon_{W}x{H}_{timestamp}.mp4)

Resolution:
  --uhd / --4k           3840x2160 (default: 1920x1080)

Anonymization:
  --no-anon              Show real usernames and file paths

Tunables:
  --window WINDOW        Git log time window (default: "4 months ago")
  --speed SPEED          Seconds per simulated day (default: 0.5)
  --fps FPS              Video framerate (default: 60)
  --title TITLE          Video title (default: "Repository Activity")
  --tail-pause SECS      Linger on final frame (default: 4)
  --crf CRF              FFmpeg quality, lower=better (default: 18)

HUD appearance:
  --font-file PATH       Path to monospaced TTF/OTF font
  --font-size SIZE       Base font size at 1080p (default: 14)
  --panel-width WIDTH    Base panel width at 1080p (default: 640)
  --margin-left PX       Left margin (default: 28)
  --margin-bottom PX     Bottom margin (default: 80)

Performance:
  --jobs N               Overlay render workers (default: min(16, cpu_count*4))
```

---

## Module 1: `git_log.py` — Parsing & Anonymization

### Data Structures

```python
class FileStatus(Enum):
    ADDED = "A"
    MODIFIED = "M"
    DELETED = "D"
    TYPE_CHANGED = "T"
    RENAMED = "R"
    COPIED = "C"

@dataclass
class FileChange:
    path: str
    status: FileStatus
    adds: int
    deletes: int
    is_binary: bool
    old_path: Optional[str] = None
    rename_score: Optional[int] = None

@dataclass
class Commit:
    timestamp: int          # unix epoch seconds
    hash: str               # full SHA (40 or 64 hex chars)
    author_email: str
    files: list[FileChange]

    @property
    def day_epoch(self) -> int:
        return (self.timestamp // 86400) * 86400
```

### Parsing Strategy

Two `git log` subprocess calls (consolidated from the original three):

**Call A** (`--numstat`): `git log --since='{window}' --numstat --format='%ct%x09%H%x09%ae' --no-merges`
- Produces: timestamp, hash, author_email, then per-file adds/deletes/path lines
- Binary files appear as `-\t-\tpath`
- Renames appear with brace notation: `{old => new}` resolved via regex

**Call B** (`--name-status`): `git log --since='{window}' --name-status --format='%ct%x09%H' --no-merges`
- Produces: timestamp, hash, then per-file status/path lines
- Provides accurate A/M/D/R/C status that numstat alone cannot determine

**Merge:** Join by commit hash. Numstat provides LOC counts, name-status provides file status. Files appearing in only one call are handled defensively.

Both calls use `cwd=repo_path` — no shell injection risk.

### Parsing Algorithms

**Numstat parser** (`_parse_numstat_output`):
- Iterate lines, detect commit headers by: 3 tab-separated fields, first field all digits, second field is 40/64 hex chars
- Subsequent lines with 3+ tab-separated fields are numstat entries
- Binary files: `adds_str == '-'` and `dels_str == '-'` -> `is_binary=True, adds=0, deletes=0`
- Rename resolution: regex `r'\{([^}]*) => ([^}]*)\}'` handles `prefix/{old => new}/suffix`; fallback split on ` => ` for simple renames

**Name-status parser** (`_parse_name_status_output`):
- Commit headers: 2 tab-separated fields (timestamp, hash)
- File entries: status code + path(s). `R100\told\tnew` and `C075\told\tnew` parsed for score and both paths
- Unknown status codes silently skipped

**Merge** (`_merge_commits`):
- Index both parsed results by hash
- Union of all hashes (defensive: handles commits appearing in only one call)
- For each hash: combine numstat LOC data with name-status file status
- Sort output by `(timestamp, hash)` for determinism

### Anonymization

Stateful `Anonymizer` class with deterministic first-seen ordering:

```python
class Anonymizer:
    def anonymize_author(self, email: str) -> str:
        # First seen -> Dev_1, second -> Dev_2, etc.

    def anonymize_path(self, path: str) -> str:
        # Directory segments -> d0001, d0002, ...
        # Filename bases -> f0001, f0002, ...
        # Extensions preserved
        # Dotfiles (.gitignore): entire name is base, no extension

    def anonymize_commits(self, commits: list[Commit]) -> list[AnonymizedCommit]:
        # Must receive timestamp-sorted input for deterministic assignment
```

Path anonymization preserves:
- Directory hierarchy depth
- File extensions (last dot only: `file.test.py` -> `f0001.py`)
- Shared segments reuse tokens (`src/a.py` and `src/b.py` share `d0001`)

### Gource Log Output

The anonymized (or raw) commit data is written as a gource custom log file:
```
timestamp|author|action|path
```
Where action is A/M/D derived from FileStatus.

### Edge Cases

| Case | Handling |
|------|----------|
| Binary files | `adds=0, deletes=0, is_binary=True` |
| Rename brace notation | Regex resolution to new path |
| Empty commits | Valid commit with empty files list |
| Dotfiles (`.gitignore`) | No extension, entire name is base |
| Double extensions (`file.test.py`) | Last dot defines extension |
| Paths with spaces | Tab delimiters, not affected |
| Non-UTF-8 paths | `errors='replace'` fallback |

### Test Cases

1. Basic commit parsing (1 commit, 2 files)
2. Multiple commits back-to-back
3. Binary file handling
4. Rename brace notation resolution
5. Simple rename resolution
6. Empty commit (header only)
7. Name-status A/M/D/R/C parsing
8. Merge: same hash in both calls
9. Merge: file in name-status but not numstat
10. Merge: output sorted by timestamp
11. Anonymizer: deterministic author mapping
12. Anonymizer: path structure preservation
13. Anonymizer: shared directory segments
14. Anonymizer: dotfile handling
15. Anonymizer: deeply nested paths
16. Anonymizer: rename old_path anonymized
17. Empty input -> empty output
18. Round-trip: parse + anonymize produces valid tokens only

---

## Module 2: `stats.py` — Metrics Computation

### Day Bucketing

```python
@dataclass
class DayBucket:
    timestamp: int
    loc_added: int
    loc_deleted: int
    commit_count: int
    authors: set[str]
    files_changed: set[str]
    files_added_count: int
    files_deleted_count: int

def bucket_commits(commits: list[Commit]) -> tuple[list[int], dict[int, DayBucket]]:
    # Floor timestamps to midnight UTC
    # Fill gaps so every day in min..max range has an entry
    # Returns (sorted_days, buckets_by_day)
```

Complexity: O(C + F + D) where C=commits, F=file changes, D=days in range.

### Rolling Window Functions

**Rolling sum** (for LOC, commits, files added/deleted):
```python
def rolling_sum(days: list[int], values: dict[int, int], window_seconds: int) -> dict[int, int]:
```
Deque-based sliding window. O(n) amortized. Each element enters/leaves the deque exactly once.

Window sizes: 1d (86400s), 7d (604800s), 30d (2592000s).

**Rolling unique count** (for authors, files changed):
```python
def rolling_unique_count(days: list[int], sets_by_day: dict[int, set[str]], window_seconds: int) -> dict[int, int]:
```
Counter-based approach: maintain `Counter[element -> days_active_in_window]`. On new day: increment for each element. On eviction: decrement, delete at zero. Unique count = `len(counter)`.

O(n * s_avg) amortized, vs O(n * w * s_avg) for the naive union-recompute approach.

**Why Counter beats naive union:** When removing a day from the window, you can't simply subtract its set from the union — an element might appear on other days still in the window. The Counter tracks how many in-window days each element appears on, so decrement-and-delete-at-zero is correct.

### Running Maxima

```python
def running_maxima(days: list[int], values: dict[int, int]) -> dict[int, int]:
```
Single forward pass: `max_so_far = max(max_so_far, current)`. O(n).

Applied to LOC total (adds+deletes) for 1d, 7d, 30d rolling sums.

### Cumulative Series

```python
def cumulative_series(days: list[int], values: dict[int, int]) -> dict[int, int]:
```
Prefix sum. O(n). Used for:
- Cumulative LOC delta (adds - deletes per day, running sum)
- Cumulative files delta (files added - files deleted per day, running sum)

### Derived Metrics

**Churn percentage:** `round(100 * deletes / (adds + deletes))`, 0 when total is 0. Domain: [0, 100].

**Efficiency percentage:** `round(100 * (adds - deletes) / (adds + deletes))`, 0 when total is 0. Domain: [-100, +100].

**Week-over-week trend deltas:** `values[i] - values[i-7]`, 0 when `i < 7`. Formatted as arrows: `"▲ +N"` / `"▼ N"` / `"– 0"`.

**Language mix (7d):** Counter-based sliding window over `lang_loc_day[day][language] -> loc`. Top 3 by LOC share, percentage rounded.

Extension-to-language mapping covers: Python, TypeScript, JavaScript, Go, Rust, Java, Kotlin, Ruby, PHP, C, C++, C#, Swift, Obj-C, Shell, YAML, JSON, TOML, Markdown, SQL, R, Julia, Scala. Unknown -> "other".

**Change size distribution (7d):** Per-commit size = adds + deletes. Collect sizes in 7d window, compute median and p90 via linear interpolation:
```
k = (n-1) * p
f, c = floor(k), ceil(k)
result = round(v[f] * (c-k) + v[c] * (k-f))   # or v[k] if f==c
```

### Percentile Function

```python
def percentile(sorted_values: list[int], p: float) -> int:
```
Linear interpolation matching numpy's default method. Returns 0 for empty input.

### Output Data Structure

```python
@dataclass
class DayMetrics:
    timestamp: int
    # LOC 1d/7d/30d added/deleted
    # Commits 1d/7d/30d
    # Authors 1d/7d/30d (unique count)
    # Files changed 1d/7d/30d (unique count)
    # Files added/deleted 1d/7d/30d
    # Running maxima 1d/7d/30d
    # Cumulative LOC delta, cumulative files delta
    # Churn 7d/30d, efficiency 7d/30d
    # WoW trend deltas and arrows
    # Language mix 7d (top 3)
    # Change size median/p90 7d
```

### Top-Level Orchestrator

```python
def compute_all_metrics(commits: list[Commit]) -> list[DayMetrics]:
```
Buckets commits, computes all rolling windows, derives all metrics, returns chronologically ordered list. Empty input -> empty output.

### Test Cases

1. 3-day single author: verify all 1d/7d/30d sums, running max, cumulative series
2. Gap filling: 2 commits 3 days apart, verify zero-filled days
3. Multiple authors with window eviction: verify Counter-based unique count after 7d eviction
4. Empty input: returns empty list
5. Single day: all windows degenerate to same value
6. Window larger than data: 30d window on 5 days of data, no eviction occurs
7. Churn/efficiency edge cases: zero total, pure adds, pure deletes, even split
8. WoW deltas: known 8-day series, verify delta at day 7
9. Language mix: 8-day series with eviction, verify top-3 percentages
10. Percentile: comprehensive cases matching numpy reference values
11. Change size distribution: 3-day known values, verify median and p90

---

## Module 3: `overlay.py` — Pillow-Based Overlay Rendering

### Public API

```python
def render_overlays(
    day_data: list[DayMetrics],
    output_dir: str,
    width: int,
    height: int,
    font_path: str | None = None,
    panel_width: int = 640,
    jobs: int = 0,
    scale: float = 1.0,
) -> int:  # returns frame count
```

### Layout Computation

All pixel values scale by factor S (1.0 for 1080p, 2.0 for 4K).

```
font_size = 14 * S
line_gap = int(font_size * 1.35)
pad_x = 16 * S
pad_y = 12 * S
graph_h = 140 * S
graph_gap = 14 * S
panel_w = panel_width * S

panel_h = pad_y + (13 * line_gap) + graph_gap + (3 * graph_h) + (2 * graph_gap) + pad_y
```

At 1080p: panel_h = 12 + 234 + 14 + 420 + 28 + 12 = 720px.

Panel is flush bottom-left:
```
rect = (0, frame_h - panel_h, panel_w, frame_h)
```

Three graphs stacked bottom-up inside the panel, each `graph_h` tall with `graph_gap` spacing.

### Text Content (13 Lines)

```
LOC 1d  +{adds}  -{dels}   (Net {net})
LOC 7d  +{adds}  -{dels}   (Net {net})
LOC 30d +{adds}  -{dels}   (Net {net})
Peaks   Max1d {m1}  •  Max7d {m7}  •  Max30d {m30}
Commits 1d {c1}  •  7d {c7}  •  30d {c30}
Authors 1d {u1}  •  7d {u7}  •  30d {u30}
FilesΔ  1d {f1}  •  7d {f7}  •  30d {f30}
Files A/D  1d +{a}/-{d}  •  7d +{a}/-{d}  •  30d +{a}/-{d}
Churn 7d {c}%  •  30d {c}%
Efficiency 7d {e}%  •  30d {e}%
Trends 7d  LOC {arrow}  •  Commits {arrow}  •  FilesΔ {arrow}
Lang 7d  {lang1} {pct}% {lang2} {pct}% {lang3} {pct}%
Change Size 7d  median {med}  •  p90 {p90}
```

Numbers right-justified with thousands separators, column widths precomputed across all days to prevent horizontal jumping.

### Graph Rendering

Three graphs, each with polylines drawn progressively (frame N shows points 0..N):

1. **Total LOC (Δ)** — white polyline, cumulative (adds-deletes)
2. **Files (Δ)** — cyan (#00FFFF) polyline, cumulative (files_added - files_deleted)
3. **+Adds / -Deletes (7d)** — green (#00FF66) + red (#FF5555) polylines

Graph borders: thin white at 40% opacity. Labels inside top-left of each box.

**Peak markers** on LOC graph: gold (#FFD700) circle for new Max7d, magenta (#FF00FF) for new Max30d.

**Polyline points precomputed once** as full-length arrays. Each worker slices `[:i+1]`.

### Pillow Drawing Sequence Per Frame

1. `Image.new('RGBA', (W, H), (0,0,0,0))` — transparent canvas
2. `draw.rectangle(...)` — panel background (0,0,0,140 alpha)
3. `draw.rectangle(...) x3` — graph borders
4. `draw.text(...) x13` — stat lines (white, dark stroke outline)
5. `draw.text(...) x3` — graph labels
6. `draw.line(...) x1-4` — polylines (sliced to frame index)
7. `draw.ellipse(...) x0-2` — peak markers
8. `im.save(path, 'PNG')`

### Font Loading

Search order for monospaced fonts:
1. User-provided `--font-file` (error if path doesn't exist)
2. Auto-detect from common system paths: DejaVu Sans Mono, Liberation Mono, Noto Sans Mono, Ubuntu Mono, FreeMono, Menlo, Consolas

`RuntimeError` if no font found.

### Concurrent Rendering

`ThreadPoolExecutor` with `min(16, cpu_count * 4)` workers (overridable via `--jobs`). Progress reported to stderr.

Precomputed before dispatch: layout metrics, format widths, text lines, graph point arrays, peak marker booleans. Workers do only Pillow draw + save.

### Test Cases

1. Layout math at 1080p: verify all coordinates
2. Layout math at 4K: verify scaling
3. Text doesn't overlap graph 1 top edge
4. Graph boxes don't overlap each other
5. Panel fits within frame
6. Thousands separator formatting
7. Right-justification consistency across days
8. Cumulative series computation and range clamping
9. Peak marker detection (boolean arrays)
10. Polyline X-spacing for known day counts
11. Polyline Y-normalization for known values
12. Output PNG is RGBA with correct dimensions
13. Panel region has non-zero alpha
14. Outside-panel region is fully transparent
15. Empty day_data: returns 0, no files created
16. Single day: 1 frame, no polylines (need >=2 points)
17. Font detection: finds installed font / raises on missing

---

## Module 4: `video.py` — Pipeline Orchestration

### Public API

```python
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
    # Raises DependencyError if gource/ffmpeg not on PATH

def render_video(config: VideoConfig) -> Path:
    # Returns output path on success
```

### Pipeline Design

Two subprocesses piped together:

```
gource --output-ppm-stream - | ffmpeg -f image2pipe -i - -i overlay_%05d.png ...
```

Implemented with `subprocess.Popen`:
1. Launch gource with `stdout=PIPE`
2. Launch ffmpeg with `stdin=gource.stdout`
3. **Critical:** Close `gource.stdout` in parent process so ffmpeg sees EOF when gource exits
4. Stream ffmpeg stderr for progress
5. Wait for both, raise `RenderError` on non-zero exit

### Gource Command

```
gource --log-format custom {log_file}
       --hide usernames,filenames,dirnames
       --seconds-per-day {speed}
       --camera-mode overview --stop-at-end
       --title "{title}" -{W}x{H}
       --output-ppm-stream -
```

No `--auto-skip-seconds` — linear time required for overlay sync.

### FFmpeg Command

```
ffmpeg -y -hide_banner -loglevel error
       -r {fps} -f image2pipe -vcodec ppm -i -
       -framerate {1/speed} -start_number 0 -i {overlay_dir}/overlay_%05d.png
       -filter_complex "[0:v]fps={fps},settb=AVTB,setpts=N/({fps}*TB)[bg];
                        [1:v]fps={fps},format=rgba,settb=AVTB,setpts=N/({fps}*TB)[ov];
                        [bg][ov]overlay=x=0:y=0:format=auto,
                        tpad=stop_mode=clone:stop_duration={tail_pause}"
       -pix_fmt yuv420p -movflags +faststart -crf {crf} {output}
```

### Signal Handling

Custom SIGINT/SIGTERM handler terminates both subprocesses. `finally` block kills+waits as fallback. Original handlers restored after pipeline completes.

### Error Handling

- **Pre-flight:** Dependency check, log file exists, overlay dir exists and non-empty, output parent dir created
- **Runtime:** Gource stderr captured for error messages. FFmpeg last 20 stderr lines included in `RenderError`.
- **Exceptions:** `DependencyError` (tool not found), `RenderError` (subprocess failure), `FileNotFoundError` (missing inputs)

### Output Path Default

If not provided: `{repo}/gource_anon_{W}x{H}_{YYYYMMDD_HHMMSS}.mp4`

### Test Cases

1. `_build_gource_cmd`: correct flags for default and custom configs
2. `_build_ffmpeg_cmd`: filter_complex string, overlay fps = 1/speed
3. `_count_overlay_frames`: correct count, ignores non-matching files
4. `check_dependencies`: raises when tools missing (mock `shutil.which`)
5. Integration: tiny end-to-end render with minimal log + solid-color overlays, verify valid MP4 via ffprobe (requires gource+ffmpeg installed, skip in CI if absent)

---

## Module 5: `cli.py` — Entry Point

### Responsibilities

1. Parse CLI args via argparse
2. Validate repo path (default to cwd, must be git repo)
3. Create temp directory (context manager, auto-cleanup)
4. Orchestrate: parse git log -> (optionally anonymize) -> compute stats -> render overlays -> render video
5. Print output path on success

### Flow

```
def main():
    args = parse_args()
    repo = resolve_repo(args.repo)
    check_dependencies()
    with tempfile.TemporaryDirectory() as tmpdir:
        commits = parse_git_log(repo, args.window)
        if not args.no_anon:
            anonymizer = Anonymizer()
            commits = anonymizer.anonymize_commits(commits)
        write_gource_log(commits, tmpdir / "repo.log")
        metrics = compute_all_metrics(commits)
        render_overlays(metrics, tmpdir, args.width, args.height, ...)
        render_video(VideoConfig(...))
    print(f"Wrote: {output_path}")
```

---

## Dependencies

### Runtime
- Python >= 3.10
- `pillow` (PyPI)
- `gource` (system)
- `ffmpeg` (system)

### Development
- `pytest`

### pyproject.toml

```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.backends._legacy:_Backend"

[project]
name = "gource-hud"
version = "0.1.0"
requires-python = ">=3.10"
dependencies = ["pillow"]

[project.optional-dependencies]
dev = ["pytest"]

[project.scripts]
gource-hud = "gource_hud.cli:main"
```

---

## Differences from Original Script

| Aspect | Original | Rewrite |
|--------|----------|---------|
| Language | Bash + inline Python + awk | Pure Python |
| HUD modes | caption, ASS, PNG | PNG only |
| Image rendering | ImageMagick subprocess | Pillow in-process |
| Git log calls | 3 | 2 |
| Rolling set-union | Naive O(n*w) union-recompute | Counter-based O(n) |
| Rolling sum | `list.pop(0)` O(n) per pop | `deque.popleft()` O(1) |
| Anonymization | awk inline | Python class, deterministic |
| Anonymization toggle | Always on | Default on, `--no-anon` flag |
| Repo path | Required argument | Optional, defaults to cwd |
| Configuration | Bash variables + env vars | CLI flags with defaults |
| Testing | None | 100% TDD with pytest |
| Installation | Copy script | `pip install` |
