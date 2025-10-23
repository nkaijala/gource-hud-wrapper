#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 [/flags] /path/to/repo [output.mp4]"
  echo "Flags: --uhd | --4k (3840x2160), --fhd (1920x1080 default)"
  exit 1
fi

# parse flags + positional args
PRESET="fhd"
REPO=""
OUT=""
for arg in "$@"; do
  case "$arg" in
    --uhd|--4k) PRESET="uhd" ;;
    --fhd) PRESET="fhd" ;;
    --*) ;; # ignore unknown flags
    *)
      if [[ -z "$REPO" ]]; then REPO="$(realpath "$arg")"; continue; fi
      if [[ -z "$OUT" ]]; then OUT="$arg"; continue; fi
      ;;
  esac
done

[[ -d "$REPO/.git" ]] || { echo "Not a git repo: $REPO"; exit 1; }

# -------- tunables (change if you like) --------
WINDOW="4 months ago"       # repo age < 4 months
SPD=0.5                     # seconds per simulated day (~60s for ~120 days)
FPS=60
RES_W=1920
RES_H=1080
CAPTION_SIZE=32
TITLE="Repository Activity (last 4 months)"

# HUD rendering mode:
#  - png: left-side, multiline, non-blinking (per-day PNG overlays via ffmpeg)
#  - overlay: left-side, multiline (ffmpeg+libass)
#  - caption: single-line, centered (Gource captions)
HUD_MODE="png"

# Overlay HUD appearance (overlay/png modes)
HUD_FONT="DejaVu Sans Mono"   # font family name (fallback if file not found)
HUD_FONT_FILE=""              # optional absolute path to a TTF/OTF file
HUD_FONT_SIZE=14
HUD_MARGIN_L=28    # px from left
HUD_MARGIN_T=80    # px from top (used by overlay/ass when top-aligned)
HUD_MARGIN_B=80    # px from bottom (used by PNG overlay bottom-aligned)
# PNG panel width (px)
HUD_PANEL_W=640
# Pause at end (seconds) to linger on final frame
TAIL_PAUSE=4
# ----------------------------------------------

timestamp() { date +"%Y%m%d_%H%M%S"; }
# apply resolution preset
case "$PRESET" in
  uhd)
    RES_W=3840; RES_H=2160 ;;
  *)
    RES_W=1920; RES_H=1080 ;;
esac

# scale-dependent UI params
SCALE=1
if [[ "$PRESET" == "uhd" ]]; then SCALE=2; fi

HUD_FONT_SIZE_EFF=$(( HUD_FONT_SIZE * SCALE ))
HUD_MARGIN_L_EFF=$(( HUD_MARGIN_L * SCALE ))
HUD_MARGIN_T_EFF=$(( HUD_MARGIN_T * SCALE ))
HUD_MARGIN_B_EFF=$(( HUD_MARGIN_B * SCALE ))
HUD_PANEL_W_EFF=$(( HUD_PANEL_W * SCALE ))
CAPTION_SIZE_EFF=$(( CAPTION_SIZE * SCALE ))

[[ -n "$OUT" ]] || OUT="$REPO/gource_anon_${RES_W}x${RES_H}_$(timestamp).mp4"

TMPDIR="$(mktemp -d)"
cleanup(){ rm -rf "$TMPDIR"; }
trap cleanup EXIT

# deps check
command -v gource >/dev/null || { echo "gource not found"; exit 1; }
command -v ffmpeg >/dev/null || { echo "ffmpeg not found"; exit 1; }
command -v python3 >/dev/null || { echo "python3 not found"; exit 1; }
if [[ "$HUD_MODE" == "png" ]]; then
  if command -v magick >/dev/null; then IM_CMD="magick"; elif command -v convert >/dev/null; then IM_CMD="convert"; else echo "ImageMagick not found (magick/convert) required for HUD_MODE=png"; exit 1; fi
  # try to resolve a usable monospaced font file if HUD_FONT_FILE is not set
  if [[ -z "${HUD_FONT_FILE}" || ! -f "${HUD_FONT_FILE}" ]]; then
    for fp in \
      /usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf \
      /usr/share/fonts/dejavu/DejaVuSansMono.ttf \
      /usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf \
      /usr/share/fonts/truetype/noto/NotoSansMono-Regular.ttf \
      /usr/share/fonts/truetype/ubuntu/UbuntuMono-R.ttf \
      /usr/share/fonts/truetype/freefont/FreeMono.ttf; do
      if [[ -f "$fp" ]]; then HUD_FONT_FILE="$fp"; break; fi
    done
  fi
fi

pushd "$REPO" >/dev/null

# --- compute window start ---
SINCE_EPOCH="$(date -d "$WINDOW" +%s)"

