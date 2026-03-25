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
