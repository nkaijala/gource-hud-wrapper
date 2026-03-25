import os
import tempfile
from unittest.mock import patch
from gource_hud.overlay import (
    compute_layout, LayoutMetrics,
    thousands, fmt, compute_format_widths, format_day_lines,
    compute_graph_series, GraphSeries, _precompute_polyline_points,
    find_mono_font, render_overlays,
)
from gource_hud.stats import DayMetrics
from PIL import Image


class TestComputeLayout:
    def test_1080p(self):
        layout = compute_layout(1920, 1080, 1.0, 14, 640)
        assert layout.font_size == 14
        assert layout.line_gap == 18
        assert layout.pad_x == 16
        assert layout.pad_y == 12
        assert layout.graph_h == 140
        assert layout.graph_gap == 14
        assert layout.panel_w == 640
        assert layout.panel_h == 720
        assert layout.rect_x1 == 0
        assert layout.rect_y1 == 360
        assert layout.rect_x2 == 640
        assert layout.rect_y2 == 1080

    def test_4k(self):
        layout = compute_layout(3840, 2160, 2.0, 14, 640)
        assert layout.font_size == 28
        assert layout.line_gap == 37
        assert layout.panel_w == 1280

    def test_text_above_graph1(self):
        layout = compute_layout(1920, 1080, 1.0, 14, 640)
        text_bottom = layout.text_y_start + 13 * layout.line_gap
        assert text_bottom <= layout.graph1_bbox[1]

    def test_graphs_dont_overlap(self):
        layout = compute_layout(1920, 1080, 1.0, 14, 640)
        assert layout.graph1_bbox[3] <= layout.graph2_bbox[1]
        assert layout.graph2_bbox[3] <= layout.graph3_bbox[1]

    def test_panel_fits_in_frame(self):
        layout = compute_layout(1920, 1080, 1.0, 14, 640)
        assert layout.rect_y1 >= 0
        assert layout.rect_x2 <= 1920
        assert layout.rect_y2 == 1080


class TestFormatting:
    def test_thousands(self):
        assert thousands(0) == "0"
        assert thousands(999) == "999"
        assert thousands(1000) == "1,000"
        assert thousands(1234567) == "1,234,567"
        assert thousands(-42) == "-42"

    def test_fmt_right_justify(self):
        assert fmt(42, 7) == "     42"
        assert fmt(1000, 7) == "  1,000"

    def test_format_day_lines_count(self):
        m = DayMetrics(timestamp=0)
        widths = compute_format_widths([m])
        lines = format_day_lines([m], widths)
        assert len(lines) == 1
        assert len(lines[0]) == 13

    def test_format_day_lines_fixed_width(self):
        m1 = DayMetrics(timestamp=0, loc_added_1d=10, loc_deleted_1d=2)
        m2 = DayMetrics(timestamp=86400, loc_added_1d=1000, loc_deleted_1d=500)
        widths = compute_format_widths([m1, m2])
        lines = format_day_lines([m1, m2], widths)
        for line_idx in range(13):
            assert len(lines[0][line_idx]) == len(lines[1][line_idx])


class TestGraphSeries:
    def test_cumulative_loc(self):
        metrics = [
            DayMetrics(timestamp=0, cumulative_loc_delta=7),
            DayMetrics(timestamp=86400, cumulative_loc_delta=22),
            DayMetrics(timestamp=172800, cumulative_loc_delta=25),
        ]
        series = compute_graph_series(metrics)
        assert series.cum_loc == [7, 22, 25]
        assert series.cum_loc_min == 7
        assert series.cum_loc_range == 18

    def test_single_day_range_clamped(self):
        metrics = [DayMetrics(timestamp=0, cumulative_loc_delta=5)]
        series = compute_graph_series(metrics)
        assert series.cum_loc_range == 1

    def test_peak_markers(self):
        metrics = [
            DayMetrics(timestamp=0, max_loc_total_7d=10),
            DayMetrics(timestamp=86400, max_loc_total_7d=20),
            DayMetrics(timestamp=172800, max_loc_total_7d=20),
            DayMetrics(timestamp=259200, max_loc_total_7d=25),
        ]
        series = compute_graph_series(metrics)
        assert series.is_new_max7 == [False, True, False, True]


class TestPolylinePoints:
    def test_x_spacing(self):
        metrics = [DayMetrics(timestamp=i * 86400, cumulative_loc_delta=i * 10) for i in range(5)]
        series = compute_graph_series(metrics)
        layout = compute_layout(1920, 1080, 1.0, 14, 640)
        pts_loc, _, _, _ = _precompute_polyline_points(series, layout, 5)
        assert len(pts_loc) == 5
        assert pts_loc[0][0] == 16   # gx1
        assert pts_loc[4][0] == 624  # gx2

    def test_y_normalization(self):
        metrics = [
            DayMetrics(timestamp=0, cumulative_loc_delta=0),
            DayMetrics(timestamp=86400, cumulative_loc_delta=50),
            DayMetrics(timestamp=172800, cumulative_loc_delta=100),
        ]
        series = compute_graph_series(metrics)
        layout = compute_layout(1920, 1080, 1.0, 14, 640)
        pts_loc, _, _, _ = _precompute_polyline_points(series, layout, 3)
        gy1 = layout.graph1_bbox[1]
        gy2 = layout.graph1_bbox[3]
        assert pts_loc[0][1] == gy2  # min value -> bottom
        assert pts_loc[2][1] == gy1  # max value -> top

    def test_single_day_no_points(self):
        metrics = [DayMetrics(timestamp=0, cumulative_loc_delta=42)]
        series = compute_graph_series(metrics)
        layout = compute_layout(1920, 1080, 1.0, 14, 640)
        pts_loc, _, _, _ = _precompute_polyline_points(series, layout, 1)
        assert len(pts_loc) == 1


class TestFindMonoFont:
    def test_finds_system_font(self):
        try:
            path = find_mono_font()
            assert os.path.isfile(path)
        except RuntimeError:
            import pytest
            pytest.skip("No system monospaced font found")

    def test_raises_when_no_font(self):
        import pytest
        with patch("os.path.isfile", return_value=False):
            with pytest.raises(RuntimeError, match="No monospaced font"):
                find_mono_font()


class TestRenderOverlays:
    def test_empty_returns_zero(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            count = render_overlays([], tmpdir, 1920, 1080)
            assert count == 0

    def test_single_frame_output(self):
        m = DayMetrics(timestamp=0)
        with tempfile.TemporaryDirectory() as tmpdir:
            count = render_overlays([m], tmpdir, 1920, 1080, jobs=1)
            assert count == 1
            out_path = os.path.join(tmpdir, "overlay_00000.png")
            assert os.path.exists(out_path)
            im = Image.open(out_path)
            assert im.mode == "RGBA"
            assert im.size == (1920, 1080)

    def test_panel_not_transparent(self):
        m = DayMetrics(timestamp=0)
        with tempfile.TemporaryDirectory() as tmpdir:
            render_overlays([m], tmpdir, 1920, 1080, jobs=1)
            im = Image.open(os.path.join(tmpdir, "overlay_00000.png"))
            pixel = im.getpixel((100, 1000))
            assert pixel[3] > 0

    def test_outside_panel_transparent(self):
        m = DayMetrics(timestamp=0)
        with tempfile.TemporaryDirectory() as tmpdir:
            render_overlays([m], tmpdir, 1920, 1080, jobs=1)
            im = Image.open(os.path.join(tmpdir, "overlay_00000.png"))
            pixel = im.getpixel((1900, 10))
            assert pixel[3] == 0
