from __future__ import annotations
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from PIL import Image, ImageDraw, ImageFont
from gource_hud.stats import DayMetrics

N_LINES = 13
N_GRAPHS = 3


@dataclass
class LayoutMetrics:
    scale: float
    font_size: int
    line_gap: int
    pad_x: int
    pad_y: int
    graph_h: int
    graph_gap: int
    panel_w: int
    panel_h: int
    rect_x1: int
    rect_y1: int
    rect_x2: int
    rect_y2: int
    graph1_bbox: tuple[int, int, int, int]
    graph2_bbox: tuple[int, int, int, int]
    graph3_bbox: tuple[int, int, int, int]
    text_x: int
    text_y_start: int
    stroke_width: int
    polyline_width: int


def compute_layout(frame_w: int, frame_h: int, scale: float, font_size_base: int, panel_width_base: int) -> LayoutMetrics:
    font_size = int(font_size_base * scale)
    line_gap = int(font_size * 1.35)
    pad_x = int(16 * scale)
    pad_y = int(12 * scale)
    graph_h = int(140 * scale)
    graph_gap = int(14 * scale)
    panel_w = int(panel_width_base * scale)
    text_h = N_LINES * line_gap
    panel_h = pad_y + text_h + graph_gap + N_GRAPHS * graph_h + (N_GRAPHS - 1) * graph_gap + pad_y
    rect_x1 = 0
    rect_y1 = frame_h - panel_h
    rect_x2 = panel_w
    rect_y2 = frame_h
    gx1 = pad_x
    gx2 = panel_w - pad_x
    g3_y2 = rect_y2 - pad_y
    g3_y1 = g3_y2 - graph_h
    g2_y2 = g3_y1 - graph_gap
    g2_y1 = g2_y2 - graph_h
    g1_y2 = g2_y1 - graph_gap
    g1_y1 = g1_y2 - graph_h
    return LayoutMetrics(
        scale=scale, font_size=font_size, line_gap=line_gap,
        pad_x=pad_x, pad_y=pad_y, graph_h=graph_h, graph_gap=graph_gap,
        panel_w=panel_w, panel_h=panel_h,
        rect_x1=rect_x1, rect_y1=rect_y1, rect_x2=rect_x2, rect_y2=rect_y2,
        graph1_bbox=(gx1, g1_y1, gx2, g1_y2),
        graph2_bbox=(gx1, g2_y1, gx2, g2_y2),
        graph3_bbox=(gx1, g3_y1, gx2, g3_y2),
        text_x=pad_x, text_y_start=rect_y1 + pad_y,
        stroke_width=max(1, int(scale)),
        polyline_width=max(2, int(2 * scale)),
    )


# ---------------------------------------------------------------------------
# Text formatting helpers
# ---------------------------------------------------------------------------

def thousands(n: int) -> str:
    """Format an integer with comma separators."""
    return f"{n:,}"


def fmt(n: int, w: int) -> str:
    """Right-justify a thousands-formatted integer to width *w*."""
    return thousands(n).rjust(w)


def _maxlen(values: list[int]) -> int:
    """Return the display-width of the widest value in thousands format."""
    if not values:
        return 1
    return max(len(thousands(v)) for v in values)


# ---------------------------------------------------------------------------
# FormatWidths – column widths for right-justified numbers
# ---------------------------------------------------------------------------

@dataclass
class FormatWidths:
    w_a1: int = 1
    w_d1: int = 1
    w_n1: int = 1
    w_a7: int = 1
    w_d7: int = 1
    w_n7: int = 1
    w_a30: int = 1
    w_d30: int = 1
    w_n30: int = 1
    w_m1: int = 1
    w_m7: int = 1
    w_m30: int = 1
    w_c1: int = 1
    w_c7: int = 1
    w_c30: int = 1
    w_u1: int = 1
    w_u7: int = 1
    w_u30: int = 1
    w_f1: int = 1
    w_f7: int = 1
    w_f30: int = 1
    w_fa1: int = 1
    w_fa7: int = 1
    w_fa30: int = 1
    w_fd1: int = 1
    w_fd7: int = 1
    w_fd30: int = 1
    w_churn7: int = 1
    w_churn30: int = 1
    w_eff7: int = 1
    w_eff30: int = 1
    w_med: int = 1
    w_p90: int = 1