# --- 1) anonymized, segment-preserving custom log ---
gource --output-custom-log - \
| awk -F'|' -v since="$SINCE_EPOCH" 'BEGIN{OFS="|"}
  function anonuser(u){ if(!(u in uid)) uid[u]=++uc; return "Dev_" uid[u] }
  function segtok(s){ if(!(s in sid)) sid[s]=++sc; return sprintf("s%04X", sid[s]) }
  function anonpath(p,    n,i,parts,last,base,ext,tok,out){
    n=split(p, parts, "/"); out="";
    for(i=1;i<=n;i++){
      last = (i==n)
      base = parts[i]; ext=""
      if(last && match(base, /\.[^\/.]+$/)){ ext=substr(base,RSTART); base=substr(base,1,RSTART-1) }
      tok = segtok(base)
      out = out (length(out)?"/":"") (last ? "f" tok ext : "d" tok)
    }
    return out
  }
  $1>=since { $2=anonuser($2); $4=anonpath($4); print }
' | LC_ALL=C sort -n -t'|' -k1,1 > "$TMPDIR/repo.anon.log"

#########################################
# --- 2) build HUD data and overlays ---
#########################################
python3 - "$WINDOW" "$TMPDIR/hud_single.txt" "$TMPDIR/hud_multi.ass" \
        "$SPD" "$RES_W" "$RES_H" "$HUD_FONT" "$HUD_FONT_SIZE_EFF" \
        "$HUD_MARGIN_L_EFF" "$HUD_MARGIN_T_EFF" "$HUD_PANEL_W_EFF" "$HUD_MODE" "$TMPDIR" "${IM_CMD:-}" "${HUD_FONT_FILE}" "$HUD_MARGIN_B_EFF" "$SCALE" <<'PY'
import subprocess, sys, math, os, string
from collections import defaultdict, Counter

WINDOW, OUT_SINGLE, OUT_ASS, SPD, RES_W, RES_H, FONT, FONT_SIZE, ML, MT, PANEL_W, HUD_MODE, TMPDIR, IM_CMD, FONT_FILE, MB, SCALE = sys.argv[1:]
SPD = float(SPD)
RES_W = int(RES_W); RES_H=int(RES_H)
FONT_SIZE=int(FONT_SIZE); ML=int(ML); MT=int(MT)
PANEL_W=int(PANEL_W)
MB=int(MB)
SCALE=float(SCALE)

