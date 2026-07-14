"""Revo3 Touch Panel - For Revo3 Tactile Array devices

Displays Revo3 tactile array data:
- Summary: 42 pressure values or Matrix module aggregates
- Detail: 11 tactile array modules as heatmaps

Tabs:
- Summary: 16-line curves + status cards
- Per-finger heatmap tabs (Palm, Thumb, Index, Middle, Ring, Pinky)
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QTabWidget, QGroupBox, QCheckBox,
    QFrame, QLabel, QComboBox, QPushButton, QMessageBox
)

from .touch_common import (
    SummaryChart, HeatmapChart, build_status_cards,
    run_async, logger
)
from .i18n import tr
from .styles import is_dark_mode

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from common_imports import sdk

if sdk is not None and hasattr(sdk, "TouchVendor"):
    TouchVendor = sdk.TouchVendor
else:
    class TouchVendor:
        Unknown = 0
        Pressure = 1
        Matrix = 2


def matrix_touch_tare_command(value: int):
    if sdk is not None and hasattr(sdk, "MatrixTouchTareCommand"):
        return sdk.MatrixTouchTareCommand(value)
    return value


def matrix_touch_output_mode(value: int):
    if sdk is not None and hasattr(sdk, "MatrixTouchOutputMode"):
        return sdk.MatrixTouchOutputMode(value)
    return value


def pressure_touch_force_tare_command(value: int):
    if sdk is not None and hasattr(sdk, "PressureTouchForceTareCommand"):
        return sdk.PressureTouchForceTareCommand(value)
    return value


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

# Pressure Touch regional force summary max: 20000 mN = 20 N.
PRESSURE_FORCE_LIMIT_MN = 20000.0

# Matrix Touch force range upper limit in raw units.
# Raw unit: 0.0001 N. Convert raw -> N by dividing by 10000,
# or raw -> mN by dividing by 10.
# Palm: 80N (800000), ThumbTip: 30N (300000), ThumbPad: 20N (200000)
# IndexTip/MiddleTip/RingTip/PinkyTip: 40N (400000)
# IndexPad/MiddlePad/RingPad/PinkyPad: 30N (300000)
MATRIX_FORCE_LIMITS = [
    800000,  # 0: Palm
    300000,  # 1: ThumbTip
    200000,  # 2: ThumbPad
    400000,  # 3: IndexTip
    300000,  # 4: IndexPad
    400000,  # 5: MiddleTip
    300000,  # 6: MiddlePad
    400000,  # 7: RingTip
    300000,  # 8: RingPad
    400000,  # 9: PinkyTip
    300000,  # 10: PinkyPad
]

REVO3_HEATMAP_LAYOUT = {
    "Palm":      (9, 6),
    "ThumbTip":  (9, 7),
    "ThumbPad":  (14, 8),
    "IndexTip":  (8, 6), "IndexPad":  (13, 8),
    "MiddleTip": (8, 6), "MiddlePad": (13, 8),
    "RingTip":   (8, 6), "RingPad":   (13, 8),
    "PinkyTip":  (8, 6), "PinkyPad":  (13, 8),
}

REVO3_MATRIX_HEATMAP_LAYOUT = {name: (10, 6) for name in REVO3_MODULE_NAMES}

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
        self.matrix_modes = [1] * 11
        self.detail_charts = [None] * 11
        self.sensor_cards = []
        self.sensor_bars = []
        self.sensor_labels = []
        self.module_checks = []
        self.touch_vendor = TouchVendor.Pressure
        self.is_matrix_touch = False
        self.matrix_point_counts = [53, 56, 22, 22, 27, 22, 27, 22, 27, 22, 27]
        self.matrix_module_sns = []
        self.module_info = [
            # (module_id, name_en, name_zh, row, col)
            (0, "Palm", "手掌", 0, 0),
            (1, "Thumb Tip", "大拇指尖", 0, 1),
            (2, "Thumb Pad", "大拇指指腹", 1, 1),
            (3, "Index Tip", "食指尖", 0, 2),
            (4, "Index Pad", "食指指腹", 1, 2),
            (5, "Middle Tip", "中指尖", 0, 3),
            (6, "Middle Pad", "中指指腹", 1, 3),
            (7, "Ring Tip", "无名指尖", 0, 4),
            (8, "Ring Pad", "无名指指腹", 1, 4),
            (9, "Pinky Tip", "小指尖", 0, 5),
            (10, "Pinky Pad", "小指指腹", 1, 5)
        ]
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
        self.type_combo.addItems(["Tactile Array (点阵)", "Force Summary (合力)"])
        self.type_combo.currentIndexChanged.connect(self._on_type_changed)
        self.type_combo.setEnabled(False)
        ctrl_layout.addWidget(self.type_combo)

        self.read_btn = QPushButton("Read Enable State")
        self.read_btn.clicked.connect(self._read_all_settings)
        self.read_btn.setEnabled(False)
        ctrl_layout.addWidget(self.read_btn)

        self.read_sn_btn = QPushButton("Read SN")
        self.read_sn_btn.clicked.connect(self._read_matrix_module_sns)
        self.read_sn_btn.setEnabled(False)
        self.read_sn_btn.setVisible(False)
        ctrl_layout.addWidget(self.read_sn_btn)

        self.read_points_btn = QPushButton("Read Points")
        self.read_points_btn.clicked.connect(self._read_matrix_point_counts)
        self.read_points_btn.setEnabled(False)
        self.read_points_btn.setVisible(False)
        ctrl_layout.addWidget(self.read_points_btn)

        self.read_output_mode_btn = QPushButton("Read Module Value Type")
        self.read_output_mode_btn.clicked.connect(self._read_matrix_output_mode)
        self.read_output_mode_btn.setEnabled(False)
        self.read_output_mode_btn.setVisible(False)
        ctrl_layout.addWidget(self.read_output_mode_btn)

        self.read_tare_status_btn = QPushButton("Read Tare State")
        self.read_tare_status_btn.clicked.connect(self._read_matrix_tare_status)
        self.read_tare_status_btn.setEnabled(False)
        self.read_tare_status_btn.setVisible(False)
        ctrl_layout.addWidget(self.read_tare_status_btn)

        # Touch zero drift calibration button
        self.zero_calibrate_btn = QPushButton("Zero Calibration")
        self.zero_calibrate_btn.clicked.connect(self._zero_calibrate)
        self.zero_calibrate_btn.setEnabled(False)
        ctrl_layout.addWidget(self.zero_calibrate_btn)

        # Touch zero cancel button
        self.zero_cancel_btn = QPushButton("Zero Cancel")
        self.zero_cancel_btn.clicked.connect(self._zero_cancel)
        self.zero_cancel_btn.setEnabled(False)
        self.zero_cancel_btn.setVisible(False)
        ctrl_layout.addWidget(self.zero_cancel_btn)

        self.pressure_force_clear_btn = QPushButton("Regional Force Zero")
        self.pressure_force_clear_btn.clicked.connect(self._pressure_force_clear)
        self.pressure_force_clear_btn.setEnabled(False)
        self.pressure_force_clear_btn.setVisible(False)
        ctrl_layout.addWidget(self.pressure_force_clear_btn)

        self.pressure_force_restore_btn = QPushButton("Restore Regional Force")
        self.pressure_force_restore_btn.clicked.connect(self._pressure_force_restore)
        self.pressure_force_restore_btn.setEnabled(False)
        self.pressure_force_restore_btn.setVisible(False)
        ctrl_layout.addWidget(self.pressure_force_restore_btn)

        ctrl_layout.addStretch()
        layout.addLayout(ctrl_layout)

        is_dark = is_dark_mode()
        group_border = "#444444" if is_dark else "#cfd4d9"
        group_title_color = "#00FF66" if is_dark else "#2c3e50"
        cb_text_color = "#CCCCCC" if is_dark else "#495057"
        cb_border_color = "#555555" if is_dark else "#ced4da"
        cb_bg_color = "#2D2D2D" if is_dark else "#ffffff"
        cb_checked_border = "#00FF66" if is_dark else "#2ecc71"
        cb_checked_bg = "#008833" if is_dark else "#2ecc71"
        cb_disabled_border = "#333333" if is_dark else "#dee2e6"
        cb_disabled_bg = "#1F1F1F" if is_dark else "#e9ecef"

        modules_group = QGroupBox("Active Touch Modules (激活触觉模块)")
        modules_group.setStyleSheet(f"""
            QGroupBox {{
                border: 1px solid {group_border};
                border-radius: 6px;
                margin-top: 8px;
                padding-top: 8px;
                font-weight: bold;
                color: {group_title_color};
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 3px 0 3px;
            }}
        """)
        modules_layout = QGridLayout(modules_group)
        modules_layout.setContentsMargins(8, 8, 8, 8)
        modules_layout.setSpacing(8)

        for item in self.module_info:
            mod_id, name_en, name_zh, row, col = item
            cb = QCheckBox(f"{name_zh} ({name_en})")
            cb.setEnabled(False)
            cb.setStyleSheet(f"""
                QCheckBox {{
                    spacing: 6px;
                    font-size: 11px;
                    font-weight: bold;
                    color: {cb_text_color};
                }}
                QCheckBox::indicator {{
                    width: 14px;
                    height: 14px;
                    border-radius: 7px;
                    border: 2px solid {cb_border_color};
                    background-color: {cb_bg_color};
                }}
                QCheckBox::indicator:checked {{
                    border: 2px solid {cb_checked_border};
                    background-color: {cb_checked_bg};
                }}
                QCheckBox::indicator:checked:disabled {{
                    border: 2px solid {cb_checked_border};
                    background-color: {cb_checked_bg};
                }}
                QCheckBox::indicator:disabled {{
                    border: 2px solid {cb_disabled_border};
                    background-color: {cb_disabled_bg};
                }}
            """)
            # Connect clicked signal to handler
            cb.clicked.connect(lambda checked, mid=mod_id: self._on_module_toggle(mid, checked))

            # Palm module spans 2 rows for layout balance
            if mod_id == 0:
                modules_layout.addWidget(cb, 0, 0, 2, 1)
            else:
                modules_layout.addWidget(cb, row, col)
            self.module_checks.append(cb)

        layout.addWidget(modules_group)

        self.tabs = QTabWidget()
        self.tabs.tabBar().setElideMode(Qt.ElideNone)
        self.tabs.tabBar().setExpanding(False)

        # --- Tab 1: Summary ---
        overview_widget = QWidget()
        self.overview_layout = QGridLayout(overview_widget)
        self.overview_layout.setSpacing(8)

        self.summary_chart = None

        self.status_widget = QWidget()
        self.status_layout = QVBoxLayout(self.status_widget)
        self.status_layout.setSpacing(4)

        self._rebuild_status_cards()

        self.overview_layout.addWidget(self.status_widget, 0, 1, 2, 1)
        self.overview_layout.setColumnStretch(0, 3)
        self.overview_layout.setColumnStretch(1, 1)

        self.tabs.addTab(overview_widget, "📊 Summary")

        self._rebuild_detail_tabs()
        layout.addWidget(self.tabs, 1)
        self.tabs.currentChanged.connect(self._on_tab_changed)

    def _get_module_chart_config(self, mod_key: str):
        if self.is_matrix_touch:
            rows, cols = REVO3_MATRIX_HEATMAP_LAYOUT[mod_key]
            idx = REVO3_MODULE_NAMES.index(mod_key)
            pts = self.matrix_point_counts[idx]
            return pts, rows, cols, None
        pts = REVO3_MODULE_POINTS[mod_key]
        rows, cols = REVO3_HEATMAP_LAYOUT[mod_key]
        return pts, rows, cols, _get_revo3_coord_map(mod_key)

    def _rebuild_status_cards(self):
        # 1. Clear status_layout widgets
        while self.status_layout.count() > 0:
            item = self.status_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        # 2. Rebuild summary_chart
        if self.summary_chart is not None:
            self.overview_layout.removeWidget(self.summary_chart)
            self.summary_chart.deleteLater()
            self.summary_chart = None

        # 3. Determine names & colors
        if self.is_matrix_touch:
            names = [item[1] for item in self.module_info]
            colors = [
                (100, 255, 255),  # Palm
                (255, 100, 100), (255, 100, 100),  # Thumb Tip, Pad
                (100, 255, 100), (100, 255, 100),  # Index Tip, Pad
                (100, 100, 255), (100, 100, 255),  # Middle Tip, Pad
                (255, 255, 100), (255, 255, 100),  # Ring Tip, Pad
                (255, 100, 255), (255, 100, 255),  # Pinky Tip, Pad
            ]
            # Calculate actual max single-point range across all modules (in mN)
            limits_mnd = []
            for idx in range(len(self.module_info)):
                pts_count = self.matrix_point_counts[idx] if idx < len(self.matrix_point_counts) else 60
                limit_raw = MATRIX_FORCE_LIMITS[idx] if idx < len(MATRIX_FORCE_LIMITS) else 300000
                limits_mnd.append(limit_raw / pts_count / 10.0)
            y_range = (0, int(max(limits_mnd)) if limits_mnd else 2000)
            y_label = "mN"
        else:
            names = REVO3_SUMMARY_NAMES
            colors = REVO3_SUMMARY_COLORS
            y_range = (0, int(PRESSURE_FORCE_LIMIT_MN))
            y_label = "mN"

        # 4. Rebuild chart and cards
        self.summary_chart = SummaryChart(
            "Touch Summary", y_range,
            sensor_names=names,
            sensor_colors=colors,
            y_label=y_label,
        )
        self.overview_layout.addWidget(self.summary_chart, 0, 0, 2, 1)

        self.sensor_cards, self.sensor_bars, self.sensor_labels = build_status_cards(
            self.status_layout, names, colors, is_compact=True
        )

    def _rebuild_detail_tabs(self):
        if not hasattr(self, "tabs"):
            return

        while self.tabs.count() > 1:
            widget = self.tabs.widget(1)
            self.tabs.removeTab(1)
            if widget is not None:
                widget.deleteLater()

        self.detail_charts = [None] * 11

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
                pts, rows, cols, coord_map = self._get_module_chart_config(mod_key)
                chart = HeatmapChart(name, pts, color, rows, cols, coord_map=coord_map)
                self.detail_charts[mod_idx] = chart

                if self.is_matrix_touch or self.touch_vendor == TouchVendor.Pressure:
                    container = QWidget()
                    lay = QHBoxLayout(container)
                    lay.setContentsMargins(4, 4, 4, 4)
                    lay.addWidget(chart, 1)
                    ctrl = self._create_module_ctrl_widget(mod_idx, name)
                    lay.addWidget(ctrl)
                    self.tabs.addTab(container, f"{icon} {group_name}")
                else:
                    self.tabs.addTab(chart, f"{icon} {group_name}")
            else:
                finger_widget = QWidget()
                finger_layout = QVBoxLayout(finger_widget)
                finger_layout.setContentsMargins(0, 0, 0, 0)
                finger_layout.setSpacing(4)

                for mod_idx, name, mod_key in modules:
                    color = REVO3_MODULE_COLORS[mod_idx]
                    pts, rows, cols, coord_map = self._get_module_chart_config(mod_key)
                    chart = HeatmapChart(name, pts, color, rows, cols, coord_map=coord_map)
                    self.detail_charts[mod_idx] = chart

                    if self.is_matrix_touch or self.touch_vendor == TouchVendor.Pressure:
                        container = QWidget()
                        lay = QHBoxLayout(container)
                        lay.setContentsMargins(0, 0, 0, 0)
                        lay.addWidget(chart, 1)
                        ctrl = self._create_module_ctrl_widget(mod_idx, name)
                        lay.addWidget(ctrl)
                        finger_layout.addWidget(container, 1)
                    else:
                        finger_layout.addWidget(chart, 1)

                self.tabs.addTab(finger_widget, f"{icon} {group_name}")

        if hasattr(self.tabs, "setTabVisible"):
            self.tabs.setTabVisible(0, True)

    def update_data(self, revo3_data):
        """Process Revo3 Touch data.

        revo3_data: object with .summary (list of 42) and .modules (list of 11 lists)
        """
        if not hasattr(revo3_data, 'summary') or not hasattr(revo3_data, 'modules'):
            return

        summary = revo3_data.summary
        modules = revo3_data.modules

        # Update summary. Matrix touch does not expose the 42-zone pressure summary,
        # so the overview uses per-module maxima in the first 11 channels.
        if self.is_matrix_touch and modules:
            summary_11 = [0.0] * 11
            for i, module_points in enumerate(modules[:11]):
                summary_11[i] = max(list(module_points or [0.0]))

            # Apply scaling factor for matrix touch in Force mode
            for i in range(len(summary_11)):
                is_force = (self.matrix_modes[i] == 1) if i < len(self.matrix_modes) else True
                if is_force:
                    summary_11[i] /= 10.0

            self.summary_chart.add_data(summary_11)
            for i, val in enumerate(summary_11):
                if i < len(self.sensor_bars):
                    is_force = (self.matrix_modes[i] == 1) if i < len(self.matrix_modes) else True
                    pts = list(modules[i] or []) if i < len(modules) else []
                    if is_force:
                        pts_scaled = [p / 10.0 for p in pts] # scale to mN
                        n_total = len(pts_scaled) if pts_scaled else 1
                        max_v = max(pts_scaled) if pts_scaled else 0
                        min_v = min(pts_scaled) if pts_scaled else 0
                        sum_v = sum(pts_scaled) if pts_scaled else 0
                        avg_v = sum_v / n_total if pts_scaled else 0
                        active_vals = [v for v in pts_scaled if v > 0]
                        a_avg = sum(active_vals) / len(active_vals) if active_vals else 0
                        cnt = len(active_vals)

                        pts_count = self.matrix_point_counts[i] if i < len(self.matrix_point_counts) else 60
                        # MATRIX_FORCE_LIMITS uses 0.0001N units, so divide by 10.0 to get mN.
                        sum_limit_mN = (MATRIX_FORCE_LIMITS[i] / 10.0) if i < len(MATRIX_FORCE_LIMITS) else 30000.0
                        avg_limit_mN = sum_limit_mN / pts_count

                        # Map ProgressBar to Average force (avg_v) within [0, avg_limit_mN]
                        self.sensor_bars[i].setRange(0, int(avg_limit_mN))
                        self.sensor_bars[i].setValue(min(int(avg_v), int(avg_limit_mN)))

                        # Unify units: mN for max & avg, N for sum
                        sum_val_N = sum_v / 1000.0
                        sum_limit_N = sum_limit_mN / 1000.0

                        sn_str = self.matrix_module_sns[i] if (self.is_matrix_touch and i < len(self.matrix_module_sns)) else ""
                        if not sn_str and self.is_matrix_touch:
                            sn_str = "—"
                        sn_line = f"\nSN: {sn_str}" if self.is_matrix_touch else ""
                        self.sensor_labels[i].setText(
                            f"max:{max_v:.0f} avg:{avg_v:.0f}/{avg_limit_mN:.0f} mN\n"
                            f"sum:{sum_val_N:.1f}/{sum_limit_N:.1f} N  cnt:{cnt}/{n_total}"
                            f"{sn_line}"
                        )
                    else:
                        n_total = len(pts) if pts else 1
                        max_v = max(pts) if pts else 0
                        min_v = min(pts) if pts else 0
                        sum_v = sum(pts) if pts else 0
                        avg_v = sum_v / n_total if pts else 0
                        active_vals = [v for v in pts if v > 0]
                        a_avg = sum(active_vals) / len(active_vals) if active_vals else 0
                        cnt = len(active_vals)

                        # In raw ADC mode, range is 0~255
                        self.sensor_bars[i].setRange(0, 255)
                        self.sensor_bars[i].setValue(min(int(avg_v), 255))

                        sn_str = self.matrix_module_sns[i] if (self.is_matrix_touch and i < len(self.matrix_module_sns)) else ""
                        if not sn_str and self.is_matrix_touch:
                            sn_str = "—"
                        sn_line = f"\nSN: {sn_str}" if self.is_matrix_touch else ""
                        self.sensor_labels[i].setText(
                            f"max:{int(max_v)} avg:{avg_v:.0f}/255\n"
                            f"sum:{int(sum_v)}  cnt:{cnt}/{n_total}"
                            f"{sn_line}"
                        )
        elif summary and len(summary) >= 42:
            summary_42 = list(summary[:42])
            self.summary_chart.add_data(summary_42)
            is_force = (self.type_combo.currentIndex() == 1)
            limit_val = PRESSURE_FORCE_LIMIT_MN if is_force else 4096.0
            for i, val in enumerate(summary_42):
                if i < len(self.sensor_bars):
                    self.sensor_bars[i].setRange(0, int(limit_val))
                    self.sensor_bars[i].setValue(min(int(val), int(limit_val)))
                    if is_force:
                        self.sensor_labels[i].setText(
                            f"{float(val):.0f}/{limit_val:.0f} mN\n"
                            f"{float(val) / 1000.0:.1f}/{limit_val / 1000.0:.1f} N"
                        )
                    else:
                        self.sensor_labels[i].setText(
                            f"{float(val):.0f}/{limit_val:.0f} ADC"
                        )

        # Update detail
        if modules:
            for i, module_points in enumerate(modules):
                if i < len(self.detail_charts) and self.detail_charts[i] is not None:
                    is_enabled = True
                    if i < len(self.module_checks):
                        is_enabled = self.module_checks[i].isChecked()

                    points = module_points or []
                    limit = 255.0 if self.is_matrix_touch else 4096.0
                    value_unit = "adc"
                    stats_limit = None
                    if self.is_matrix_touch:
                        is_force = (self.matrix_modes[i] == 1) if i < len(self.matrix_modes) else True
                        if is_force:
                            pts_count = self.matrix_point_counts[i] if i < len(self.matrix_point_counts) else 60
                            points = [p / 10.0 for p in points]
                            limit = (MATRIX_FORCE_LIMITS[i] / pts_count / 10.0) if i < len(MATRIX_FORCE_LIMITS) else (30000.0 / pts_count)
                            value_unit = "force"
                            stats_limit = limit
                        else:
                            stats_limit = 255.0
                    elif self.type_combo.currentIndex() == 1:
                        limit = PRESSURE_FORCE_LIMIT_MN
                        value_unit = "force"
                        stats_limit = None

                    self.detail_charts[i].add_data(
                        points,
                        is_enabled=is_enabled,
                        max_limit=limit,
                        value_unit=value_unit,
                        stats_max_limit=stats_limit,
                    )

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
        self.read_btn.setText(
            tr("btn_read_touch_settings")
            if tr("btn_read_touch_settings") != "btn_read_touch_settings"
            else "Read Enable State"
        )
        self.read_sn_btn.setText(
            tr("btn_read_matrix_module_sns")
            if tr("btn_read_matrix_module_sns") != "btn_read_matrix_module_sns"
            else "Read SN"
        )
        self.read_points_btn.setText(
            tr("btn_read_matrix_point_counts")
            if tr("btn_read_matrix_point_counts") != "btn_read_matrix_point_counts"
            else "Read Points"
        )
        self.read_output_mode_btn.setText(
            tr("btn_read_matrix_output_mode")
            if tr("btn_read_matrix_output_mode") != "btn_read_matrix_output_mode"
            else "Read Module Value Type"
        )
        self.read_tare_status_btn.setText(
            tr("btn_read_matrix_tare_status")
            if tr("btn_read_matrix_tare_status") != "btn_read_matrix_tare_status"
            else "Read Tare State"
        )
        self._update_zero_button_texts()
        self.zero_cancel_btn.setText(
            tr("btn_touch_zero_cancel")
            if tr("btn_touch_zero_cancel") != "btn_touch_zero_cancel"
            else "Zero Cancel"
        )
        self.pressure_force_clear_btn.setText(
            tr("btn_pressure_force_clear")
            if tr("btn_pressure_force_clear") != "btn_pressure_force_clear"
            else "Regional Force Zero"
        )
        self.pressure_force_restore_btn.setText(
            tr("btn_pressure_force_restore")
            if tr("btn_pressure_force_restore") != "btn_pressure_force_restore"
            else "Restore Regional Force"
        )
        self.tabs.tabBar().updateGeometry()
        self.tabs.tabBar().update()

    def _update_zero_button_texts(self):
        if self.touch_vendor == 1 and not self.is_matrix_touch:
            self.zero_calibrate_btn.setText(
                tr("btn_pressure_zero")
                if tr("btn_pressure_zero") != "btn_pressure_zero"
                else "Pressure Zero"
            )
            return
        self.zero_calibrate_btn.setText(
            tr("btn_touch_zero_calibrate")
            if tr("btn_touch_zero_calibrate") != "btn_touch_zero_calibrate"
            else "Zero Calibration"
        )

    def _on_tab_changed(self, index):
        if not self.device:
            return
        if self.is_matrix_touch:
            run_async(self._refresh_active_tab_matrix_modes)
            return
        # index: 0 = Summary (ForceSummary = 1), >0 = Finger detail (TactileArray = 0)
        target_type = 1 if index == 0 else 0
        if self.type_combo.currentIndex() != target_type:
            mode_str = "Force Summary" if target_type == 1 else "Tactile Array"
            tab_name = self.tabs.tabText(index)
            logger.info(
                f"Tab changed to {index} ({tab_name}). "
                f"Automatically switching touch data type to {target_type} ({mode_str})"
            )
            self.type_combo.setCurrentIndex(target_type)

    def _on_type_changed(self, index):
        if not self.device:
            return
        if self.is_matrix_touch:
            return
        # index: 0 = Tactile Array, 1 = Force Summary
        val = int(index)
        mode_str = "Force Summary" if val == 1 else "Tactile Array"
        logger.info(f"Setting touch data type to {val} ({mode_str})")
        try:
            from common_imports import sdk
            if sdk is not None and hasattr(sdk, "TouchDataMode"):
                mode = sdk.TouchDataMode(val)
            else:
                mode = val
            run_async(lambda: self.device.revo3_set_touch_data_type(self.slave_id, mode))
            self._refresh_detail_chart_units()
            if val == 1 and self.tabs.currentIndex() != 0:
                self.tabs.setCurrentIndex(0)
        except Exception as e:
            logger.error(f"Failed to set touch data type: {e}")

    def _refresh_detail_chart_units(self):
        if self.is_matrix_touch:
            for i, chart in enumerate(self.detail_charts):
                if chart is None:
                    continue
                is_force = (self.matrix_modes[i] == 1) if i < len(self.matrix_modes) else True
                if is_force:
                    pts_count = self.matrix_point_counts[i] if i < len(self.matrix_point_counts) else 60
                    limit = (MATRIX_FORCE_LIMITS[i] / pts_count / 10.0) if i < len(MATRIX_FORCE_LIMITS) else (30000.0 / pts_count)
                    chart.set_value_unit("force", limit, stats_max_limit=limit)
                else:
                    chart.set_value_unit("adc", 255.0, stats_max_limit=255.0)
            return

        if self.type_combo.currentIndex() == 1:
            for chart in self.detail_charts:
                if chart is not None:
                    chart.set_value_unit(
                        "force",
                        PRESSURE_FORCE_LIMIT_MN,
                        stats_max_limit=None,
                    )
        else:
            for chart in self.detail_charts:
                if chart is not None:
                    chart.set_value_unit("adc", 4096.0)

    def _read_data_type(self):
        if not self.device:
            return
        if self.is_matrix_touch:
            return
        async def fetch():
            try:
                val = await self.device.revo3_get_touch_data_type(self.slave_id)
                val_int = int(val)
                mode_str = "Force Summary" if val_int == 1 else "Tactile Array"
                logger.info(f"Fetched touch data type: {val_int} ({mode_str})")
                # block signals temporarily to avoid triggering currentIndexChanged
                self.type_combo.blockSignals(True)
                self.type_combo.setCurrentIndex(1 if val_int == 1 else 0)
                self.type_combo.blockSignals(False)
                self._refresh_detail_chart_units()
            except Exception as e:
                logger.error(f"Failed to read touch data type: {e}")
        run_async(fetch)

    def _zero_calibrate(self):
        if not self.device:
            return
        logger.info("Calibrating touch sensor zero drift...")
        try:
            if self.touch_vendor == TouchVendor.Pressure and hasattr(self.device, "revo3_calibrate_pressure_touch_zero"):
                run_async(lambda: self.device.revo3_calibrate_pressure_touch_zero(self.slave_id))
            else:
                run_async(lambda: self.device.revo3_calibrate_touch_zero(self.slave_id))
        except Exception as e:
            logger.error(f"Failed to calibrate touch zero drift: {e}")

    def _zero_cancel(self):
        if not self.device:
            return
        if not self.is_matrix_touch:
            logger.info("Pressure touch does not support zero cancel; ignoring request.")
            return
        logger.info("Canceling global touch sensor zero drift...")
        try:
            run_async(lambda: self.device.revo3_set_matrix_touch_tare(self.slave_id, matrix_touch_tare_command(2)))
        except Exception as e:
            logger.error(f"Failed to cancel global touch zero drift: {e}")

    def _confirm_pressure_restore(self, module_id=None):
        title = (
            tr("dialog_pressure_force_restore_title")
            if tr("dialog_pressure_force_restore_title") != "dialog_pressure_force_restore_title"
            else "Confirm Regional Force Restore"
        )
        if module_id is None:
            message_key = "dialog_pressure_force_restore_all_message"
            fallback = "Restore regional force factory settings for all Pressure Touch modules?"
        else:
            message_key = "dialog_pressure_force_restore_module_message"
            fallback = f"Restore regional force factory settings for Pressure Touch module {module_id}?"
        message = tr(message_key) if tr(message_key) != message_key else fallback
        if "{module_id}" in message:
            message = message.format(module_id=module_id)
        return (
            QMessageBox.question(
                self,
                title,
                message,
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            == QMessageBox.Yes
        )

    def _pressure_force_clear(self):
        if not self.device or self.is_matrix_touch:
            return
        logger.info("Clearing global Pressure touch regional force tare...")
        try:
            run_async(lambda: self.device.revo3_set_pressure_touch_force_tare(
                self.slave_id,
                pressure_touch_force_tare_command(2),
            ))
        except Exception as e:
            logger.error(f"Failed to clear Pressure touch regional force tare: {e}")

    def _pressure_force_restore(self):
        if not self.device or self.is_matrix_touch:
            return
        if not self._confirm_pressure_restore():
            return
        logger.warning("Restoring global Pressure touch regional force tare factory settings...")
        try:
            run_async(lambda: self.device.revo3_set_pressure_touch_force_tare(
                self.slave_id,
                pressure_touch_force_tare_command(3),
            ))
        except Exception as e:
            logger.error(f"Failed to restore Pressure touch regional force tare: {e}")

    def _update_zero_buttons(self, enabled: bool):
        self.zero_calibrate_btn.setEnabled(enabled)
        self.zero_cancel_btn.setEnabled(enabled and self.is_matrix_touch)
        self.zero_cancel_btn.setVisible(self.is_matrix_touch)
        is_pressure_touch = self.touch_vendor == TouchVendor.Pressure and not self.is_matrix_touch
        self.pressure_force_clear_btn.setEnabled(enabled and is_pressure_touch)
        self.pressure_force_clear_btn.setVisible(is_pressure_touch)
        self.pressure_force_restore_btn.setEnabled(enabled and is_pressure_touch)
        self.pressure_force_restore_btn.setVisible(is_pressure_touch)

    def _update_matrix_read_buttons(self, enabled: bool):
        is_matrix = bool(enabled and self.device and self.is_matrix_touch)
        button_specs = [
            (self.read_sn_btn, "revo3_get_all_matrix_touch_module_serial_numbers"),
            (self.read_points_btn, "revo3_get_all_matrix_touch_module_point_counts"),
            (self.read_output_mode_btn, "revo3_get_matrix_touch_output_mode"),
            (
                self.read_tare_status_btn,
                "revo3_get_all_matrix_touch_module_tare_statuses",
                "revo3_get_matrix_touch_tare_status",
            ),
        ]
        for spec in button_specs:
            btn = spec[0]
            api_names = spec[1:]
            supported = is_matrix and any(hasattr(self.device, api_name) for api_name in api_names)
            btn.setEnabled(supported)
            btn.setVisible(supported)

    def _create_module_ctrl_widget(self, mod_idx, mod_name):
        from PySide6.QtWidgets import QFrame, QLabel, QComboBox, QPushButton
        frame = QFrame()
        frame.setFixedWidth(180)
        frame.setStyleSheet("""
            QFrame {
                border: 1px solid #444444;
                border-radius: 4px;
                background-color: #262626;
                padding: 4px;
            }
            QLabel {
                font-size: 11px;
                color: #CCCCCC;
                border: none;
            }
            QPushButton {
                font-size: 10px;
                font-weight: bold;
                padding: 4px 6px;
                background-color: #333333;
                color: #FFFFFF;
                border: 1px solid #555555;
            }
            QPushButton:hover {
                background-color: #444444;
            }
            QComboBox {
                font-size: 10px;
                background-color: #333333;
                color: #FFFFFF;
                border: 1px solid #555555;
            }
        """)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(6)

        title = QLabel(f"<b>{mod_name} Control</b>")
        title.setStyleSheet("color: #00FF66;")
        layout.addWidget(title)

        if not self.is_matrix_touch:
            pressure_zero_btn = QPushButton(
                tr("btn_pressure_zero")
                if tr("btn_pressure_zero") != "btn_pressure_zero"
                else "Pressure Zero"
            )
            pressure_zero_btn.clicked.connect(lambda: self._on_pressure_module_zero(mod_idx))
            layout.addWidget(pressure_zero_btn)

            pressure_force_clear_btn = QPushButton(
                tr("btn_pressure_force_clear")
                if tr("btn_pressure_force_clear") != "btn_pressure_force_clear"
                else "Regional Force Zero"
            )
            pressure_force_clear_btn.clicked.connect(lambda: self._on_pressure_module_force_clear(mod_idx))
            layout.addWidget(pressure_force_clear_btn)

            pressure_force_restore_btn = QPushButton(
                tr("btn_pressure_force_restore")
                if tr("btn_pressure_force_restore") != "btn_pressure_force_restore"
                else "Restore Regional Force"
            )
            pressure_force_restore_btn.clicked.connect(lambda: self._on_pressure_module_force_restore(mod_idx))
            layout.addWidget(pressure_force_restore_btn)

            layout.addStretch()
            return frame

        # Status Label
        status_label = QLabel("Zero Status: --")
        status_label.setObjectName(f"status_{mod_idx}")
        layout.addWidget(status_label)

        # Buttons layout
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(4)
        tare_btn = QPushButton("Tare")
        tare_btn.clicked.connect(lambda: self._on_module_tare(mod_idx))
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(lambda: self._on_module_tare_cancel(mod_idx))
        btn_layout.addWidget(tare_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)

        # Matrix module value type: ADC value or force.
        mode_label = QLabel("Value Type:")
        layout.addWidget(mode_label)
        mode_combo = QComboBox()
        mode_combo.addItems(["ADC Value", "Force"])
        mode_combo.currentIndexChanged.connect(lambda idx, mid=mod_idx: self._on_module_mode_change(mid, idx))
        mode_combo.setObjectName(f"mode_{mod_idx}")
        layout.addWidget(mode_combo)

        layout.addStretch()
        return frame

    def _on_module_tare(self, mod_idx):
        if not self.device:
            return
        logger.info(f"Triggering single module {mod_idx} zero tare")
        run_async(lambda: self.device.revo3_calibrate_touch_zero_single(self.slave_id, mod_idx))

    def _on_module_tare_cancel(self, mod_idx):
        if not self.device:
            return
        logger.info(f"Canceling single module {mod_idx} zero tare")
        run_async(lambda: self.device.revo3_set_matrix_touch_module_tare(self.slave_id, mod_idx, matrix_touch_tare_command(2)))

    def _on_pressure_module_zero(self, mod_idx):
        if not self.device or self.is_matrix_touch:
            return
        logger.info(f"Calibrating Pressure touch module {mod_idx} pressure zero")
        run_async(lambda: self.device.revo3_calibrate_pressure_touch_module_zero(self.slave_id, mod_idx))

    def _on_pressure_module_force_clear(self, mod_idx):
        if not self.device or self.is_matrix_touch:
            return
        logger.info(f"Clearing Pressure touch module {mod_idx} regional force tare")
        run_async(lambda: self.device.revo3_set_pressure_touch_module_force_tare(
            self.slave_id,
            mod_idx,
            pressure_touch_force_tare_command(2),
        ))

    def _on_pressure_module_force_restore(self, mod_idx):
        if not self.device or self.is_matrix_touch:
            return
        if not self._confirm_pressure_restore(module_id=mod_idx):
            return
        logger.warning(f"Restoring Pressure touch module {mod_idx} regional force tare factory settings")
        run_async(lambda: self.device.revo3_set_pressure_touch_module_force_tare(
            self.slave_id,
            mod_idx,
            pressure_touch_force_tare_command(3),
        ))

    def _on_module_mode_change(self, mod_idx, mode_idx):
        if not self.device:
            return
        logger.info(f"Setting module {mod_idx} mode to: {mode_idx} (0=ADC [0~255], 1=Force [mN])")
        if mod_idx < len(self.matrix_modes):
            self.matrix_modes[mod_idx] = mode_idx
        self._refresh_detail_chart_units()
        run_async(lambda: self.device.revo3_set_matrix_touch_module_output_mode(self.slave_id, mod_idx, matrix_touch_output_mode(mode_idx)))

    async def _refresh_active_tab_matrix_modes(self):
        if not self.device or not self.is_matrix_touch:
            return
        # Get active modules from current tab index
        tab_idx = self.tabs.currentIndex()
        # 0 = Summary, 1 = Palm(0), 2 = Thumb(1,2), 3 = Index(3,4), 4 = Middle(5,6), 5 = Ring(7,8), 6 = Pinky(9,10)
        active_mids = []
        if tab_idx == 1:
            active_mids = [0]
        elif tab_idx >= 2 and tab_idx <= 6:
            base = (tab_idx - 2) * 2 + 1
            active_mids = [base, base + 1]

        for mid in active_mids:
            try:
                if hasattr(self.device, "revo3_get_matrix_touch_module_output_mode"):
                    mode = await self.device.revo3_get_matrix_touch_module_output_mode(self.slave_id, mid)
                    if mid < len(self.matrix_modes):
                        self.matrix_modes[mid] = int(mode)
                    combo = self.findChild(QComboBox, f"mode_{mid}")
                    if combo:
                        combo.blockSignals(True)
                        combo.setCurrentIndex(1 if int(mode) == 1 else 0)
                        combo.blockSignals(False)
            except Exception as e:
                logger.error(f"Failed to fetch module {mid} output mode: {e}")

    def _read_modules_enabled(self):
        if not self.device:
            return
        async def fetch():
            try:
                # Fetch enabled mask
                bits = await self.device.revo3_get_all_touch_modules_enabled(self.slave_id)
                logger.info(f"Fetched touch modules enabled bitmask: {bin(bits)}")
                # Update checkboxes without triggering signals
                for cb, item in zip(self.module_checks, self.module_info):
                    mod_id = item[0]
                    is_on = bool((bits >> mod_id) & 1)
                    cb.blockSignals(True)
                    cb.setChecked(is_on)
                    cb.blockSignals(False)
            except Exception as e:
                logger.error(f"Failed to read touch modules enabled status: {e}")
        run_async(fetch)

    def _on_module_toggle(self, module_id, enabled):
        if not self.device:
            return
        logger.info(f"Toggling touch module {module_id} -> {enabled}")
        try:
            run_async(lambda: self.device.revo3_set_touch_module_enabled(self.slave_id, module_id, enabled))
        except Exception as e:
            logger.error(f"Failed to set touch module {module_id} enabled: {e}")
            # Re-read to sync back on error
            self._read_modules_enabled()

    def _read_all_settings(self):
        if not self.is_matrix_touch:
            self._read_data_type()
        self._read_modules_enabled()

    def _read_touch_vendor(self):
        if not self.device:
            return

        async def fetch():
            try:
                vendor = TouchVendor.Pressure
                if hasattr(self.device, "get_touch_vendor"):
                    vendor = await self.device.get_touch_vendor(self.slave_id)
                vendor_int = int(vendor)
                self.touch_vendor = vendor_int
                self.is_matrix_touch = vendor_int == TouchVendor.Matrix
                logger.info(f"Touch vendor: {vendor_int} (0=Unknown, 1=Pressure, 2=Matrix)")

                self.type_combo.blockSignals(True)
                self.type_combo.setCurrentIndex(0 if self.is_matrix_touch else 1)
                self.type_combo.setEnabled(not self.is_matrix_touch)
                self.type_combo.blockSignals(False)
                if not self.is_matrix_touch:
                    self.tabs.setCurrentIndex(0)
                self._update_zero_button_texts()
                self.zero_cancel_btn.setText(
                    tr("btn_touch_zero_cancel")
                    if tr("btn_touch_zero_cancel") != "btn_touch_zero_cancel"
                    else "Zero Cancel"
                )
                self._update_zero_buttons(True)
                self._update_matrix_read_buttons(True)
                self._rebuild_status_cards()
                self._rebuild_detail_tabs()
                await self._fetch_all_settings()
                self.update_texts()
            except Exception as e:
                logger.error(f"Failed to read touch vendor: {e}")

        run_async(fetch)

    def _read_matrix_settings(self):
        if not self.device or not self.is_matrix_touch:
            return

        async def fetch():
            await self._fetch_matrix_settings()

        run_async(fetch)

    def _read_matrix_module_sns(self):
        if not self.device or not self.is_matrix_touch:
            return

        async def fetch():
            await self._fetch_matrix_module_sns()

        run_async(fetch)

    def _read_matrix_point_counts(self):
        if not self.device or not self.is_matrix_touch:
            return

        async def fetch():
            await self._fetch_matrix_point_counts(rebuild_tabs=True)

        run_async(fetch)

    def _read_matrix_output_mode(self):
        if not self.device or not self.is_matrix_touch:
            return

        async def fetch():
            await self._fetch_matrix_output_mode()

        run_async(fetch)

    def _read_matrix_tare_status(self):
        if not self.device or not self.is_matrix_touch:
            return

        async def fetch():
            await self._fetch_matrix_tare_statuses()

        run_async(fetch)

    async def _fetch_all_settings(self):
        if not self.is_matrix_touch:
            try:
                # 默认强行切换到合力 (Force Summary) 数据类型
                logger.info("Pressure touch mode: forcing data type to 1 (Force Summary)")
                try:
                    from common_imports import sdk
                    if sdk is not None and hasattr(sdk, "TouchDataMode"):
                        mode = sdk.TouchDataMode(1)
                    else:
                        mode = 1
                    await self.device.revo3_set_touch_data_type(self.slave_id, mode)
                except Exception as ex:
                    logger.error(f"Failed to auto-set touch data type to Force Summary: {ex}")

                self.type_combo.blockSignals(True)
                self.type_combo.setCurrentIndex(1)
                self.type_combo.blockSignals(False)
                self._refresh_detail_chart_units()
                if self.tabs.currentIndex() != 0:
                    self.tabs.setCurrentIndex(0)
            except Exception as e:
                logger.error(f"Failed to setup pressure touch data type: {e}")

        try:
            bits = await self.device.revo3_get_all_touch_modules_enabled(self.slave_id)
            logger.info(f"Fetched touch modules enabled bitmask: {bin(bits)}")
            for cb, item in zip(self.module_checks, self.module_info):
                mod_id = item[0]
                is_on = bool((bits >> mod_id) & 1)
                cb.blockSignals(True)
                cb.setChecked(is_on)
                cb.blockSignals(False)
        except Exception as e:
            logger.error(f"Failed to read touch modules enabled status: {e}")

    async def _fetch_matrix_module_sns(self):
        try:
            if hasattr(self.device, "revo3_get_all_matrix_touch_module_serial_numbers"):
                raw_sns = await self.device.revo3_get_all_matrix_touch_module_serial_numbers(self.slave_id)
                self.matrix_module_sns = [sn if sn else "" for sn in raw_sns]
                logger.info(f"Matrix touch module SNs: {self.matrix_module_sns}")
        except Exception as e:
            logger.error(f"Failed to read Matrix touch module SNs: {e}")

    async def _fetch_matrix_point_counts(self, rebuild_tabs=False):
        try:
            raw_counts = []
            if hasattr(self.device, "revo3_get_all_matrix_touch_module_point_counts"):
                raw_counts = await self.device.revo3_get_all_matrix_touch_module_point_counts(self.slave_id)
                default_counts = [53, 56, 22, 22, 27, 22, 27, 22, 27, 22, 27]
                self.matrix_point_counts = [
                    raw_counts[idx] if idx < len(raw_counts) and raw_counts[idx] > 0
                    else (default_counts[idx] if idx < len(default_counts) else 22)
                    for idx in range(11)
                ]
                logger.info(f"Matrix touch point counts: {self.matrix_point_counts}")
                if rebuild_tabs:
                    self._rebuild_status_cards()
                    self._rebuild_detail_tabs()
                    self._refresh_detail_chart_units()
            return raw_counts
        except Exception as e:
            logger.error(f"Failed to read Matrix touch point counts: {e}")
            return []

    async def _fetch_matrix_output_mode(self):
        try:
            if hasattr(self.device, "revo3_get_matrix_touch_output_mode"):
                mode = await self.device.revo3_get_matrix_touch_output_mode(self.slave_id)
                logger.info(f"Matrix touch output mode: {int(mode)} (0=ADC [0~255], 1=force [mN])")
                self.matrix_modes = [int(mode)] * 11
                self._refresh_detail_chart_units()
                await self._refresh_active_tab_matrix_modes()
        except Exception as e:
            logger.error(f"Failed to read Matrix touch output mode: {e}")

    async def _fetch_matrix_tare_statuses(self):
        try:
            if hasattr(self.device, "revo3_get_matrix_touch_tare_status"):
                status = await self.device.revo3_get_matrix_touch_tare_status(self.slave_id)
                logger.info(f"Matrix touch zero status: {int(status)}")

            # Read all 11 modules' tare statuses in one Modbus pass
            if hasattr(self.device, "revo3_get_all_matrix_touch_module_tare_statuses"):
                statuses = await self.device.revo3_get_all_matrix_touch_module_tare_statuses(self.slave_id)
                for mod_idx, status_val in enumerate(statuses):
                    lbl = self.findChild(QLabel, f"status_{mod_idx}")
                    if lbl:
                        st_str = "NotTared"
                        color = "#888888"
                        if int(status_val) == 1:
                            st_str = "Tared"
                            color = "#00FF66"
                        elif int(status_val) == 2:
                            st_str = "Busy/Failed"
                            color = "#FF3333"
                        lbl.setText(f"Zero Status: <span style='color:{color}; font-weight:bold;'>{st_str}</span>")
        except Exception as e:
            logger.error(f"Failed to read Matrix touch tare status: {e}")

    async def _fetch_matrix_settings(self):
        try:
            await self._fetch_matrix_module_sns()
            raw_counts = await self._fetch_matrix_point_counts()
            await self._fetch_matrix_output_mode()
            await self._fetch_matrix_tare_statuses()

            has_empty_sn = any(not sn for sn in self.matrix_module_sns) if self.matrix_module_sns else True
            has_zero_count = any(c <= 0 for c in raw_counts) if raw_counts else True

            if has_empty_sn or has_zero_count:
                logger.info("Touch settings not fully initialized by firmware yet. Retrying in 3 seconds...")
                from PySide6.QtCore import QTimer
                QTimer.singleShot(3000, lambda: run_async(self._fetch_matrix_settings))

            # Refresh active tab modes to keep UI dropdowns in sync immediately
            await self._refresh_active_tab_matrix_modes()
        except Exception as e:
            logger.error(f"Failed to read Matrix touch settings: {e}")

    def set_device(self, device, slave_id, device_info=None, shared_data=None):
        self.device = device
        self.slave_id = slave_id
        self.matrix_modes = [1] * 11
        self.is_matrix_touch = False
        # Enable controls
        self.type_combo.setEnabled(True)
        self.read_btn.setEnabled(True)
        self._update_matrix_read_buttons(False)
        self._update_zero_buttons(True)
        for cb in self.module_checks:
            cb.setEnabled(True)
        self._read_touch_vendor()

    def clear_device(self):
        self.device = None
        self.touch_vendor = TouchVendor.Pressure
        self.is_matrix_touch = False
        self.type_combo.setEnabled(False)
        self.read_btn.setEnabled(False)
        self._update_matrix_read_buttons(False)
        self._update_zero_buttons(False)
        for cb in self.module_checks:
            cb.setEnabled(False)
            cb.setChecked(False)
        self._update_zero_button_texts()
        self.zero_cancel_btn.setText(
            tr("btn_touch_zero_cancel")
            if tr("btn_touch_zero_cancel") != "btn_touch_zero_cancel"
            else "Zero Cancel"
        )
        self._rebuild_status_cards()
        self._rebuild_detail_tabs()