def compute_format_widths(metrics: list[DayMetrics]) -> FormatWidths:
    """Compute column widths from the global max across all days."""
    if not metrics:
        return FormatWidths()
    return FormatWidths(
        w_a1=_maxlen([m.loc_added_1d for m in metrics]),
        w_d1=_maxlen([m.loc_deleted_1d for m in metrics]),
        w_n1=max(_maxlen([m.loc_added_1d for m in metrics]),
                 _maxlen([m.loc_deleted_1d for m in metrics])) + 1,
        w_a7=_maxlen([m.loc_added_7d for m in metrics]),
        w_d7=_maxlen([m.loc_deleted_7d for m in metrics]),
        w_n7=max(_maxlen([m.loc_added_7d for m in metrics]),
                 _maxlen([m.loc_deleted_7d for m in metrics])) + 1,
        w_a30=_maxlen([m.loc_added_30d for m in metrics]),
        w_d30=_maxlen([m.loc_deleted_30d for m in metrics]),
        w_n30=max(_maxlen([m.loc_added_30d for m in metrics]),
                  _maxlen([m.loc_deleted_30d for m in metrics])) + 1,
        w_m1=_maxlen([m.max_loc_total_1d for m in metrics]),
        w_m7=_maxlen([m.max_loc_total_7d for m in metrics]),
        w_m30=_maxlen([m.max_loc_total_30d for m in metrics]),
        w_c1=_maxlen([m.commits_1d for m in metrics]),
        w_c7=_maxlen([m.commits_7d for m in metrics]),
        w_c30=_maxlen([m.commits_30d for m in metrics]),
        w_u1=_maxlen([m.authors_1d for m in metrics]),
        w_u7=_maxlen([m.authors_7d for m in metrics]),
        w_u30=_maxlen([m.authors_30d for m in metrics]),
        w_f1=_maxlen([m.files_changed_1d for m in metrics]),
        w_f7=_maxlen([m.files_changed_7d for m in metrics]),
        w_f30=_maxlen([m.files_changed_30d for m in metrics]),
        w_fa1=_maxlen([m.files_added_1d for m in metrics]),
        w_fa7=_maxlen([m.files_added_7d for m in metrics]),
        w_fa30=_maxlen([m.files_added_30d for m in metrics]),
        w_fd1=_maxlen([m.files_deleted_1d for m in metrics]),
        w_fd7=_maxlen([m.files_deleted_7d for m in metrics]),
        w_fd30=_maxlen([m.files_deleted_30d for m in metrics]),
        w_churn7=_maxlen([m.churn_7d for m in metrics]),
        w_churn30=_maxlen([m.churn_30d for m in metrics]),
        w_eff7=_maxlen([m.efficiency_7d for m in metrics]),
        w_eff30=_maxlen([m.efficiency_30d for m in metrics]),
        w_med=_maxlen([m.change_median_7d for m in metrics]),
        w_p90=_maxlen([m.change_p90_7d for m in metrics]),
    )