def hmsf(seconds: float) -> str:
    # ASS time format H:MM:SS.cs (centiseconds)
    cs = int(round(seconds * 100))
    s = (cs // 100) % 60
    m = (cs // 6000) % 60
    h = cs // 360000
    cs = cs % 100
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"

# pull commits and numstat inside the repo cwd
p1 = subprocess.run(
    ["bash","-lc",f"git log --since='{WINDOW}' --numstat --format='%ct%x09%H%x09%ae' --no-merges"],
    capture_output=True, text=True, check=True
)
lines = p1.stdout.splitlines()

add = defaultdict(int); dele = defaultdict(int)  # LOC per day
day_commits = defaultdict(int)
day_authors = defaultdict(set)

# for language mix and change size
def lang_from_path(path: str) -> str:
    # naive ext -> language mapping (top-level categories only)
    ext = path.rsplit('.', 1)[-1].lower() if '.' in path.rsplit('/', 1)[-1] else ''
    m = {
        'py':'py','ipynb':'py','ts':'ts','tsx':'ts','js':'js','jsx':'js','mjs':'js',
        'go':'go','rs':'rs','java':'java','kt':'kt','kts':'kt','rb':'rb','php':'php',
        'c':'c','h':'c','cc':'cpp','cpp':'cpp','cxx':'cpp','hh':'cpp','hpp':'cpp','hxx':'cpp',
        'cs':'cs','swift':'swift','m':'objc','mm':'objc',
        'sh':'sh','bash':'sh','zsh':'sh','fish':'sh','ps1':'ps',
        'yml':'yaml','yaml':'yaml','json':'json','toml':'toml','ini':'ini','conf':'conf',
        'md':'md','rst':'rst','txt':'txt',
        'sql':'sql','r':'r','jl':'jl','scala':'scala',
    }
    return m.get(ext, 'other')

lang_loc_day = defaultdict(lambda: defaultdict(int))  # day -> lang -> LOC

commit_sizes = []  # (ts, size)

ts = None; commit = None; author = None
for line in lines:
    parts = line.split('\t')
    if len(parts) == 3 and parts[0].isdigit():
        sha = parts[1]
        sha_l = len(sha)
        if sha_l in (40, 64) and all(c in string.hexdigits for c in sha):
            # commit header: ts\tsha\tauthor
            ts = int(parts[0]); commit = sha; author = parts[2]
            day = (ts//86400)*86400
            day_commits[day] += 1
            day_authors[day].add(author)
            add.setdefault(day,0); dele.setdefault(day,0)
            continue
    # numstat lines: a\td\tpath
    if len(parts) >= 3 and ts is not None:
        a_s, d_s, path = parts[0], parts[1], parts[2]
        try: a = 0 if a_s == '-' else int(a_s)
        except: a = 0
        try: d = 0 if d_s == '-' else int(d_s)
        except: d = 0
        day = (ts//86400)*86400
        add[day] += a; dele[day] += d
        lang = lang_from_path(path)
        lang_loc_day[day][lang] += (a + d)
        continue

# We also need per-commit sizes; re-run a short parse producing commit totals
p2 = subprocess.run(
    ["bash","-lc",f"git log --since='{WINDOW}' --numstat --format='%ct' --no-merges"],
    capture_output=True, text=True, check=True
)
ts=None; c_add=0; c_del=0
for line in p2.stdout.splitlines():
    parts = line.split()
    if len(parts)==1 and parts[0].isdigit():
        if ts is not None:
            commit_sizes.append((ts, c_add + c_del))
        ts = int(parts[0]); c_add=0; c_del=0
    elif len(parts)>=3 and ts is not None:
        a_s, d_s = parts[0], parts[1]
        a = 0 if a_s == '-' else int(a_s) if a_s.isdigit() else 0
        d = 0 if d_s == '-' else int(d_s) if d_s.isdigit() else 0
        c_add += a; c_del += d
if ts is not None:
    commit_sizes.append((ts, c_add + c_del))

# Files changed / added / deleted per day via name-status
p3 = subprocess.run(
    ["bash","-lc",f"git log --since='{WINDOW}' --name-status --format='%ct' --no-merges"],
    capture_output=True, text=True, check=True
)
files_changed_day = defaultdict(set)  # unique paths per day (changed any status)
files_added_day = defaultdict(int)
files_deleted_day = defaultdict(int)
ts=None
for line in p3.stdout.splitlines():
    parts = line.split()
    if len(parts)==1 and parts[0].isdigit():
        ts = int(parts[0])
        continue
    if ts is None or not parts:
        continue
    st = parts[0]
    # handle simple statuses (A,M,D,T,C,R may have two paths for R/C)
    if st in ('A','M','D','T'):  # simple: st path
        path = parts[1]
        day = (ts//86400)*86400
        files_changed_day[day].add(path)
        if st=='A': files_added_day[day]+=1
        if st=='D': files_deleted_day[day]+=1
    elif st.startswith('R') or st.startswith('C'):
        # R100	old	new — count as changed; not added/deleted
        path = parts[-1]
        day = (ts//86400)*86400
        files_changed_day[day].add(path)

if add:
    start, end = min(add), max(add)
    days = list(range(start, end+86400, 86400))
else:
    days = []

for t in days:
    add.setdefault(t,0); dele.setdefault(t,0)
    day_commits.setdefault(t,0)
    files_added_day.setdefault(t,0)
    files_deleted_day.setdefault(t,0)
    files_changed_day.setdefault(t,set())
    day_authors.setdefault(t,set())

def roll(vals, window_days):
    q=[]; s=0; out={}
    w=window_days*86400
    for t in days:
        v=vals[t]; q.append((t,v)); s+=v
        while q and t-q[0][0]>=w:
            s-=q[0][1]; q.pop(0)
        out[t]=s
    return out

def roll_union(sets_by_day, window_days):
    w=window_days*86400
    q=[]  # (t, set)
    out={}
    for t in days:
        q.append((t, sets_by_day[t]))
        while q and t-q[0][0]>=w:
            q.pop(0)
        u=set()
        for _,s in q:
            u |= s
        out[t]=len(u)
    return out

a1={t:add[t] for t in days}; d1={t:dele[t] for t in days}
a7=roll(add,7); d7=roll(dele,7)
a30=roll(add,30); d30=roll(dele,30)

# commits / authors
c1={t:day_commits[t] for t in days}
c7=roll(day_commits,7); c30=roll(day_commits,30)
u1={t:len(day_authors[t]) for t in days}
u7=roll_union(day_authors,7); u30=roll_union(day_authors,30)

# files changed and files added/deleted
fchg1={t:len(files_changed_day[t]) for t in days}
fchg7=roll_union(files_changed_day,7); fchg30=roll_union(files_changed_day,30)
fadd1={t:files_added_day[t] for t in days}
fadd7=roll(files_added_day,7); fadd30=roll(files_added_day,30)
fdel1={t:files_deleted_day[t] for t in days}
fdel7=roll(files_deleted_day,7); fdel30=roll(files_deleted_day,30)

# language share 7d (by LOC changed) via sliding window
lang7_by_day = {}
from collections import deque
_lang_win_days = deque()
_lang_win = Counter()
for t in days:
    _lang_win_days.append(t)
    for lg,loc in lang_loc_day[t].items():
        _lang_win[lg] += loc
    if len(_lang_win_days) > 7:
        old = _lang_win_days.popleft()
        for lg,loc in lang_loc_day[old].items():
            _lang_win[lg] -= loc
            if _lang_win[lg] <= 0:
                _lang_win.pop(lg, None)
    total = sum(_lang_win.values())
    if total>0:
        top = _lang_win.most_common(3)
        lang7_by_day[t] = [(lg, int(round(100*loc/total))) for lg,loc in top]
    else:
        lang7_by_day[t] = []

# change size 7d distribution (median, p90)
def pct(nums, p):
    if not nums:
        return 0
    nums=sorted(nums)
    k = (len(nums)-1)*p
    f = math.floor(k); c = math.ceil(k)
    if f==c:
        return nums[int(k)]
    return int(round(nums[f]*(c-k) + nums[c]*(k-f)))

sizes_by_day = {}
# bin commit sizes by day
from bisect import bisect_left, insort
sizes_on_day = defaultdict(list)
for ts_, size in commit_sizes:
    d = (ts_//86400)*86400
    sizes_on_day[d].append(size)
_sizes_win_days = deque()
_sorted = []
for t in days:
    _sizes_win_days.append(t)
    for s in sizes_on_day.get(t, []):
        insort(_sorted, s)
    if len(_sizes_win_days) > 7:
        old = _sizes_win_days.popleft()
        for s in sizes_on_day.get(old, []):
            i = bisect_left(_sorted, s)
            if i < len(_sorted) and _sorted[i] == s:
                _sorted.pop(i)
    n = len(_sorted)
    if n == 0:
        sizes_by_day[t] = (0, 0)
    else:
        m_idx = (n-1)*0.5
        p_idx = (n-1)*0.9
        def _interp(idx):
            import math
            f = math.floor(idx); c = math.ceil(idx)
            if f == c:
                return _sorted[int(idx)]
            return int(round(_sorted[f]*(c-idx) + _sorted[c]*(idx-f)))
        sizes_by_day[t] = (_interp(m_idx), _interp(p_idx))

max1=max7=max30=0

# Precompute fixed widths so the HUD text length stays constant
def thousands(n):
    return f"{n:,}"

def maxlen(vals):
    return max((len(thousands(v)) for v in vals), default=1)

tot1_all=[a1[t]+d1[t] for t in days]
tot7_all=[a7[t]+d7[t] for t in days]
tot30_all=[a30[t]+d30[t] for t in days]
max1_all=[max(tot1_all[:i+1]) for i in range(len(tot1_all))] if tot1_all else []
max7_all=[max(tot7_all[:i+1]) for i in range(len(tot7_all))] if tot7_all else []
max30_all=[max(tot30_all[:i+1]) for i in range(len(tot30_all))] if tot30_all else []

w_a1 = maxlen([a1[t] for t in days])
w_d1 = maxlen([d1[t] for t in days])
w_t1 = maxlen(tot1_all)
w_a7 = maxlen([a7[t] for t in days])
w_d7 = maxlen([d7[t] for t in days])
w_t7 = maxlen(tot7_all)
w_a30 = maxlen([a30[t] for t in days])
w_d30 = maxlen([d30[t] for t in days])
w_t30 = maxlen(tot30_all)
w_m1 = maxlen(max1_all if max1_all else [0])
w_m7 = maxlen(max7_all if max7_all else [0])
w_m30 = maxlen(max30_all if max30_all else [0])

# widths for new metrics
w_c1 = maxlen([c1[t] for t in days]); w_c7=maxlen([c7[t] for t in days]); w_c30=maxlen([c30[t] for t in days])
w_u1 = maxlen([u1[t] for t in days]); w_u7=maxlen([u7[t] for t in days]); w_u30=maxlen([u30[t] for t in days])
w_fchg1=maxlen([fchg1[t] for t in days]); w_fchg7=maxlen([fchg7[t] for t in days]); w_fchg30=maxlen([fchg30[t] for t in days])
w_fadd1=maxlen([fadd1[t] for t in days]); w_fadd7=maxlen([fadd7[t] for t in days]); w_fadd30=maxlen([fadd30[t] for t in days])
w_fdel1=maxlen([fdel1[t] for t in days]); w_fdel7=maxlen([fdel7[t] for t in days]); w_fdel30=maxlen([fdel30[t] for t in days])
w_med = maxlen([sizes_by_day[t][0] for t in days]); w_p90 = maxlen([sizes_by_day[t][1] for t in days])

def fmt(n, w):
    s = thousands(n)
    return s.rjust(w)

# Write single-line captions (fallback) with fixed widths to prevent horizontal jumping
with open(OUT_SINGLE, 'w') as f:
    for idx, t in enumerate(days):
        tot1=a1[t]+d1[t]; tot7=a7[t]+d7[t]; tot30=a30[t]+d30[t]
        max1=max(max1,tot1); max7=max(max7,tot7); max30=max(max30,tot30)
        cap=(f"1d +{fmt(a1[t],w_a1)}/-{fmt(d1[t],w_d1)} ({fmt(tot1,w_t1)})  •  "
             f"7d +{fmt(a7[t],w_a7)}/-{fmt(d7[t],w_d7)} ({fmt(tot7,w_t7)})  •  "
             f"30d +{fmt(a30[t],w_a30)}/-{fmt(d30[t],w_d30)} ({fmt(tot30,w_t30)})  •  "
             f"Max1d {fmt(max1,w_m1)}  •  Max7d {fmt(max7,w_m7)}  •  Max30d {fmt(max30,w_m30)}")
        f.write(f"{t}|{cap}\n")

# Reset maxima for overlay loop (we want same running maxima)
max1=max7=max30=0

ass_header = f"""
[Script Info]
; Script generated by gource_anon_hud.sh
ScriptType: v4.00+
PlayResX: {RES_W}
PlayResY: {RES_H}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
; BorderStyle 3 draws an opaque box using BackColour behind each line
Style: HUD,{FONT},{FONT_SIZE},&H00FFFFFF,&H000000FF,&H00000000,&H64000000,0,0,0,0,100,100,0,0,3,1,0,1,{ML},20,{MB},0

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
""".lstrip()

with open(OUT_ASS, 'w') as f:
    f.write(ass_header)
    if not days:
        sys.exit(0)
    start_day = days[0]
    # show each day's HUD for ~SPD seconds, slight overlap to avoid blink if needed
    seg = max(SPD*0.98, 0.01)
    for i, t in enumerate(days):
        tot1=a1[t]+d1[t]; tot7=a7[t]+d7[t]; tot30=a30[t]+d30[t]
        max1=max(max1,tot1); max7=max(max7,tot7); max30=max(max30,tot30)
        lines = [
            f"1d   +{fmt(a1[t],w_a1)}  -{fmt(d1[t],w_d1)}   ({fmt(tot1,w_t1)})",
            f"7d   +{fmt(a7[t],w_a7)}  -{fmt(d7[t],w_d7)}   ({fmt(tot7,w_t7)})",
            f"30d  +{fmt(a30[t],w_a30)}  -{fmt(d30[t],w_d30)}  ({fmt(tot30,w_t30)})",
            f"Max1d   {fmt(max1,w_m1)}",
            f"Max7d   {fmt(max7,w_m7)}",
            f"Max30d  {fmt(max30,w_m30)}",
        ]
        txt = "\\N".join(lines)  # ASS newline
        st = i * SPD
        en = st + seg
        f.write(f"Dialogue: 0,{hmsf(st)},{hmsf(en)},HUD,,0000,0000,0000,,{txt}\n")
        
# --- PNG overlays (HUD_MODE=png): generate full-frame transparent PNG per-day ---
if HUD_MODE == 'png':
    import concurrent.futures as cf
    # Draw settings
    line_gap = int(FONT_SIZE * 1.35)
    pad_x = int(16 * SCALE)
    pad_y = int(12 * SCALE)
    graph_h = int(140 * SCALE)  # px height of each live graph (2x height)
    graph_gap = int(14 * SCALE) # spacing between text rows and graphs
    graphs_n = 3   # LOC, Files, and Flow (7d adds/deletes) graphs
    # Compute panel height based on number of lines + graphs
    nlines = 13
    text_h = nlines*line_gap
    panel_h = pad_y + text_h + graph_gap + graphs_n*graph_h + (graphs_n-1)*graph_gap + pad_y
    # Background rectangle positioned flush at bottom-left (no outer margins)
    rect_x1 = 0
    rect_x2 = PANEL_W
    rect_y2 = RES_H
    rect_y1 = rect_y2 - panel_h

    # Precompute text lines per day
    # Build cumulative total LOC delta series (baseline=0 at window start)
    cum_vals = []
    c = 0
    for t in days:
        c += (a1[t] - d1[t])
        cum_vals.append(c)
    min_c = min(cum_vals) if cum_vals else 0
    max_c = max(cum_vals) if cum_vals else 1
    rng_c = max(1, max_c - min_c)

    # Build cumulative files delta series (added - deleted)
    cum_files = []
    cf_sum = 0
    for t in days:
        cf_sum += (fadd1[t] - fdel1[t])
        cum_files.append(cf_sum)
    min_f = min(cum_files) if cum_files else 0
    max_f = max(cum_files) if cum_files else 1
    rng_f = max(1, max_f - min_f)

    # Flow series: 7d adds and deletes
    flow_add7 = [a7[t] for t in days]
    flow_del7 = [d7[t] for t in days]
    max_flow = max(max(flow_add7) if flow_add7 else 0, max(flow_del7) if flow_del7 else 0, 1)

    # Trend deltas WoW for 7d metrics (vs value 7 days earlier)
    net7 = [(a7[t]-d7[t]) for t in days]
    def delta_wow(arr, idx, step=7):
        if idx >= step:
            return arr[idx] - arr[idx-step]
        return 0

    day_lines = []
    for i, t in enumerate(days):
        tot1=a1[t]+d1[t]; tot7=a7[t]+d7[t]; tot30=a30[t]+d30[t]
        max1=max1_all[i] if i < len(max1_all) else 0
        max7=max7_all[i] if i < len(max7_all) else 0
        max30=max30_all[i] if i < len(max30_all) else 0
        lg7 = lang7_by_day.get(t, [])
        lg_txt = " ".join([f"{lg} {p}%" for lg,p in lg7]) if lg7 else ""
        med, p90 = sizes_by_day[t]
        # ratios
        def pct_div(n, d):
            return int(round(100*n/d)) if d>0 else 0
        churn7 = pct_div(d7[t], (a7[t]+d7[t]))
        churn30 = pct_div(d30[t], (a30[t]+d30[t]))
        eff7 = pct_div((a7[t]-d7[t]), (a7[t]+d7[t]))
        eff30 = pct_div((a30[t]-d30[t]), (a30[t]+d30[t]))
        # trends
        d_loc7 = delta_wow(net7, i)
        d_cmt7 = delta_wow([c7[x] for x in days], i) if False else (c7[t] - (c7[days[i-7]] if i>=7 else 0))
        d_fch7 = delta_wow([fchg7[x] for x in days], i) if False else (fchg7[t] - (fchg7[days[i-7]] if i>=7 else 0))
        def arrow(d):
            return ("▲ +"+str(d)) if d>0 else ("▼ "+str(abs(d))) if d<0 else "– 0"
        lines = [
            f"LOC 1d  +{fmt(a1[t],w_a1)}  -{fmt(d1[t],w_d1)}   (Net {fmt(a1[t]-d1[t], max(w_a1,w_d1))})",
            f"LOC 7d  +{fmt(a7[t],w_a7)}  -{fmt(d7[t],w_d7)}   (Net {fmt(a7[t]-d7[t], max(w_a7,w_d7))})",
            f"LOC 30d +{fmt(a30[t],w_a30)}  -{fmt(d30[t],w_d30)}  (Net {fmt(a30[t]-d30[t], max(w_a30,w_d30))})",
            f"Peaks   Max1d {fmt(max1,w_m1)}  •  Max7d {fmt(max7,w_m7)}  •  Max30d {fmt(max30,w_m30)}",
            f"Commits 1d {fmt(c1[t],w_c1)}  •  7d {fmt(c7[t],w_c7)}  •  30d {fmt(c30[t],w_c30)}",
            f"Authors 1d {fmt(u1[t],w_u1)}  •  7d {fmt(u7[t],w_u7)}  •  30d {fmt(u30[t],w_u30)}",
            f"FilesΔ  1d {fmt(fchg1[t],w_fchg1)}  •  7d {fmt(fchg7[t],w_fchg7)}  •  30d {fmt(fchg30[t],w_fchg30)}",
            f"Files A/D  1d +{fmt(fadd1[t],w_fadd1)}/-{fmt(fdel1[t],w_fdel1)}  •  7d +{fmt(fadd7[t],w_fadd7)}/-{fmt(fdel7[t],w_fdel7)}  •  30d +{fmt(fadd30[t],w_fadd30)}/-{fmt(fdel30[t],w_fdel30)}",
            f"Churn 7d {churn7}%  •  30d {churn30}%",
            f"Efficiency 7d {eff7}%  •  30d {eff30}%",
            f"Trends 7d  LOC {arrow(d_loc7)}  •  Commits {arrow(d_cmt7)}  •  FilesΔ {arrow(d_fch7)}",
            f"Lang 7d  {lg_txt}",
            f"Change Size 7d  median {fmt(med,w_med)}  •  p90 {fmt(p90,w_p90)}",
        ]
        day_lines.append(lines)

    def render_one(i_lines):
        i, lines = i_lines
        y = rect_y1 + pad_y + FONT_SIZE
        out = os.path.join(TMPDIR, f"overlay_{i:05d}.png")
        # Graph areas geometry (three stacked graphs)
        gx1 = pad_x
        gx2 = rect_x2 - pad_x
        gw = max(1, gx2 - gx1)
        g3_y2 = rect_y2 - pad_y
        g3_y1 = g3_y2 - graph_h
        g2_y2 = g3_y1 - graph_gap
        g2_y1 = g2_y2 - graph_h
        g1_y2 = g2_y1 - graph_gap
        g1_y1 = g1_y2 - graph_h
        # Points up to day i
        if i > 0:
            step = gw / max(1, len(cum_vals)-1)
            pts1 = []
            pts2 = []
            pts3a = []
            pts3d = []
            for j in range(0, i+1):
                x = int(round(gx1 + j*step))
                n1 = (cum_vals[j] - min_c) / rng_c
                y1v = int(round(g1_y2 - n1*graph_h))
                pts1.append(f"{x},{y1v}")
                n2 = (cum_files[j] - min_f) / rng_f
                y2v = int(round(g2_y2 - n2*graph_h))
                pts2.append(f"{x},{y2v}")
                # flow lines scale by max_flow
                fa = flow_add7[j] / max_flow
                fd = flow_del7[j] / max_flow
                y3av = int(round(g3_y2 - fa*graph_h))
                y3dv = int(round(g3_y2 - fd*graph_h))
                pts3a.append(f"{x},{y3av}")
                pts3d.append(f"{x},{y3dv}")
            poly1 = " ".join(pts1)
            poly2 = " ".join(pts2)
            poly3a = " ".join(pts3a)
            poly3d = " ".join(pts3d)
        else:
            poly1 = poly2 = poly3a = poly3d = ""

        cmd = [IM_CMD, "-size", f"{RES_W}x{RES_H}", "xc:none",
               "-gravity", "NorthWest",
               # panel background
               "-fill", "rgba(0,0,0,0.55)", "-draw",
               f"rectangle {rect_x1},{rect_y1} {rect_x2},{rect_y2}",
               # graph borders
               "-fill", "none", "-stroke", "rgba(255,255,255,0.4)", "-strokewidth", "1", "-draw",
               f"rectangle {gx1},{g1_y1} {gx2},{g1_y2}",
               "-draw", f"rectangle {gx1},{g2_y1} {gx2},{g2_y2}",
               "-draw", f"rectangle {gx1},{g3_y1} {gx2},{g3_y2}"]
        # graph polylines
        if poly1:
            cmd += ["-fill", "none", "-stroke", "white", "-strokewidth", str(max(2,int(2*SCALE))), "-draw", f"polyline {poly1}"]
        if poly2:
            cmd += ["-fill", "none", "-stroke", "#00FFFF", "-strokewidth", str(max(2,int(2*SCALE))), "-draw", f"polyline {poly2}"]
        if poly3a:
            cmd += ["-fill", "none", "-stroke", "#00FF66", "-strokewidth", str(max(2,int(2*SCALE))), "-draw", f"polyline {poly3a}"]
        if poly3d:
            cmd += ["-fill", "none", "-stroke", "#FF5555", "-strokewidth", str(max(2,int(2*SCALE))), "-draw", f"polyline {poly3d}"]
        # peak markers on LOC graph when new Max7d / Max30d occurs
        # place small circles near top edge of LOC graph
        if i > 0:
            # Determine if today increases running max7 or max30 (gross totals)
            runmax7_prev = max(tot7_all[:i]) if i>0 else 0
            runmax30_prev = max(tot30_all[:i]) if i>0 else 0
            run7_today = tot7
            run30_today = tot30
            if run7_today > runmax7_prev:
                cx = int(round(gx1 + i*step))
                cy = int(round(g1_y1 + int(6*SCALE)))
                r = max(2, int(round(2*SCALE)))
                cmd += ["-fill", "#FFD700", "-stroke", "none", "-draw", f"circle {cx},{cy} {cx+r},{cy}"]
            if run30_today > runmax30_prev:
                cx = int(round(gx1 + i*step))
                cy = int(round(g1_y1 + int(14*SCALE)))
                r = max(2, int(round(2*SCALE)))
                cmd += ["-fill", "#FF00FF", "-stroke", "none", "-draw", f"circle {cx},{cy} {cx+r},{cy}"]
        # reset for text
        cmd += ["-fill", "white", "-stroke", "#00000099", "-strokewidth", str(max(1,int(1*SCALE)))]
        if FONT_FILE:
            cmd += ["-font", FONT_FILE]
        elif FONT:
            cmd += ["-font", FONT]
        cmd += ["-pointsize", str(FONT_SIZE)]
        # labels for graphs (inside top-left of each box)
        cmd += ["-annotate", f"+{gx1+2}+{g1_y1 + int(12*SCALE)}", "Total LOC (Δ)"]
        cmd += ["-annotate", f"+{gx1+2}+{g2_y1 + int(12*SCALE)}", "Files (Δ)"]
        cmd += ["-annotate", f"+{gx1+2}+{g3_y1 + int(12*SCALE)}", "+Adds / -Deletes (7d)"]
        for line in lines:
            cmd += ["-annotate", f"+{pad_x}+{y}", line]
            y += line_gap
        # clear stroke for any following operations
        cmd += ["-stroke", "none"]
        cmd += [out]
        subprocess.run(cmd, check=True)

    total = len(day_lines)
    # Quadruple default concurrency (4x CPU), cap to 16 unless HUD_JOBS is set
    jobs = int(os.environ.get('HUD_JOBS', '0')) or max(1, min(16, (os.cpu_count() or 2) * 4))
    # Progress setup
    import sys as _sys
    _sys.stderr.write(f"[HUD] Rendering overlays: 0/{total} frames using {jobs} workers\n")
    _sys.stderr.flush()
    step = max(1, total // 20)  # update every ~5%
    done = 0
    with cf.ThreadPoolExecutor(max_workers=jobs) as ex:
        futs = {ex.submit(render_one, x): x for x in enumerate(day_lines)}
        from concurrent.futures import as_completed
        for fut in as_completed(futs):
            # make exceptions visible and fallback later
            try:
                fut.result()
            except Exception as e:
                _sys.stderr.write(f"\n[HUD] WARN: overlay render failed: {e}\n")
            done += 1
            if done == 1 or done % step == 0 or done == total:
                _sys.stderr.write(f"[HUD] Rendering overlays: {done}/{total}\r")
                _sys.stderr.flush()
    _sys.stderr.write("\n")
    _sys.stderr.flush()

    # Verify and fill any missing frames sequentially
    import os as __os
    missing = [i for i in range(total) if not __os.path.exists(__os.path.join(TMPDIR, f"overlay_{i:05d}.png"))]
    if missing:
        _sys.stderr.write(f"[HUD] Filling missing overlays sequentially: {len(missing)} frames\n")
        for i in missing:
            render_one((i, day_lines[i]))
PY

# decide whether overlay is available
HAS_ASS_FILTER=0
if ffmpeg -hide_banner -filters 2>/dev/null | grep -q "\bass\b"; then HAS_ASS_FILTER=1; fi

# --- 3) render (1080p) ---
# For caption mode, set duration >= SPD to minimize blinking.
CAP_DUR=$(python3 - <<PY
spd=$SPD
print(round(spd*1.05,3))
PY
)

# preview sanity check (optional):
# gource --log-format custom "$TMPDIR/repo.anon.log" --hide usernames,filenames,dirnames,date --seconds-per-day 2 --auto-skip-seconds 1

AUTO_SKIP=1
# When overlay/PNG HUD is selected, prefer linear time for perfect sync
if { [[ "$HUD_MODE" == "overlay" && "$HAS_ASS_FILTER" -eq 1 ]] || [[ "$HUD_MODE" == "png" ]]; }; then
  AUTO_SKIP=0
fi

# Build autoskip args only when > 0 (gource rejects 0)
EXTRA_AUTOSKIP=()
if [[ "$AUTO_SKIP" -gt 0 ]]; then
  EXTRA_AUTOSKIP=(--auto-skip-seconds "$AUTO_SKIP")
fi

GOURCE_HIDE="usernames,filenames,dirnames"  # keep date/time visible (default top HUD)

if [[ "$HUD_MODE" == "caption" ]]; then
  gource --log-format custom "$TMPDIR/repo.anon.log" \
         --hide "$GOURCE_HIDE" \
         --caption-file "$TMPDIR/hud_single.txt" \
         --caption-size "$CAPTION_SIZE_EFF" --caption-duration "$CAP_DUR" \
         --seconds-per-day "$SPD" "${EXTRA_AUTOSKIP[@]}" \
         --camera-mode overview --stop-at-end \
         --title "$TITLE" \
         -"${RES_W}x${RES_H}" \
         --output-ppm-stream - \
  | ffmpeg -y -r "$FPS" -f image2pipe -vcodec ppm -i - \
           -vf "tpad=stop_mode=clone:stop_duration=${TAIL_PAUSE}" \
           -pix_fmt yuv420p -movflags +faststart -crf 18 \
           "$OUT"
elif [[ "$HUD_MODE" == "overlay" && "$HAS_ASS_FILTER" -eq 1 ]]; then
  gource --log-format custom "$TMPDIR/repo.anon.log" \
         --hide "$GOURCE_HIDE" \
         --seconds-per-day "$SPD" "${EXTRA_AUTOSKIP[@]}" \
         --camera-mode overview --stop-at-end \
         --title "$TITLE" \
         -"${RES_W}x${RES_H}" \
         --output-ppm-stream - \
  | ffmpeg -y -r "$FPS" -f image2pipe -vcodec ppm -i - \
           -vf "ass=$TMPDIR/hud_multi.ass,tpad=stop_mode=clone:stop_duration=${TAIL_PAUSE}" \
           -pix_fmt yuv420p -movflags +faststart -crf 18 \
           "$OUT"
elif [[ "$HUD_MODE" == "png" ]]; then
  OVERLAY_FPS=$(python3 - <<PY
spd=$SPD
print(1/spd)
PY
)
  OVERLAY_COUNT=$(find "$TMPDIR" -maxdepth 1 -name 'overlay_*.png' -printf '.' 2>/dev/null | wc -c | tr -d ' ')
  echo "[HUD] Days in window: $OVERLAY_COUNT, overlay fps: $OVERLAY_FPS" >&2

  gource --log-format custom "$TMPDIR/repo.anon.log" \
         --hide "$GOURCE_HIDE" \
         --seconds-per-day "$SPD" "${EXTRA_AUTOSKIP[@]}" \
         --camera-mode overview --stop-at-end \
         --title "$TITLE" \
         -"${RES_W}x${RES_H}" \
         --output-ppm-stream - \
  | ffmpeg -y -hide_banner -loglevel error \
           -r "$FPS" -f image2pipe -vcodec ppm -i - \
           -framerate "$OVERLAY_FPS" -start_number 0 -i "$TMPDIR/overlay_%05d.png" \
           -filter_complex "[0:v]fps=$FPS,settb=AVTB,setpts=N/($FPS*TB)[bg];[1:v]fps=$FPS,format=rgba,settb=AVTB,setpts=N/($FPS*TB)[ov];[bg][ov]overlay=x=0:y=0:format=auto,tpad=stop_mode=clone:stop_duration=${TAIL_PAUSE}" \
           -pix_fmt yuv420p -movflags +faststart -crf 18 \
           "$OUT"
else
  echo "Overlay HUD requested but ffmpeg 'ass' filter not available. Falling back to caption mode." >&2
  gource --log-format custom "$TMPDIR/repo.anon.log" \
         --hide "$GOURCE_HIDE" \
         --caption-file "$TMPDIR/hud_single.txt" \
         --caption-size "$CAPTION_SIZE" --caption-duration "$CAP_DUR" \
         --seconds-per-day "$SPD" ${AUTO_SKIP:+--auto-skip-seconds $AUTO_SKIP} \
         --camera-mode overview --stop-at-end \
         --title "$TITLE" \
         -"${RES_W}x${RES_H}" \
         --output-ppm-stream - \
  | ffmpeg -y -r "$FPS" -f image2pipe -vcodec ppm -i - \
           -vf "tpad=stop_mode=clone:stop_duration=${TAIL_PAUSE}" \
           -pix_fmt yuv420p -movflags +faststart -crf 18 \
           "$OUT"
fi

popd >/dev/null
echo "✅ Wrote: $OUT"
