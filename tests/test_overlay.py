import os
from gource_hud.overlay import compute_layout, LayoutMetrics


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