def _format_one_day(m: DayMetrics, w: FormatWidths) -> list[str]:
    """Return 13 fixed-width text lines for one day."""
    net1 = m.loc_added_1d - m.loc_deleted_1d
    net7 = m.loc_added_7d - m.loc_deleted_7d
    net30 = m.loc_added_30d - m.loc_deleted_30d

    lines = [
        f"LOC 1d  +{fmt(m.loc_added_1d, w.w_a1)}  -{fmt(m.loc_deleted_1d, w.w_d1)}   (Net {fmt(net1, w.w_n1)})",
        f"LOC 7d  +{fmt(m.loc_added_7d, w.w_a7)}  -{fmt(m.loc_deleted_7d, w.w_d7)}   (Net {fmt(net7, w.w_n7)})",
        f"LOC 30d +{fmt(m.loc_added_30d, w.w_a30)}  -{fmt(m.loc_deleted_30d, w.w_d30)}  (Net {fmt(net30, w.w_n30)})",
        f"Peaks   Max1d {fmt(m.max_loc_total_1d, w.w_m1)}  \u2022  Max7d {fmt(m.max_loc_total_7d, w.w_m7)}  \u2022  Max30d {fmt(m.max_loc_total_30d, w.w_m30)}",
        f"Commits 1d {fmt(m.commits_1d, w.w_c1)}  \u2022  7d {fmt(m.commits_7d, w.w_c7)}  \u2022  30d {fmt(m.commits_30d, w.w_c30)}",
        f"Authors 1d {fmt(m.authors_1d, w.w_u1)}  \u2022  7d {fmt(m.authors_7d, w.w_u7)}  \u2022  30d {fmt(m.authors_30d, w.w_u30)}",
        f"Files\u0394  1d {fmt(m.files_changed_1d, w.w_f1)}  \u2022  7d {fmt(m.files_changed_7d, w.w_f7)}  \u2022  30d {fmt(m.files_changed_30d, w.w_f30)}",
        f"Files A/D  1d +{fmt(m.files_added_1d, w.w_fa1)}/-{fmt(m.files_deleted_1d, w.w_fd1)}  \u2022  7d +{fmt(m.files_added_7d, w.w_fa7)}/-{fmt(m.files_deleted_7d, w.w_fd7)}  \u2022  30d +{fmt(m.files_added_30d, w.w_fa30)}/-{fmt(m.files_deleted_30d, w.w_fd30)}",
        f"Churn 7d {fmt(m.churn_7d, w.w_churn7)}%  \u2022  30d {fmt(m.churn_30d, w.w_churn30)}%",
        f"Efficiency 7d {fmt(m.efficiency_7d, w.w_eff7)}%  \u2022  30d {fmt(m.efficiency_30d, w.w_eff30)}%",
        f"Trends 7d  LOC {m.arrow_loc}  \u2022  Commits {m.arrow_commits}  \u2022  Files\u0394 {m.arrow_files}",
    ]

    # Lang 7d line
    if m.lang_mix_7d:
        lang_parts = "  ".join(f"{lang} {pct}%" for lang, pct in m.lang_mix_7d)
        lines.append(f"Lang 7d  {lang_parts}")
    else:
        lines.append("Lang 7d  -")

    # Change Size line
    lines.append(f"Change Size 7d  median {fmt(m.change_median_7d, w.w_med)}  \u2022  p90 {fmt(m.change_p90_7d, w.w_p90)}")

    return lines


def format_day_lines(metrics: list[DayMetrics], widths: FormatWidths) -> list[list[str]]:
    """Return a list of 13-line text blocks, one per day."""
    return [_format_one_day(m, widths) for m in metrics]


# ---------------------------------------------------------------------------
# GraphSeries – precomputed series for graph rendering
# ---------------------------------------------------------------------------

@dataclass
class GraphSeries:
    cum_loc: list[int] = field(default_factory=list)
    cum_loc_min: int = 0
    cum_loc_range: int = 1
    cum_files: list[int] = field(default_factory=list)
    cum_files_min: int = 0
    cum_files_range: int = 1
    flow_add7: list[int] = field(default_factory=list)
    flow_del7: list[int] = field(default_factory=list)
    flow_max: int = 1
    is_new_max7: list[bool] = field(default_factory=list)
    is_new_max30: list[bool] = field(default_factory=list)


