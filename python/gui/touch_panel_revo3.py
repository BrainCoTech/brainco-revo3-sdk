"""Revo3 Touch Panel - For Revo3 Tactile Array devices

Displays Revo3 tactile array data:
- Summary: 16 values (palm + 5 fingers × 3 locations)
- Detail: 11 tactile array modules as heatmaps

Tabs:
- Summary: 16-line curves + status cards
- Per-finger heatmap tabs (Palm, Thumb, Index, Middle, Ring, Pinky)
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QGridLayout, QTabWidget
)

from .touch_common import (
    SummaryChart, HeatmapChart, build_status_cards,
    run_async, logger
)
from .i18n import tr

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from common_imports import sdk


# Summary: 42 values (mapped 4100~4141)
REVO3_SUMMARY_NAMES = [
    "Palm",
    "Thumb T1", "Thumb T2", "Thumb T3",
    "Thumb P1", "Thumb P2", "Thumb P3", "Thumb P4", "Thumb P5", "Thumb P6",
    "Index T1", "Index T2", "Index T3",
    "Index P1", "Index P2", "Index P3", "Index P4", "Index P5",
    "Middle T1", "Middle T2", "Middle T3",
    "Middle P1", "Middle P2", "Middle P3", "Middle P4", "Middle P5",
    "Ring T1", "Ring T2", "Ring T3",
    "Ring P1", "Ring P2", "Ring P3", "Ring P4", "Ring P5",
    "Pinky T1", "Pinky T2", "Pinky T3",
    "Pinky P1", "Pinky P2", "Pinky P3", "Pinky P4", "Pinky P5",
]

REVO3_SUMMARY_COLORS = [
    (100, 255, 255),
    (255, 100, 100), (255, 120, 120), (255, 140, 140), (255, 160, 160), (255, 180, 180), (255, 200, 200), (220, 80, 80), (200, 60, 60), (180, 40, 40),
    (100, 255, 100), (120, 255, 120), (140, 255, 140), (160, 255, 160), (180, 255, 180), (80, 220, 80), (60, 200, 60), (40, 180, 40),
    (100, 100, 255), (120, 120, 255), (140, 140, 255), (160, 160, 255), (180, 180, 255), (80, 80, 220), (60, 60, 200), (40, 40, 180),
    (255, 255, 100), (255, 255, 120), (255, 255, 140), (255, 255, 160), (255, 255, 180), (220, 220, 80), (200, 200, 60), (180, 180, 40),
    (255, 100, 255), (255, 120, 255), (255, 140, 255), (255, 160, 255), (255, 180, 255), (220, 80, 220), (200, 60, 200), (180, 40, 180),
]

# Detail: 11 modules
REVO3_MODULE_NAMES = [
    "Palm", "ThumbTip", "ThumbPad", "IndexTip", "IndexPad",
    "MiddleTip", "MiddlePad", "RingTip", "RingPad", "PinkyTip", "PinkyPad"
]

REVO3_MODULE_COLORS = [
    (0, 230, 230),
    (255, 100, 100), (255, 160, 120),
    (100, 255, 100), (140, 255, 160),
    (100, 140, 255), (140, 180, 255),
    (255, 255, 100), (255, 220, 140),
    (255, 100, 255), (255, 160, 230),
]

REVO3_MODULE_POINTS = {
    "Palm": 36,
    "ThumbTip": 31, "ThumbPad": 57,
    "IndexTip": 21, "IndexPad": 52,
    "MiddleTip": 21, "MiddlePad": 52,
    "RingTip": 21, "RingPad": 52,
    "PinkyTip": 21, "PinkyPad": 52,
}

REVO3_HEATMAP_LAYOUT = {
    "Palm":      (9, 6),
    "ThumbTip":  (9, 7),
    "ThumbPad":  (14, 8),
    "IndexTip":  (8, 6), "IndexPad":  (13, 8),
    "MiddleTip": (8, 6), "MiddlePad": (13, 8),
    "RingTip":   (8, 6), "RingPad":   (13, 8),
    "PinkyTip":  (8, 6), "PinkyPad":  (13, 8),
}

# Explicit coordinate maps (from physical layout diagrams)
# Format: coord_map[i] = (row, col) in heatmap grid  (sensor index = i+1)
# Reference images: docs/touch/images/revo3_*.png (right-side black grid)
REVO3_COORD_MAP = {
    # ThumbTip — 31 pts, grid 9 rows × 7 cols (image x:0-6, y:0-8)
    "ThumbTip": [
        (0, 0), (0, 1), (0, 3), (0, 4),           # 1-4
        (1, 0), (1, 1), (1, 3), (1, 4), (1, 5),   # 5-9
        (2, 0), (2, 1), (2, 2), (2, 3), (2, 4), (2, 5), # 10-15
        (3, 0), (3, 1), (3, 2), (3, 3), (3, 4), (3, 5), # 16-21
        (4, 0), (4, 1), (4, 2), (4, 3), (4, 4), (4, 5), # 22-27
        (5, 6), (6, 6), (7, 6), (8, 6),           # 28-31
    ],

    # ThumbPad — 57 pts, grid 14 rows × 8 cols (image x:0-7, y:0-13)
    "ThumbPad": [
        (0, 0), (0, 1), (0, 2), (0, 3), (0, 4),           # 1-5
        (1, 0), (1, 1), (1, 2), (1, 3), (1, 4),           # 6-10
        (2, 0), (2, 1), (2, 2), (2, 3), (2, 4),           # 11-15
        (3, 0), (3, 1), (3, 2), (3, 3), (3, 4),           # 16-20
        (4, 0), (4, 1), (4, 2), (4, 3), (4, 4),           # 21-25
        (5, 0), (5, 1), (5, 2), (5, 3), (5, 4),           # 26-30
        (6, 0), (6, 1), (6, 2), (6, 3), (6, 4),           # 31-35
        (7, 0), (7, 1), (7, 2), (7, 3), (7, 4),           # 36-40
        (8, 1), (8, 2), (8, 3),                           # 41-43
        (9, 1), (9, 2),                                   # 44-45
        (10, 5), (10, 6), (10, 7),                        # 46-48
        (11, 5), (11, 6), (11, 7),                        # 49-51
        (12, 5), (12, 6), (12, 7),                        # 52-54
        (13, 5), (13, 6), (13, 7),                        # 55-57
    ],

    # FourFingerTip (Index/Middle/Ring/Pinky Tip) — 21 pts, 8 rows × 6 cols
    # (image x:0-5, y:0-8)
    "FourFingerTip": [
        (0, 1), (0, 2), (0, 3),           # 1-3
        (1, 1), (1, 2), (1, 3),           # 4-6
        (2, 1), (2, 2), (2, 3), (2, 4),   # 7-10
        (3, 1), (3, 2), (3, 3), (3, 4),   # 11-14
        (4, 1), (4, 2), (4, 3), (4, 4),   # 15-18
        (5, 5), (6, 5), (7, 5),           # 19-21
    ],

    # FourFingerPad (Index/Middle/Ring/Pinky Pad) — 52 pts, grid 13 rows × 8 cols
    # (image x:0-7, y:0-12)
    "FourFingerPad": [
        (0, 1), (0, 5),                                   # 1-2
        (1, 1), (1, 2), (1, 3), (1, 4),                   # 3-6
        (2, 1), (2, 2), (2, 3), (2, 4),                   # 7-10
        (3, 0), (3, 1), (3, 2), (3, 3), (3, 4),           # 11-15
        (4, 1), (4, 2), (4, 3), (4, 4), (4, 5),           # 16-20
        (5, 1), (5, 2), (5, 3), (5, 4), (5, 5),           # 21-25
        (6, 1), (6, 2), (6, 3), (6, 4), (6, 5),           # 26-30
        (7, 1), (7, 2), (7, 3), (7, 4), (7, 5),           # 31-35
        (8, 1), (8, 2), (8, 3), (8, 4), (8, 5),           # 36-40
        (9, 5), (9, 6), (9, 7),                           # 41-43
        (10, 5), (10, 6), (10, 7),                        # 44-46
        (11, 5), (11, 6), (11, 7),                        # 47-49
        (12, 5), (12, 6), (12, 7),                        # 50-52
    ],

    # Palm — 36 pts, grid 9 rows × 6 cols (image x:0-5, y:0-8)
    "Palm": [
        (0, 1), (0, 2), (0, 3), (0, 4), (0, 5),           # 1-5
        (1, 0), (1, 1), (1, 2), (1, 3), (1, 4), (1, 5),   # 6-11
        (2, 0), (2, 1), (2, 2), (2, 3), (2, 4), (2, 5),   # 12-17
        (3, 0), (3, 3), (3, 4), (3, 5),                   # 18-21
        (4, 0), (4, 3), (4, 4), (4, 5),                   # 22-25
        (5, 0), (5, 3), (5, 4), (5, 5),                   # 26-29
        (6, 0), (6, 3), (6, 5),                           # 30-32
        (7, 0), (7, 4), (7, 5),                           # 33-35
        (8, 5),                                           # 36
    ],

    # PalmLeft — 36 pts, grid 9 rows × 6 cols (image x:0-5, y:0-8)
    "PalmLeft": [
        (0, 0), (0, 1), (0, 2), (0, 3), (0, 4),           # 1-5
        (1, 0), (1, 1), (1, 2), (1, 3), (1, 4), (1, 5),   # 6-11
        (2, 0), (2, 1), (2, 2), (2, 3), (2, 4), (2, 5),   # 12-17
        (3, 0), (3, 1), (3, 2), (3, 5),                   # 18-21
        (4, 0), (4, 1), (4, 2), (4, 5),                   # 22-25
        (5, 0), (5, 1), (5, 2), (5, 5),                   # 26-29
        (6, 0), (6, 2), (6, 5),                           # 30-32
        (7, 0), (7, 1), (7, 5),                           # 33-35
        (8, 0),                                           # 36
    ],
}


def _get_revo3_coord_map(module_name: str):
    """Get coordinate map for a Revo3 touch module"""
    if module_name in REVO3_COORD_MAP:
        return REVO3_COORD_MAP[module_name]
    if module_name in ("IndexTip", "MiddleTip", "RingTip", "PinkyTip"):
        return REVO3_COORD_MAP["FourFingerTip"]
    if module_name in ("IndexPad", "MiddlePad", "RingPad", "PinkyPad"):
        return REVO3_COORD_MAP["FourFingerPad"]
    return None


class Revo3TouchSubPanel(QWidget):
    """Revo3 Touch Panel for Revo3 Tactile Array devices.

    Tabs:
    - Summary: 16-line curves + status cards
    - Per-finger: Heatmap tabs (Palm, Thumb, Index, Middle, Ring, Pinky)
    """

    def __init__(self):
        super().__init__()
        self.device = None
        self.slave_id = 1
        self.detail_charts = [None] * 11
        self.sensor_cards = []
        self.sensor_bars = []
        self.sensor_labels = []
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # --- Data Type Control Bar ---
        from PySide6.QtWidgets import QHBoxLayout, QLabel, QComboBox, QPushButton
        ctrl_layout = QHBoxLayout()
        ctrl_layout.setContentsMargins(8, 4, 8, 4)
        ctrl_layout.setSpacing(8)

        self.type_label = QLabel("Touch Data Type:")
        ctrl_layout.addWidget(self.type_label)

        self.type_combo = QComboBox()
        self.type_combo.addItems(["Pressure Array (点阵)", "Force Summary (合力)"])
        self.type_combo.currentIndexChanged.connect(self._on_type_changed)
        self.type_combo.setEnabled(False)
        ctrl_layout.addWidget(self.type_combo)

        self.read_btn = QPushButton("Read")
        self.read_btn.clicked.connect(self._read_data_type)
        self.read_btn.setEnabled(False)
        ctrl_layout.addWidget(self.read_btn)

        # Touch zero drift calibration button
        self.zero_calibrate_btn = QPushButton("Zero Calibration")
        self.zero_calibrate_btn.clicked.connect(self._zero_calibrate)
        self.zero_calibrate_btn.setEnabled(False)
        ctrl_layout.addWidget(self.zero_calibrate_btn)

        ctrl_layout.addStretch()
        layout.addLayout(ctrl_layout)

        self.tabs = QTabWidget()

        # --- Tab 1: Summary ---
        overview_widget = QWidget()
        overview_layout = QGridLayout(overview_widget)
        overview_layout.setSpacing(8)

        self.summary_chart = SummaryChart(
            "Touch Summary", (0, 5000),
            sensor_names=REVO3_SUMMARY_NAMES,
            sensor_colors=REVO3_SUMMARY_COLORS,
        )
        overview_layout.addWidget(self.summary_chart, 0, 0, 2, 1)

        status_widget = QWidget()
        status_layout = QVBoxLayout(status_widget)
        status_layout.setSpacing(4)
        self.sensor_cards, self.sensor_bars, self.sensor_labels = build_status_cards(
            status_layout, REVO3_SUMMARY_NAMES, REVO3_SUMMARY_COLORS, is_compact=True
        )
        overview_layout.addWidget(status_widget, 0, 1, 2, 1)
        overview_layout.setColumnStretch(0, 3)
        overview_layout.setColumnStretch(1, 1)

        self.tabs.addTab(overview_widget, "📊 Summary")

        # --- Detail tabs: grouped by finger ---
        revo3_finger_groups = [
            ("Palm", "🖐", [(0, "Palm", "Palm")]),
            ("Thumb", "👆", [(1, "Thumb Tip", "ThumbTip"), (2, "Thumb Pad", "ThumbPad")]),
            ("Index", "👆", [(3, "Index Tip", "IndexTip"), (4, "Index Pad", "IndexPad")]),
            ("Middle", "👆", [(5, "Middle Tip", "MiddleTip"), (6, "Middle Pad", "MiddlePad")]),
            ("Ring", "👆", [(7, "Ring Tip", "RingTip"), (8, "Ring Pad", "RingPad")]),
            ("Pinky", "👆", [(9, "Pinky Tip", "PinkyTip"), (10, "Pinky Pad", "PinkyPad")]),
        ]

        for group_name, icon, modules in revo3_finger_groups:
            if len(modules) == 1:
                mod_idx, name, mod_key = modules[0]
                color = REVO3_MODULE_COLORS[mod_idx]
                pts = REVO3_MODULE_POINTS[mod_key]
                rows, cols = REVO3_HEATMAP_LAYOUT[mod_key]
                coord_map = _get_revo3_coord_map(mod_key)
                chart = HeatmapChart(name, pts, color, rows, cols, coord_map=coord_map)
                self.detail_charts[mod_idx] = chart
                self.tabs.addTab(chart, f"{icon} {group_name}")
            else:
                finger_widget = QWidget()
                finger_layout = QVBoxLayout(finger_widget)
                finger_layout.setContentsMargins(0, 0, 0, 0)
                finger_layout.setSpacing(4)

                for mod_idx, name, mod_key in modules:
                    color = REVO3_MODULE_COLORS[mod_idx]
                    pts = REVO3_MODULE_POINTS[mod_key]
                    rows, cols = REVO3_HEATMAP_LAYOUT[mod_key]
                    coord_map = _get_revo3_coord_map(mod_key)
                    chart = HeatmapChart(name, pts, color, rows, cols, coord_map=coord_map)
                    self.detail_charts[mod_idx] = chart
                    finger_layout.addWidget(chart, 1)

                self.tabs.addTab(finger_widget, f"{icon} {group_name}")

        layout.addWidget(self.tabs, 1)
        self.tabs.currentChanged.connect(self._on_tab_changed)

    def update_data(self, revo3_data):
        """Process Revo3 Touch data.

        revo3_data: object with .summary (list of 42) and .modules (list of 11 lists)
        """
        if not hasattr(revo3_data, 'summary') or not hasattr(revo3_data, 'modules'):
            return

        summary = revo3_data.summary
        modules = revo3_data.modules

        # Update summary
        if summary and len(summary) >= 42:
            summary_42 = list(summary[:42])
            self.summary_chart.add_data(summary_42)
            for i, val in enumerate(summary_42):
                if i < len(self.sensor_bars):
                    self.sensor_bars[i].setValue(min(val, 5000))
                    self.sensor_labels[i].setText(f"{val}")

        # Update detail
        if modules:
            for i, module_points in enumerate(modules):
                if i < len(self.detail_charts) and self.detail_charts[i] is not None and module_points:
                    self.detail_charts[i].add_data(module_points)

    def clear(self):
        self.summary_chart.clear()
        for chart in self.detail_charts:
            if chart is not None:
                chart.clear()

    def update_texts(self):
        self.tabs.setTabText(0, f"📊 {tr('touch_summary')}")
        
        revo3_finger_groups = [
            ("touch_palm", "🖐"),
            ("touch_thumb", "👆"),
            ("touch_index", "👆"),
            ("touch_middle", "👆"),
            ("touch_ring", "👆"),
            ("touch_pinky", "👆"),
        ]
        
        for i, (tr_key, icon) in enumerate(revo3_finger_groups):
            self.tabs.setTabText(i + 1, f"{icon} {tr(tr_key)}")

        # Update control bar texts dynamically (supporting translation dynamically)
        self.type_label.setText(tr("touch_data_type") if tr("touch_data_type") != "touch_data_type" else "Touch Data Type:")
        self.read_btn.setText(tr("btn_read") if tr("btn_read") != "btn_read" else "Read")
        self.zero_calibrate_btn.setText(
            tr("btn_touch_zero_calibrate")
            if tr("btn_touch_zero_calibrate") != "btn_touch_zero_calibrate"
            else "Zero Calibration"
        )

    def _on_tab_changed(self, index):
        if not self.device:
            return
        # index: 0 = Summary (Force Summary = 1), >0 = Finger detail (Pressure Array = 0)
        target_type = 1 if index == 0 else 0
        if self.type_combo.currentIndex() != target_type:
            mode_str = "Force Summary" if target_type == 1 else "Pressure Array"
            tab_name = self.tabs.tabText(index)
            logger.info(
                f"Tab changed to {index} ({tab_name}). "
                f"Automatically switching touch data type to {target_type} ({mode_str})"
            )
            self.type_combo.setCurrentIndex(target_type)

    def _on_type_changed(self, index):
        if not self.device:
            return
        # index: 0 = Pressure Array (点阵), 1 = Force Summary (合力)
        val = int(index)
        mode_str = "Force Summary" if val == 1 else "Pressure Array"
        logger.info(f"Setting touch data type to {val} ({mode_str})")
        try:
            from common_imports import sdk
            if sdk is not None and hasattr(sdk, "TouchDataMode"):
                mode = sdk.TouchDataMode(val)
            else:
                mode = val
            run_async(lambda: self.device.revo3_set_touch_data_type(self.slave_id, mode))
        except Exception as e:
            logger.error(f"Failed to set touch data type: {e}")

    def _read_data_type(self):
        if not self.device:
            return
        async def fetch():
            try:
                val = await self.device.revo3_get_touch_data_type(self.slave_id)
                val_int = int(val)
                mode_str = "Force Summary" if val_int == 1 else "Pressure Array"
                logger.info(f"Fetched touch data type: {val_int} ({mode_str})")
                # block signals temporarily to avoid triggering currentIndexChanged
                self.type_combo.blockSignals(True)
                self.type_combo.setCurrentIndex(1 if val_int == 1 else 0)
                self.type_combo.blockSignals(False)
            except Exception as e:
                logger.error(f"Failed to read touch data type: {e}")
        run_async(fetch)

    def _zero_calibrate(self):
        if not self.device:
            return
        logger.info("Calibrating touch sensor zero drift...")
        try:
            run_async(lambda: self.device.revo3_calibrate_touch_zero(self.slave_id))
        except Exception as e:
            logger.error(f"Failed to calibrate touch zero drift: {e}")

    def set_device(self, device, slave_id, device_info=None, shared_data=None):
        self.device = device
        self.slave_id = slave_id
        # Enable controls
        self.type_combo.setEnabled(True)
        self.read_btn.setEnabled(True)
        self.zero_calibrate_btn.setEnabled(True)
        # Read current data type asynchronously
        self._read_data_type()

    def clear_device(self):
        self.device = None
        self.type_combo.setEnabled(False)
        self.read_btn.setEnabled(False)
        self.zero_calibrate_btn.setEnabled(False)