def compute_graph_series(metrics: list[DayMetrics]) -> GraphSeries:
    """Extract and normalize series for graph rendering."""
    cum_loc = [m.cumulative_loc_delta for m in metrics]
    cum_files = [m.cumulative_files_delta for m in metrics]
    flow_add7 = [m.loc_added_7d for m in metrics]
    flow_del7 = [m.loc_deleted_7d for m in metrics]

    cum_loc_min = min(cum_loc) if cum_loc else 0
    cum_loc_max = max(cum_loc) if cum_loc else 0
    cum_loc_range = max(1, cum_loc_max - cum_loc_min)

    cum_files_min = min(cum_files) if cum_files else 0
    cum_files_max = max(cum_files) if cum_files else 0
    cum_files_range = max(1, cum_files_max - cum_files_min)

    all_flow = flow_add7 + flow_del7
    flow_max = max(1, max(all_flow)) if all_flow else 1

    # Peak markers: True when max_loc_total_7d exceeds all prior values
    # First day is never a peak (no prior reference)
    is_new_max7: list[bool] = []
    if metrics:
        is_new_max7.append(False)
        prev_max7 = metrics[0].max_loc_total_7d
        for m in metrics[1:]:
            if m.max_loc_total_7d > prev_max7:
                is_new_max7.append(True)
                prev_max7 = m.max_loc_total_7d
            else:
                is_new_max7.append(False)

    is_new_max30: list[bool] = []
    if metrics:
        is_new_max30.append(False)
        prev_max30 = metrics[0].max_loc_total_30d
        for m in metrics[1:]:
            if m.max_loc_total_30d > prev_max30:
                is_new_max30.append(True)
                prev_max30 = m.max_loc_total_30d
            else:
                is_new_max30.append(False)

    return GraphSeries(
        cum_loc=cum_loc, cum_loc_min=cum_loc_min, cum_loc_range=cum_loc_range,
        cum_files=cum_files, cum_files_min=cum_files_min, cum_files_range=cum_files_range,
        flow_add7=flow_add7, flow_del7=flow_del7, flow_max=flow_max,
        is_new_max7=is_new_max7, is_new_max30=is_new_max30,
    )


# ---------------------------------------------------------------------------
# Polyline point precomputation
# ---------------------------------------------------------------------------

def _precompute_polyline_points(
    series: GraphSeries, layout: LayoutMetrics, n_days: int
) -> tuple[list[tuple[int, int]], list[tuple[int, int]], list[tuple[int, int]], list[tuple[int, int]]]:
    """Compute (x, y) polyline points for all 4 graph series.

    Returns (pts_loc, pts_files, pts_flow_add, pts_flow_del).
    """
    gx1 = layout.graph1_bbox[0]
    gx2 = layout.graph1_bbox[2]

    def x_for(i: int) -> int:
        if n_days <= 1:
            return gx1
        return gx1 + int(i * (gx2 - gx1) / (n_days - 1))

    def y_norm(value: int, vmin: int, vrange: int, gy1: int, gy2: int) -> int:
        """Map value to y pixel. Higher values -> top (gy1), lower -> bottom (gy2)."""
        if vrange <= 0:
            return gy2
        frac = (value - vmin) / vrange
        return int(gy2 - frac * (gy2 - gy1))

    # Graph 1: cumulative LOC
    g1y1, g1y2 = layout.graph1_bbox[1], layout.graph1_bbox[3]
    pts_loc = [
        (x_for(i), y_norm(series.cum_loc[i], series.cum_loc_min, series.cum_loc_range, g1y1, g1y2))
        for i in range(n_days)
    ]

    # Graph 2: cumulative files
    g2y1, g2y2 = layout.graph2_bbox[1], layout.graph2_bbox[3]
    pts_files = [
        (x_for(i), y_norm(series.cum_files[i], series.cum_files_min, series.cum_files_range, g2y1, g2y2))
        for i in range(n_days)
    ]

    # Graph 3: flow (adds and deletes 7d)
    g3y1, g3y2 = layout.graph3_bbox[1], layout.graph3_bbox[3]
    pts_flow_add = [
        (x_for(i), y_norm(series.flow_add7[i], 0, series.flow_max, g3y1, g3y2))
        for i in range(n_days)
    ]
    pts_flow_del = [
        (x_for(i), y_norm(series.flow_del7[i], 0, series.flow_max, g3y1, g3y2))
        for i in range(n_days)
    ]

    return pts_loc, pts_files, pts_flow_add, pts_flow_del
