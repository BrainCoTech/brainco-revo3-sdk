"""Revo3 Touch Panel - For Revo3 Tactile Array devices

Displays Revo3 tactile array data:
- Summary: 42 regional force values or mx_* module aggregates
- Detail: 11 tactile array modules as heatmaps

Tabs:
- Summary: 16-line curves + status cards
- Per-finger heatmap tabs (Palm, Thumb, Index, Middle, Ring, Pinky)
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QTabWidget, QGroupBox, QCheckBox,
    QFrame, QLabel, QComboBox, QPushButton, QMessageBox, QScrollArea
)

from .touch_common import (
    HP_FORCE_DISPLAY_BASELINE_MN, SummaryChart, HeatmapChart,
    HpForceTorqueModuleCard, build_status_cards, run_async, logger
)
from .i18n import tr
from .sdk_adapter import (
    TOUCH_VALUE_MODE_ADC,
    TOUCH_VALUE_MODE_FORCE,
    map_touch_metadata_by_public_module_id,
    touch_value_mode_options,
)
from .styles import is_dark_mode

import sys
import time
import math
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))


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

# mt_* force display ceiling pending a confirmed physical measurement range.
MT_FORCE_LIMIT_MN = 20000.0
MT_ADC_MAX = 4096.0

# The SDK exposes force-mode points in mN. These raw limits are converted with
# raw * 10 mN. Unknown hand sides use the larger limit to avoid display clipping.
MX_FORCE_LIMITS_RAW_LEFT = [
    249, 63, 141, 236, 141, 236, 141, 236, 141, 236, 141,
]
MX_FORCE_LIMITS_RAW_RIGHT = [
    226, 63, 113, 236, 141, 236, 141, 236, 141, 236, 141,
]
MX_FORCE_LIMITS_RAW = [
    max(left, right)
    for left, right in zip(MX_FORCE_LIMITS_RAW_LEFT, MX_FORCE_LIMITS_RAW_RIGHT)
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


def _mx_channel_grid(point_count: int):
    """Build a compact channel grid from the module-reported point count."""
    point_count = max(1, int(point_count))
    cols = math.isqrt(point_count)
    while cols > 1 and point_count % cols != 0:
        cols -= 1
    rows = point_count // cols
    if point_count > 4 and (cols == 1 or rows > cols * 2):
        cols = math.isqrt(point_count)
        rows = math.ceil(point_count / cols)
    return rows, cols


try:
    from bc_revo3_sdk import main_mod as sdk
except ImportError:
    sdk = None


class Revo3TouchSubPanel(QWidget):
    touch_layout_updated = Signal(object)

    """Revo3 Touch Panel for Revo3 Tactile Array devices.

    Tabs:
    - Summary: 16-line curves + status cards
    - Per-finger: Heatmap tabs (Palm, Thumb, Index, Middle, Ring, Pinky)
    """

    def __init__(self):
        super().__init__()
        self.device = None
        self.slave_id = 1
        self.mx_modes = [TOUCH_VALUE_MODE_ADC] * 11
        self.detail_charts = [None] * 11
        self.hp_force_torque_cards = []
        self.sensor_cards = []
        self.sensor_bars = []
        self.sensor_labels = []
        self.module_checks = []
        self.summary_chart = None
        self.layout_label = None
        self.layout_combo = None
        self.read_mode_label = None
        self.read_mode_combo = None
        self.value_mode_label = None
        self.value_mode_combo = None
        self.read_btn = None
        self.zero_calibrate_btn = None
        self.zero_cancel_btn = None
        self.read_sn_btn = None
        self.read_points_btn = None
        self.read_output_mode_btn = None
        self.read_tare_status_btn = None
        self.restart_btn = None
        self.has_hp_touch = False
        self.is_hybrid = False
        self.has_mx_touch = False
        self.has_mt_touch = False
        self._active_touch_layout = None
        self._detected_touch_layout = None
        self._touch_layout_override_supported = False
        self._global_value_mode = TOUCH_VALUE_MODE_ADC
        self._hand_side = None
        self._last_touch_fps = 0.0
        self._last_log_time = 0.0
        self._mx_frame_counts_synced = False
        self.mx_point_counts = [0] * 11
        self.mx_module_sns = []
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

        # --- Touch Control Bar ---
        from PySide6.QtWidgets import QHBoxLayout, QLabel, QComboBox, QPushButton
        ctrl_layout = QHBoxLayout()
        ctrl_layout.setContentsMargins(8, 4, 8, 4)
        ctrl_layout.setSpacing(8)

        self.layout_label = QLabel("Touch Layout:")
        ctrl_layout.addWidget(self.layout_label)

        self.layout_combo = QComboBox()
        self.layout_combo.addItems([
            "Auto",
            "Hybrid HP+MT",
            "Hybrid HP+MX",
            "Pure HP",
            "Pure MT",
            "Pure MX",
        ])
        self.layout_combo.currentIndexChanged.connect(self._on_layout_changed)
        self.layout_combo.setEnabled(False)
        ctrl_layout.addWidget(self.layout_combo)

        self.read_mode_label = QLabel("Touch Read Mode:")
        ctrl_layout.addWidget(self.read_mode_label)

        self.read_mode_combo = QComboBox()
        self.read_mode_combo.addItems(
            ["Point Array", "Legacy Secondary-Calibrated Force Summary"]
        )
        self.read_mode_combo.currentIndexChanged.connect(self._on_read_mode_changed)
        self.read_mode_combo.setEnabled(False)
        ctrl_layout.addWidget(self.read_mode_combo)

        self.value_mode_label = QLabel("Touch Value Mode:")
        ctrl_layout.addWidget(self.value_mode_label)

        self.value_mode_combo = QComboBox()
        self._populate_value_mode_combo(self.value_mode_combo, False, False)
        self.value_mode_combo.currentIndexChanged.connect(self._on_global_value_mode_changed)
        self.value_mode_combo.setEnabled(False)
        ctrl_layout.addWidget(self.value_mode_combo)

        self.read_btn = QPushButton("Read Enable State")
        self.read_btn.clicked.connect(self._read_all_settings)
        self.read_btn.setEnabled(False)
        ctrl_layout.addWidget(self.read_btn)

        self.snapshot_btn = QPushButton("Read Snapshot")
        self.snapshot_btn.clicked.connect(self._read_touch_snapshot)
        self.snapshot_btn.setEnabled(False)
        ctrl_layout.addWidget(self.snapshot_btn)

        self.enable_all_btn = QPushButton("Enable All")
        self.enable_all_btn.clicked.connect(lambda: self._set_all_modules_enabled(True))
        self.enable_all_btn.setEnabled(False)
        ctrl_layout.addWidget(self.enable_all_btn)

        self.disable_all_btn = QPushButton("Disable All")
        self.disable_all_btn.clicked.connect(lambda: self._set_all_modules_enabled(False))
        self.disable_all_btn.setEnabled(False)
        ctrl_layout.addWidget(self.disable_all_btn)

        self.read_sn_btn = QPushButton("Read SN")
        self.read_sn_btn.clicked.connect(self._read_mx_module_sns)
        self.read_sn_btn.setEnabled(False)
        self.read_sn_btn.setVisible(False)
        ctrl_layout.addWidget(self.read_sn_btn)

        self.read_points_btn = QPushButton("Read Points")
        self.read_points_btn.clicked.connect(self._read_mx_point_counts)
        self.read_points_btn.setEnabled(False)
        self.read_points_btn.setVisible(False)
        ctrl_layout.addWidget(self.read_points_btn)

        self.read_output_mode_btn = QPushButton("Read Module Value Mode")
        self.read_output_mode_btn.clicked.connect(self._read_mx_output_mode)
        self.read_output_mode_btn.setEnabled(False)
        self.read_output_mode_btn.setVisible(False)
        ctrl_layout.addWidget(self.read_output_mode_btn)

        self.read_tare_status_btn = QPushButton("Read Tare State")
        self.read_tare_status_btn.clicked.connect(self._read_mx_tare_status)
        self.read_tare_status_btn.setEnabled(False)
        self.read_tare_status_btn.setVisible(False)
        ctrl_layout.addWidget(self.read_tare_status_btn)

        self.restart_btn = QPushButton("Restart Touch")
        self.restart_btn.clicked.connect(self._restart_touch)
        self.restart_btn.setEnabled(False)
        self.restart_btn.setVisible(False)
        ctrl_layout.addWidget(self.restart_btn)

        # Touch zero drift calibration button
        self.zero_calibrate_btn = QPushButton("Tare")
        self.zero_calibrate_btn.clicked.connect(self._zero_calibrate)
        self.zero_calibrate_btn.setEnabled(False)
        ctrl_layout.addWidget(self.zero_calibrate_btn)

        # Touch zero cancel button
        self.zero_cancel_btn = QPushButton("Cancel Tare")
        self.zero_cancel_btn.clicked.connect(self._zero_cancel)
        self.zero_cancel_btn.setEnabled(False)
        self.zero_cancel_btn.setVisible(False)
        ctrl_layout.addWidget(self.zero_cancel_btn)

        self.fps_badge = QLabel("")
        self.fps_badge.setStyleSheet(
            "background-color: rgba(16, 185, 129, 0.15); "
            "border: 1px solid #10b981; color: #10b981; "
            "border-radius: 4px; padding: 2px 8px; "
            "font-weight: bold; font-size: 11px; "
            "font-family: 'SF Mono', 'Segoe UI Mono', monospace;"
        )
        ctrl_layout.addWidget(self.fps_badge)
        self.update_fps(0.0)

        ctrl_layout.addStretch()
        self.ctrl_container = QWidget()
        self.ctrl_container.setLayout(ctrl_layout)
        layout.addWidget(self.ctrl_container)

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
        self.modules_group = modules_group
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

    @staticmethod
    def _populate_value_mode_combo(
        combo, has_mt_touch, has_mx_touch, current_value=TOUCH_VALUE_MODE_ADC
    ):
        combo.blockSignals(True)
        combo.clear()
        for label, value in touch_value_mode_options(has_mt_touch, has_mx_touch):
            combo.addItem(label, value)
        target_index = combo.findData(int(current_value))
        combo.setCurrentIndex(max(0, target_index))
        combo.blockSignals(False)

    @staticmethod
    def _combo_value_mode(combo, index):
        value = combo.itemData(index)
        return int(index if value is None else value)

    def _get_module_chart_config(self, mod_key: str):
        if self.has_mx_touch:
            idx = REVO3_MODULE_NAMES.index(mod_key)
            pts = self.mx_point_counts[idx]
            rows, cols = _mx_channel_grid(pts)
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
        if self.is_hybrid:
            names = [
                "🖐 Palm",
                "👍 Thumb Tip (Fn)",
                "👍 Thumb Pad",
                "👆 Index Tip (Fn)",
                "👆 Index Pad",
                "🖕 Middle Tip (Fn)",
                "🖕 Middle Pad",
                "💍 Ring Tip (Fn)",
                "💍 Ring Pad",
                "🤙 Pinky Tip (Fn)",
                "🤙 Pinky Pad",
            ]
            colors = REVO3_MODULE_COLORS
            y_range = (0, int(HP_FORCE_DISPLAY_BASELINE_MN))
            y_label = "mN"
            chart_title = "Touch Summary (Hybrid 11 Modules)"
        elif self.has_hp_touch and not self.is_hybrid:
            names = ["ThumbTip", "IndexTip", "MiddleTip", "RingTip", "PinkyTip"]
            colors = [
                (255, 100, 100),  # Thumb Tip
                (100, 255, 100),  # Index Tip
                (100, 100, 255),  # Middle Tip
                (255, 255, 100),  # Ring Tip
                (255, 100, 255),  # Pinky Tip
            ]
            y_range = (0, int(HP_FORCE_DISPLAY_BASELINE_MN))
            y_label = "mN (Fn)"
            chart_title = "Touch Summary (Fn Force)"
        elif self.has_mx_touch:
            names = [item[1] for item in self.module_info]
            colors = [
                (100, 255, 255),  # Palm
                (255, 100, 100), (255, 100, 100),  # Thumb Tip, Pad
                (100, 255, 100), (100, 255, 100),  # Index Tip, Pad
                (100, 100, 255), (100, 100, 255),  # Middle Tip, Pad
                (255, 255, 100), (255, 255, 100),  # Ring Tip, Pad
                (255, 100, 255), (255, 100, 255),  # Pinky Tip, Pad
            ]
            per_point_limits_mn = [
                self._mx_force_limit_raw(module_id) * 10.0
                for module_id in range(len(MX_FORCE_LIMITS_RAW))
            ]
            y_range = (0, int(max(per_point_limits_mn)))
            y_label = "mN"
            chart_title = "Per-Module Peak Force"
        else:
            names = REVO3_SUMMARY_NAMES
            colors = REVO3_SUMMARY_COLORS
            y_range = (0, int(MT_FORCE_LIMIT_MN))
            y_label = "mN"
            chart_title = "Touch Summary (Force)"

        # 4. Rebuild chart, compass grid and cards
        self.summary_chart = SummaryChart(
            chart_title, y_range,
            sensor_names=names,
            sensor_colors=colors,
            y_label=y_label,
        )
        self.overview_layout.addWidget(self.summary_chart, 0, 0, 1, 1)

        self.summary_compasses = []
        if self.has_hp_touch:
            from .touch_common import ForceCompassWidget
            compass_group = QGroupBox("5-Finger 2D Force Vector Compass (5 指尖矢量罗盘全景)")
            compass_group.setStyleSheet("""
                QGroupBox {
                    border: 1px solid #334155;
                    border-radius: 6px;
                    margin-top: 6px;
                    padding-top: 6px;
                    font-weight: bold;
                    color: #f59e0b;
                }
            """)
            c_lay = QHBoxLayout(compass_group)
            c_lay.setContentsMargins(4, 4, 4, 4)
            c_lay.setSpacing(4)

            hp_names = ["👍 拇指", "👆 食指", "🖕 中指", "💍 无名指", "🤙 小指"]
            for i, c_name in enumerate(hp_names):
                comp = ForceCompassWidget(
                    title=c_name,
                    max_force=HP_FORCE_DISPLAY_BASELINE_MN,
                )
                comp.setMaximumHeight(160)
                self.summary_compasses.append(comp)
                c_lay.addWidget(comp, 1)

            self.overview_layout.addWidget(compass_group, 1, 0, 1, 1)

        self.sensor_cards, self.sensor_bars, self.sensor_labels = build_status_cards(
            self.status_layout, names, colors, is_compact=True
        )

    def _build_hp_mt_layout(self):
        if sdk is None:
            return None
        hp_signals = [
            sdk.TouchSignal.TouchPoint,
            sdk.TouchSignal.Force3D,
            sdk.TouchSignal.Torque2D,
            sdk.TouchSignal.ResultantForce,
        ]
        modules = []
        for i in range(5):
            modules.append(
                sdk.TouchModuleLayout(
                    "hp_fingertip_48",
                    i * 2 + 1,
                    sdk.TouchRegion.Fingertip,
                    i,
                    hp_signals,
                    48,
                )
            )
        mt_pad_counts = [57, 52, 52, 52, 52]
        for i, count in enumerate(mt_pad_counts):
            layout_id = "mt_thumbpad_57" if i == 0 else "mt_fingerpad_52"
            modules.append(
                sdk.TouchModuleLayout(
                    layout_id,
                    (i + 1) * 2,
                    sdk.TouchRegion.FingerPad,
                    i,
                    [sdk.TouchSignal.TouchPoint],
                    count,
                )
            )
        modules.append(
            sdk.TouchModuleLayout(
                "mt_palm_36",
                0,
                sdk.TouchRegion.Palm,
                0,
                [sdk.TouchSignal.TouchPoint],
                36,
            )
        )
        return sdk.TouchLayout(modules)

    def _build_hp_mx_layout(self, mx_point_counts=None):
        if sdk is None:
            return None
        counts = list(mx_point_counts or self.mx_point_counts or [])
        required_ids = [0, 2, 4, 6, 8, 10]
        if len(counts) < 11 or any(counts[index] <= 0 for index in required_ids):
            raise RuntimeError(
                "hp+mx layout override requires confirmed point counts for palm and finger pads"
            )
        hp_signals = [
            sdk.TouchSignal.TouchPoint,
            sdk.TouchSignal.Force3D,
            sdk.TouchSignal.Torque2D,
            sdk.TouchSignal.ResultantForce,
        ]
        modules = []
        for i in range(5):
            modules.append(
                sdk.TouchModuleLayout(
                    "hp_fingertip_48",
                    i * 2 + 1,
                    sdk.TouchRegion.Fingertip,
                    i,
                    hp_signals,
                    48,
                )
            )
        physical_indices = [2, 4, 6, 8, 10]
        for i, phys_idx in enumerate(physical_indices):
            count = counts[phys_idx]
            modules.append(
                sdk.TouchModuleLayout(
                    f"mx_fingerpad_{count}",
                    phys_idx,
                    sdk.TouchRegion.FingerPad,
                    i,
                    [sdk.TouchSignal.TouchPoint],
                    count,
                )
            )
        palm_count = counts[0]
        modules.append(
            sdk.TouchModuleLayout(
                f"mx_palm_{palm_count}",
                0,
                sdk.TouchRegion.Palm,
                0,
                [sdk.TouchSignal.TouchPoint],
                palm_count,
            )
        )
        return sdk.TouchLayout(modules)

    def _build_hp_layout(self):
        if sdk is None:
            return None
        hp_signals = [
            sdk.TouchSignal.TouchPoint,
            sdk.TouchSignal.Force3D,
            sdk.TouchSignal.Torque2D,
            sdk.TouchSignal.ResultantForce,
        ]
        modules = [
            sdk.TouchModuleLayout(
                "hp_fingertip_48",
                i,
                sdk.TouchRegion.Fingertip,
                i,
                hp_signals,
                48,
            )
            for i in range(5)
        ]
        return sdk.TouchLayout(modules)

    def _build_mt_layout(self):
        if sdk is None:
            return None
        mt_counts = [36, 31, 57, 21, 52, 21, 52, 21, 52, 21, 52]
        modules = []
        for i, count in enumerate(mt_counts):
            if i == 0:
                region = sdk.TouchRegion.Palm
                layout_id = "mt_palm_36"
                region_index = 0
            elif i in (1, 3, 5, 7, 9):
                region = sdk.TouchRegion.Fingertip
                region_index = i // 2
                layout_id = "mt_thumbtip_31" if i == 1 else "mt_fingertip_21"
            else:
                region = sdk.TouchRegion.FingerPad
                region_index = i // 2 - 1
                layout_id = "mt_thumbpad_57" if i == 2 else "mt_fingerpad_52"
            modules.append(
                sdk.TouchModuleLayout(
                    layout_id,
                    i,
                    region,
                    region_index,
                    [sdk.TouchSignal.TouchPoint],
                    count,
                )
            )
        return sdk.TouchLayout(modules)

    def _build_mx_layout(self, mx_point_counts=None):
        if sdk is None:
            return None
        counts = list(mx_point_counts or self.mx_point_counts or [])
        if len(counts) < 11 or any(count <= 0 for count in counts[:11]):
            raise RuntimeError(
                "mx layout override requires confirmed point counts for all 11 modules"
            )
        modules = []
        for i in range(11):
            point_count = counts[i]
            if i == 0:
                region = sdk.TouchRegion.Palm
                region_index = 0
                layout_id = f"mx_palm_{point_count}"
            elif i in (1, 3, 5, 7, 9):
                region = sdk.TouchRegion.Fingertip
                region_index = i // 2
                layout_id = f"mx_fingertip_{point_count}"
            else:
                region = sdk.TouchRegion.FingerPad
                region_index = i // 2 - 1
                layout_id = f"mx_fingerpad_{point_count}"
            modules.append(
                sdk.TouchModuleLayout(
                    layout_id,
                    i,
                    region,
                    region_index,
                    [sdk.TouchSignal.TouchPoint],
                    point_count,
                )
            )
        return sdk.TouchLayout(modules)

    def _on_layout_changed(self, index):
        if not self.device:
            return
        if not self._touch_layout_override_supported:
            logger.warning("Touch layout override is unavailable for this device model")
            return
        layout_text = self.layout_combo.currentText()
        logger.info(f"User requested touch layout override: {layout_text} (index {index})")

        async def apply():
            try:
                hand = getattr(self.device, "hand", None)
                if hand is None or not hasattr(hand, "touch"):
                    return
                new_layout = None
                if index == 0:
                    new_layout = self._detected_touch_layout
                elif index == 1:  # Hybrid HP+MT
                    new_layout = self._build_hp_mt_layout()
                elif index == 2:  # Hybrid HP+MX
                    mx_counts = None
                    try:
                        raw_counts = await self.device.get_touch_module_point_counts(
                            self.slave_id
                        )
                        mx_counts = self._mx_values_by_public_module_id(
                            raw_counts, 0
                        )
                    except Exception:
                        pass
                    new_layout = self._build_hp_mx_layout(mx_counts)
                elif index == 3:  # Pure HP
                    new_layout = self._build_hp_layout()
                elif index == 4:  # Pure MT
                    new_layout = self._build_mt_layout()
                elif index == 5:  # Pure MX
                    mx_counts = None
                    try:
                        raw_counts = await self.device.get_touch_module_point_counts(
                            self.slave_id
                        )
                        mx_counts = self._mx_values_by_public_module_id(
                            raw_counts, 0
                        )
                    except Exception:
                        pass
                    new_layout = self._build_mx_layout(mx_counts)

                if new_layout is not None:
                    await self.device.set_touch_layout(self.slave_id, new_layout)
                    logger.info(f"Successfully applied touch layout override: {layout_text}")
                await self._fetch_touch_layout()
            except Exception as e:
                logger.error(f"Failed to apply touch layout override: {e}")
                await self._fetch_touch_layout()

        run_async(apply)

    def _on_hp_module_zero(self, module_idx: int):
        if module_idx < len(self.hp_force_torque_cards) and self.hp_force_torque_cards[module_idx] is not None:
            self.hp_force_torque_cards[module_idx].clear_chart()
        public_module_id = module_idx * 2 + 1 if self.is_hybrid else module_idx
        if hasattr(self.device, "calibrate_touch_zero_single"):
            run_async(lambda: self.device.calibrate_touch_zero_single(self.slave_id, public_module_id))

    def _rebuild_detail_tabs(self):
        if not hasattr(self, "tabs"):
            return

        while self.tabs.count() > 1:
            widget = self.tabs.widget(1)
            self.tabs.removeTab(1)
            if widget is not None:
                widget.deleteLater()

        self.detail_charts = [None] * 11
        self.hp_force_torque_cards = []

        if self.is_hybrid:
            # ── Hybrid Mode: 2 Top-level Category Tabs ──
            # 1. Tab: "🌟 HP" -> 5 Fingertip Cards in Sub-Tabs
            hp_container = QWidget()
            hp_lay = QVBoxLayout(hp_container)
            hp_lay.setContentsMargins(4, 4, 4, 4)

            hp_subtabs = QTabWidget()
            hp_module_info = [
                ("Thumb", "👍 拇指尖 (ThumbTip)", 0, 1, (255, 100, 100)),
                ("Index", "👆 食指尖 (IndexTip)", 1, 3, (100, 255, 100)),
                ("Middle", "🖕 中指尖 (MiddleTip)", 2, 5, (100, 100, 255)),
                ("Ring", "💍 无名指尖 (RingTip)", 3, 7, (255, 255, 100)),
                ("Pinky", "🤙 小指尖 (PinkyTip)", 4, 9, (255, 100, 255)),
            ]
            for name, tab_title, mod_idx, universal_id, color in hp_module_info:
                card = HpForceTorqueModuleCard(
                    name=name,
                    module_idx=mod_idx,
                    universal_id=universal_id,
                    color=color,
                    on_zero_cb=self._on_hp_module_zero,
                )
                self.hp_force_torque_cards.append(card)
                hp_subtabs.addTab(card, tab_title)
            hp_lay.addWidget(hp_subtabs, 1)
            self.tabs.addTab(hp_container, "🌟 HP")

            # 2. Tab: "🗺️ MT/MX" -> 6 Modules (Palm + 5 Pads) in Sub-Tabs
            array_container = QWidget()
            array_lay = QVBoxLayout(array_container)
            array_lay.setContentsMargins(4, 4, 4, 4)

            array_subtabs = QTabWidget()
            revo3_array_modules = [
                (0, "Palm", "🖐 手掌 (Palm)", "Palm"),
                (2, "Thumb Pad", "👍 拇指指腹 (ThumbPad)", "ThumbPad"),
                (4, "Index Pad", "👆 食指指腹 (IndexPad)", "IndexPad"),
                (6, "Middle Pad", "🖕 中指指腹 (MiddlePad)", "MiddlePad"),
                (8, "Ring Pad", "💍 无名指指腹 (RingPad)", "RingPad"),
                (10, "Pinky Pad", "🤙 小指指腹 (PinkyPad)", "PinkyPad"),
            ]
            for mod_idx, name, tab_title, mod_key in revo3_array_modules:
                color = REVO3_MODULE_COLORS[mod_idx]
                pts, rows, cols, coord_map = self._get_module_chart_config(mod_key)
                chart = HeatmapChart(
                    name,
                    pts,
                    color,
                    rows,
                    cols,
                    coord_map=coord_map,
                    cell_aspect=1.0,
                )
                self.detail_charts[mod_idx] = chart

                card_widget = QWidget()
                c_lay = QHBoxLayout(card_widget)
                c_lay.setContentsMargins(4, 4, 4, 4)
                c_lay.addWidget(chart, 1)
                ctrl = self._create_module_ctrl_widget(mod_idx, name)
                c_lay.addWidget(ctrl)
                array_subtabs.addTab(card_widget, tab_title)

            array_lay.addWidget(array_subtabs, 1)
            array_tab_title = "🗺️ MT" if self.has_mt_touch else ("🗺️ MX" if self.has_mx_touch else "🗺️ Array")
            self.tabs.addTab(array_container, array_tab_title)
            return

        if self.has_hp_touch and not self.is_hybrid:
            hp_module_info = [
                ("Thumb", "👍 拇指", 0, 1, (255, 100, 100)),
                ("Index", "👆 食指", 1, 3, (100, 255, 100)),
                ("Middle", "🖕 中指", 2, 5, (100, 100, 255)),
                ("Ring", "💍 无名指", 3, 7, (255, 255, 100)),
                ("Pinky", "🤙 小指", 4, 9, (255, 100, 255)),
            ]

            for name, tab_title, mod_idx, universal_id, color in hp_module_info:
                card = HpForceTorqueModuleCard(
                    name=name,
                    module_idx=mod_idx,
                    universal_id=universal_id,
                    color=color,
                    on_zero_cb=self._on_hp_module_zero,
                )
                self.hp_force_torque_cards.append(card)

                container = QWidget()
                lay = QVBoxLayout(container)
                lay.setContentsMargins(4, 4, 4, 4)
                lay.addWidget(card, 1)
                self.tabs.addTab(container, tab_title)
            return

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
                chart = HeatmapChart(
                    name,
                    pts,
                    color,
                    rows,
                    cols,
                    coord_map=coord_map,
                    cell_aspect=1.0,
                )
                self.detail_charts[mod_idx] = chart

                if self.has_mx_touch or self.has_mt_touch:
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
                finger_layout.setContentsMargins(4, 4, 4, 4)
                finger_layout.setSpacing(8)

                for mod_idx, name, mod_key in modules:
                    color = REVO3_MODULE_COLORS[mod_idx]
                    pts, rows, cols, coord_map = self._get_module_chart_config(mod_key)
                    chart = HeatmapChart(
                        name,
                        pts,
                        color,
                        rows,
                        cols,
                        coord_map=coord_map,
                        cell_aspect=1.0,
                    )
                    self.detail_charts[mod_idx] = chart

                    if self.has_mx_touch or self.has_mt_touch:
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

    def _log_throttled_touch_data(self, revo3_data):
        now = time.time()
        if now - self._last_log_time < 1.0:
            return
        self._last_log_time = now

        if not hasattr(self, "tabs") or self.tabs is None:
            return

        curr_idx = self.tabs.currentIndex()
        tab_title = self.tabs.tabText(curr_idx)

        force_torque_modules = list(getattr(revo3_data, "force_torque_modules", []) or [])
        if force_torque_modules:
            modules_by_id = {
                int(getattr(m, "module_id", i)): m
                for i, m in enumerate(force_torque_modules)
            }
            if curr_idx == 0:
                target_ids = [1, 3, 5, 7, 9] if self.is_hybrid else list(range(len(self.hp_force_torque_cards)))
                fn_str = ", ".join(
                    [
                        f"{getattr(modules_by_id.get(mod_id), 'resultant_force_mn', 0.0):+.1f}mN"
                        for mod_id in target_ids
                    ]
                )
                logger.info(f"[Touch 1s] Tab: '{tab_title}' (Summary) | 5-Finger Fn: [{fn_str}]")
            else:
                mod_idx = curr_idx - 1
                lookup_id = mod_idx * 2 + 1 if self.is_hybrid else mod_idx
                m = modules_by_id.get(lookup_id)
                if m is not None:
                    pts = getattr(m, "points", [])
                    pts_max = max(pts) if pts else 0
                    pts_sum = sum(pts) if pts else 0
                    nonzero_pts = [(i, v) for i, v in enumerate(pts) if v > 0]
                    if nonzero_pts:
                        pts_detail = f" NonZero({len(nonzero_pts)}): {nonzero_pts[:8]}"
                    else:
                        pts_detail = " (all zero)"

                    st = getattr(m, 'status', 0)
                    s_st = getattr(m, 'sensor_status', 0)
                    source_module_id = getattr(m, 'module_id', mod_idx)
                    source_region_index = getattr(m, 'region_index', mod_idx)
                    st_str = f"Ready({st})" if st == 1 else (f"WarmingUp({st})" if st == 0 else f"Offline({st})")
                    sensor_str = f"Normal({s_st})" if s_st == 0 else f"Fault({s_st})"

                    logger.debug(
                        f"[Touch 1s] Tab: '{tab_title}' (Mod {mod_idx}, Source module_id={source_module_id}, region_index={source_region_index}) | "
                        f"Status: {st_str:<12} | Sensor: {sensor_str:<10} | "
                        f"Fx:{getattr(m, 'fx', 0.0):+.1f} Fy:{getattr(m, 'fy', 0.0):+.1f} Fz:{getattr(m, 'fz', 0.0):+.1f} mN "
                        f"Mx:{getattr(m, 'mx', 0.0):+.2f} My:{getattr(m, 'my', 0.0):+.2f} Fn:{getattr(m, 'resultant_force_mn', 0.0):+.1f}mN | "
                        f"FilmPoints({len(pts)}): max={pts_max} sum={pts_sum}{pts_detail}"
                    )
        elif hasattr(revo3_data, "summary_values") and hasattr(revo3_data, "modules"):
            if curr_idx == 0:
                s = getattr(revo3_data, "summary_values", [])
                logger.debug(f"[Touch 1s] Tab: '{tab_title}' (Summary) | Summary len={len(s)}")
            else:
                mods = getattr(revo3_data, 'modules', [])
                lengths = [len(module or []) for module in mods]
                maxima = [max(module) if module else 0 for module in mods]
                logger.debug(
                    f"[Touch 1s] Tab: '{tab_title}' | Modules count={len(mods)} "
                    f"| lengths={lengths} | max={maxima}"
                )

    def _sync_mx_point_counts_from_frame(self, modules):
        if not self.has_mx_touch or self._mx_frame_counts_synced:
            return
        observed_counts = [len(module or []) for module in list(modules)[:11]]
        if len(observed_counts) != 11 or any(count <= 0 for count in observed_counts):
            return
        self._mx_frame_counts_synced = True
        if observed_counts == self.mx_point_counts:
            return
        self.mx_point_counts = observed_counts
        logger.info(f"mx_* touch point counts synchronized from frame: {observed_counts}")
        self._rebuild_status_cards()
        self._rebuild_detail_tabs()
        self._refresh_detail_chart_units()

    def update_data(self, revo3_data):
        """Process Revo3 Touch data.

        revo3_data: GUI payload with summary_values and module-indexed point arrays.
        """
        self._log_throttled_touch_data(revo3_data)

        ft_modules_by_id = {}
        force_torque_modules = list(getattr(revo3_data, "force_torque_modules", []) or [])
        if force_torque_modules:
            for idx, m in enumerate(force_torque_modules):
                mid = int(getattr(m, "module_id", idx * 2 + 1 if self.is_hybrid else idx))
                ft_modules_by_id[mid] = m
                # Keep the positional alias only as a legacy fallback. Never let
                # it overwrite an explicit public module ID such as 1/3/5/7/9.
                ft_modules_by_id.setdefault(idx, m)

            if not self.is_hybrid:
                slot_count = len(self.hp_force_torque_cards)
                fn_list = [
                    getattr(ft_modules_by_id.get(i), "resultant_force_mn", 0.0)
                    for i in range(slot_count)
                ]
                if hasattr(self, "summary_chart") and self.summary_chart is not None:
                    self.summary_chart.add_data(fn_list)
                for idx, val in enumerate(fn_list):
                    if idx < len(self.sensor_bars):
                        bar_max = max(int(HP_FORCE_DISPLAY_BASELINE_MN), int(val * 1.1))
                        self.sensor_bars[idx].setRange(0, bar_max)
                        self.sensor_bars[idx].setValue(int(min(val, float(bar_max))))
                        self.sensor_labels[idx].setText(f"Fn:{val:+.1f}mN")

            # Update 5 HP cards on Tab 1
            for idx, card in enumerate(self.hp_force_torque_cards):
                lookup_id = idx * 2 + 1 if self.is_hybrid else idx
                m = ft_modules_by_id.get(lookup_id)
                if card is not None and m is not None:
                    card.update_payload(m)
                if hasattr(self, "summary_compasses") and idx < len(self.summary_compasses) and self.summary_compasses[idx] is not None:
                    if m is not None:
                        self.summary_compasses[idx].set_values(
                            getattr(m, "fx", 0.0),
                            getattr(m, "fy", 0.0),
                            getattr(m, "fz", 0.0),
                            getattr(m, "mx", 0.0),
                            getattr(m, "my", 0.0),
                            getattr(m, "resultant_force_mn", 0.0),
                        )
                    else:
                        self.summary_compasses[idx].set_values(0.0, 0.0, 0.0, 0.0, 0.0, 0.0)

            if not self.is_hybrid:
                return

        modules = getattr(revo3_data, 'modules', []) or []
        summary = list(getattr(revo3_data, "summary_values", []) or [])
        self._sync_mx_point_counts_from_frame(modules)

        if self.is_hybrid:
            summary_11 = [0.0] * 11
            raw_summary = summary
            mt_summary_slices = {
                0: (0, 1),
                2: (4, 10),
                4: (13, 18),
                6: (21, 26),
                8: (29, 34),
                10: (37, 42),
            }

            for i in range(11):
                if i in (1, 3, 5, 7, 9):
                    # HP Fingertip modules (Universal IDs 1, 3, 5, 7, 9)
                    m = ft_modules_by_id.get(i)
                    fn_val = float(getattr(m, "resultant_force_mn", 0.0) or 0.0) if m is not None else 0.0
                    st = getattr(m, "status", 0) if m is not None else 0
                    summary_11[i] = fn_val
                    if i < len(self.sensor_bars):
                        bar_max = max(
                            int(HP_FORCE_DISPLAY_BASELINE_MN), int(fn_val * 1.1)
                        )
                        self.sensor_bars[i].setRange(0, bar_max)
                        self.sensor_bars[i].setValue(int(min(max(fn_val, 0.0), float(bar_max))))
                        st_str = "Ready" if st == 1 else "Offline"
                        self.sensor_labels[i].setText(f"Fn: {fn_val:+.1f} mN\n{st_str}")
                else:
                    # Array palm and fingerpad modules (public IDs 0, 2, 4, 6, 8, 10).
                    pts = list(modules[i] or []) if (modules and i < len(modules)) else []
                    if not pts and len(raw_summary) >= 42 and i in mt_summary_slices:
                        s_start, s_end = mt_summary_slices[i]
                        pts = raw_summary[s_start:s_end]

                    max_v = float(max(pts)) if pts else 0.0
                    sum_v = float(sum(pts)) if pts else 0.0
                    avg_v = sum_v / len(pts) if pts else 0.0
                    summary_11[i] = max_v
                    if i < len(self.sensor_bars):
                        value_unit, limit_val, _ = self._array_chart_scale(i)
                        unit_str = "mN" if value_unit == "force" else "ADC"
                        self.sensor_bars[i].setRange(0, int(limit_val))
                        self.sensor_bars[i].setValue(int(min(max(max_v, 0.0), limit_val)))
                        self.sensor_labels[i].setText(f"max:{max_v:.0f} avg:{avg_v:.0f}\nsum:{sum_v:.0f} {unit_str}")

            if hasattr(self, "summary_chart") and self.summary_chart is not None:
                self.summary_chart.add_data(summary_11)
        elif self.has_mx_touch and modules:
            summary_11 = [0.0] * 11
            for i, module_points in enumerate(modules[:11]):
                summary_11[i] = max(list(module_points or [0.0]))

            self.summary_chart.add_data(summary_11)
            for i, val in enumerate(summary_11):
                if i < len(self.sensor_bars):
                    is_force = (
                        self.mx_modes[i] == TOUCH_VALUE_MODE_FORCE
                        if i < len(self.mx_modes)
                        else True
                    )
                    pts = list(modules[i] or []) if i < len(modules) else []
                    if is_force:
                        pts_scaled = pts
                        n_total = len(pts_scaled) if pts_scaled else 1
                        max_v = max(pts_scaled) if pts_scaled else 0
                        min_v = min(pts_scaled) if pts_scaled else 0
                        sum_v = sum(pts_scaled) if pts_scaled else 0
                        avg_v = sum_v / n_total if pts_scaled else 0
                        active_vals = [v for v in pts_scaled if v > 0]
                        a_avg = sum(active_vals) / len(active_vals) if active_vals else 0
                        cnt = len(active_vals)

                        point_limit_mN = self._mx_force_limit_raw(i) * 10.0
                        sum_limit_mN = point_limit_mN * n_total
                        avg_limit_mN = point_limit_mN

                        # Map ProgressBar to Average force (avg_v) within [0, avg_limit_mN]
                        self.sensor_bars[i].setRange(0, int(avg_limit_mN))
                        self.sensor_bars[i].setValue(min(int(avg_v), int(avg_limit_mN)))

                        sn_str = self.mx_module_sns[i] if (self.has_mx_touch and i < len(self.mx_module_sns)) else ""
                        if not sn_str and self.has_mx_touch:
                            sn_str = "—"
                        sn_line = f"\nSN: {sn_str}" if self.has_mx_touch else ""
                        self.sensor_labels[i].setText(
                            f"max:{max_v:.0f} avg:{avg_v:.0f}/{avg_limit_mN:.0f} mN\n"
                            f"sum:{sum_v:.0f}/{sum_limit_mN:.0f} mN  cnt:{cnt}/{n_total}"
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

                        sn_str = self.mx_module_sns[i] if (self.has_mx_touch and i < len(self.mx_module_sns)) else ""
                        if not sn_str and self.has_mx_touch:
                            sn_str = "—"
                        sn_line = f"\nSN: {sn_str}" if self.has_mx_touch else ""
                        self.sensor_labels[i].setText(
                            f"max:{int(max_v)} avg:{avg_v:.0f}/255\n"
                            f"sum:{int(sum_v)}  cnt:{cnt}/{n_total}"
                            f"{sn_line}"
                        )
        elif summary and len(summary) >= 42:
            summary_42 = list(summary[:42])
            self.summary_chart.add_data(summary_42)
            value_unit, limit_val, _ = self._mt_chart_scale()
            is_force = value_unit == "force"
            for i, val in enumerate(summary_42):
                if i < len(self.sensor_bars):
                    self.sensor_bars[i].setRange(0, int(limit_val))
                    self.sensor_bars[i].setValue(min(int(val), int(limit_val)))
                    if is_force:
                        self.sensor_labels[i].setText(
                            f"{float(val):.0f}/{limit_val:.0f} mN"
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
                    limit = 255.0
                    value_unit = "adc"
                    stats_limit = 255.0
                    if self.has_mx_touch:
                        is_force = (
                            self.mx_modes[i] == TOUCH_VALUE_MODE_FORCE
                            if i < len(self.mx_modes)
                            else True
                        )
                        if is_force:
                            limit = self._mx_force_limit_raw(i) * 10.0
                            value_unit = "force"
                            stats_limit = limit
                        else:
                            limit = 255.0
                            stats_limit = 255.0
                    elif hasattr(self, "read_mode_combo") and self.read_mode_combo is not None:
                        value_unit, limit, stats_limit = self._mt_chart_scale()

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
        self.update_fps(self._last_touch_fps)
        self.tabs.setTabText(0, f"📊 {tr('touch_summary')}")

        if self.is_hybrid:
            if self.tabs.count() > 1:
                self.tabs.setTabText(1, "🌟 HP")
            if self.tabs.count() > 2:
                array_tab_title = "🗺️ MT" if self.has_mt_touch else ("🗺️ MX" if self.has_mx_touch else "🗺️ Array")
                self.tabs.setTabText(2, array_tab_title)
        elif self.has_hp_touch:
            hp_tab_names = [
                ("touch_thumb", "👍"),
                ("touch_index", "👆"),
                ("touch_middle", "🖕"),
                ("touch_ring", "💍"),
                ("touch_pinky", "🤙"),
            ]
            for i, (tr_key, icon) in enumerate(hp_tab_names):
                if i + 1 < self.tabs.count():
                    self.tabs.setTabText(i + 1, f"{icon} {tr(tr_key)}")
        else:
            revo3_finger_groups = [
                ("touch_palm", "🖐"),
                ("touch_thumb", "👆"),
                ("touch_index", "👆"),
                ("touch_middle", "👆"),
                ("touch_ring", "👆"),
                ("touch_pinky", "👆"),
            ]
            for i, (tr_key, icon) in enumerate(revo3_finger_groups):
                if i + 1 < self.tabs.count():
                    self.tabs.setTabText(i + 1, f"{icon} {tr(tr_key)}")

        # Update control bar texts dynamically (supporting translation dynamically)
        if hasattr(self, "layout_label") and self.layout_label is not None:
            self.layout_label.setText(
                tr("touch_layout") if tr("touch_layout") != "touch_layout" else "Touch Layout:"
            )
        self.read_mode_label.setText(tr("touch_read_mode") if tr("touch_read_mode") != "touch_read_mode" else "Touch Read Mode:")
        self.read_btn.setText(
            tr("btn_read_touch_enabled")
            if tr("btn_read_touch_enabled") != "btn_read_touch_enabled"
            else "Read Enable State"
        )
        self.snapshot_btn.setText(
            tr("btn_read_touch_snapshot")
            if tr("btn_read_touch_snapshot") != "btn_read_touch_snapshot"
            else "Read Snapshot"
        )
        self.enable_all_btn.setText(
            tr("btn_enable_all_touch")
            if tr("btn_enable_all_touch") != "btn_enable_all_touch"
            else "Enable All"
        )
        self.disable_all_btn.setText(
            tr("btn_disable_all_touch")
            if tr("btn_disable_all_touch") != "btn_disable_all_touch"
            else "Disable All"
        )
        self.read_sn_btn.setText(
            tr("btn_read_module_sns")
            if tr("btn_read_module_sns") != "btn_read_module_sns"
            else "Read SN"
        )
        self.read_points_btn.setText(
            tr("btn_read_point_counts")
            if tr("btn_read_point_counts") != "btn_read_point_counts"
            else "Read Points"
        )
        if hasattr(self, "read_output_mode_btn") and self.read_output_mode_btn:
            self._update_value_mode_texts()
        if hasattr(self, "read_tare_status_btn") and self.read_tare_status_btn:
            self.read_tare_status_btn.setText(
                tr("btn_read_tare_status")
                if tr("btn_read_tare_status") != "btn_read_tare_status"
                else "Read Tare State"
            )
        self._update_zero_button_texts()
        if hasattr(self, "zero_cancel_btn") and self.zero_cancel_btn:
            self.zero_cancel_btn.setText(
                tr("btn_touch_zero_cancel")
                if tr("btn_touch_zero_cancel") != "btn_touch_zero_cancel"
                else "Cancel Tare"
            )
        if hasattr(self, "tabs") and self.tabs:
            self.tabs.tabBar().updateGeometry()
            self.tabs.tabBar().update()

    def update_fps(self, touch_fps: float):
        self._last_touch_fps = max(0.0, float(touch_fps))
        if not hasattr(self, "fps_badge") or self.fps_badge is None:
            return
        touch_name = tr("fps_touch_prefix")
        if self._last_touch_fps > 0:
            self.fps_badge.setText(f"{touch_name} FPS: {self._last_touch_fps:.1f}")
        else:
            self.fps_badge.setText(f"{touch_name} FPS: --")

    def _update_zero_button_texts(self):
        if not hasattr(self, "zero_calibrate_btn") or self.zero_calibrate_btn is None:
            return
        self.zero_calibrate_btn.setText(
            tr("btn_touch_tare_all")
            if tr("btn_touch_tare_all") != "btn_touch_tare_all"
            else "Tare All Touch Modules"
        )
        self.zero_calibrate_btn.setToolTip(
            "对当前布局中的全部触觉模块执行零漂校准"
        )

    def _update_value_mode_texts(self):
        mt_only = self.is_hybrid and self.has_mt_touch and not self.has_mx_touch
        label_key = "mt_touch_value_mode" if mt_only else "touch_value_mode"
        button_key = "btn_read_mt_mode" if mt_only else "btn_read_mode"
        self.value_mode_label.setText(tr(label_key))
        self.read_output_mode_btn.setText(tr(button_key))
        tooltip = (
            "仅适用于 MT 手掌和指腹；HP 指尖不支持 ADC/Force 数值模式"
            if mt_only
            else "读取支持数值模式配置的触觉模块"
        )
        self.value_mode_label.setToolTip(tooltip)
        self.value_mode_combo.setToolTip(tooltip)
        self.read_output_mode_btn.setToolTip(tooltip)

    def _on_tab_changed(self, index):
        if not self.device or (self.has_hp_touch and not self.is_hybrid):
            return
        if self.has_mx_touch:
            run_async(self._refresh_active_tab_mx_modes)
            return
        # Tab 0 uses legacy summary mode (1); detail tabs use point-array mode (0).
        target_type = 1 if index == 0 else 0
        if self.read_mode_combo.currentIndex() != target_type:
            mode_str = (
                "Legacy Secondary-Calibrated Force Summary"
                if target_type == 1
                else "Point Array"
            )
            tab_name = self.tabs.tabText(index)
            logger.info(
                f"Tab changed to {index} ({tab_name}). "
                f"Automatically switching touch read mode to {target_type} ({mode_str})"
            )
            self.read_mode_combo.setCurrentIndex(target_type)

    def _on_read_mode_changed(self, index):
        if not self.device or not self.has_mt_touch:
            return
        # Combo index 0 = PointArray, 1 = LegacyForceSummary.
        val = int(index)
        mode_str = (
            "Legacy Secondary-Calibrated Force Summary"
            if val == 1
            else "Point Array"
        )
        logger.info(f"Setting touch read mode to {val} ({mode_str})")
        try:
            from common_imports import sdk
            if sdk is not None and hasattr(sdk, "TouchReadMode"):
                mode = sdk.TouchReadMode(val)
            else:
                mode = val
            run_async(lambda: self.device.set_touch_read_mode(self.slave_id, mode))
            self._refresh_detail_chart_units()
            if val == 1 and self.tabs.currentIndex() != 0:
                self.tabs.setCurrentIndex(0)
        except Exception as e:
            logger.error(f"Failed to set touch read mode: {e}")

    def _on_global_value_mode_changed(self, index):
        if not self.device or not (self.has_mt_touch or self.has_mx_touch):
            return
        val = self._combo_value_mode(self.value_mode_combo, index)
        self._global_value_mode = val
        mode_str = {
            TOUCH_VALUE_MODE_ADC: "ADC",
            TOUCH_VALUE_MODE_FORCE: "Force",
        }.get(val, str(val))
        logger.info(f"Setting global touch value mode to {val} ({mode_str})")
        try:
            for i in range(len(self.mx_modes)):
                self.mx_modes[i] = val
                combo = self.findChild(QComboBox, f"mode_{i}")
                if combo:
                    combo.blockSignals(True)
                    combo_index = combo.findData(val)
                    if combo_index >= 0:
                        combo.setCurrentIndex(combo_index)
                    combo.blockSignals(False)
            if self.summary_chart is not None:
                self.summary_chart.clear()
            self._refresh_detail_chart_units()
            if hasattr(self.device, "set_touch_value_mode"):
                run_async(lambda: self.device.set_touch_value_mode(self.slave_id, val))
        except Exception as e:
            logger.error(f"Failed to set global touch value mode: {e}")

    def _refresh_detail_chart_units(self):
        if self.has_hp_touch and not self.is_hybrid:
            return
        if self.has_mx_touch:
            mx_module_ids = [
                int(getattr(module, "module_id", -1))
                for module in list(
                    getattr(self._active_touch_layout, "modules", []) or []
                )
                if str(getattr(module, "layout_id", "")).startswith("mx_")
            ]
            if not mx_module_ids:
                mx_module_ids = list(range(len(self.mx_modes)))
            active_modes = [
                self.mx_modes[module_id]
                for module_id in mx_module_ids
                if 0 <= module_id < len(self.mx_modes)
            ]
            has_force = any(
                mode == TOUCH_VALUE_MODE_FORCE for mode in active_modes
            )
            has_adc = any(
                mode != TOUCH_VALUE_MODE_FORCE for mode in active_modes
            )
            if (has_force and has_adc) or (self.has_hp_touch and has_adc):
                summary_unit = "mN / ADC"
            elif has_force:
                summary_unit = "mN"
            else:
                summary_unit = "ADC"
            summary_limit = max(
                max(
                    self._mx_force_limit_raw(module_id) * 10.0
                    for module_id in range(len(MX_FORCE_LIMITS_RAW))
                )
                if has_force else 0,
                255.0 if has_adc else 0,
                HP_FORCE_DISPLAY_BASELINE_MN if self.has_hp_touch else 0,
            )
            if self.summary_chart is not None:
                self.summary_chart.set_y_axis((0, int(summary_limit)), summary_unit)

            for i, chart in enumerate(self.detail_charts):
                if chart is None:
                    continue
                is_force = (
                    self.mx_modes[i] == TOUCH_VALUE_MODE_FORCE
                    if i < len(self.mx_modes)
                    else True
                )
                if is_force:
                    limit = self._mx_force_limit_raw(i) * 10.0
                    chart.set_value_unit("force", limit, stats_max_limit=limit)
                else:
                    chart.set_value_unit("adc", 255.0, stats_max_limit=255.0)
            return

        value_unit, max_limit, stats_limit = self._mt_chart_scale()
        if self.summary_chart is not None:
            summary_label = "mN" if value_unit == "force" else "ADC"
            summary_limit = max_limit
            if self.has_hp_touch:
                summary_limit = max(summary_limit, HP_FORCE_DISPLAY_BASELINE_MN)
                if value_unit != "force":
                    summary_label = "mN / ADC"
            self.summary_chart.set_y_axis(
                (0, int(summary_limit)), summary_label
            )
        for chart in self.detail_charts:
            if chart is not None:
                chart.set_value_unit(
                    value_unit, max_limit, stats_max_limit=stats_limit
                )

    def _mt_chart_scale(self):
        if self.read_mode_combo.currentIndex() == 1:
            return "force", MT_FORCE_LIMIT_MN, None
        if self._global_value_mode == TOUCH_VALUE_MODE_FORCE:
            return "force", MT_FORCE_LIMIT_MN, MT_FORCE_LIMIT_MN
        return "adc", MT_ADC_MAX, MT_ADC_MAX

    def _array_chart_scale(self, module_id):
        if self._module_layout_id(module_id).startswith("mx_"):
            is_force = (
                self.mx_modes[module_id] == TOUCH_VALUE_MODE_FORCE
                if 0 <= module_id < len(self.mx_modes)
                else False
            )
            if is_force:
                limit = self._mx_force_limit_raw(module_id) * 10.0
                return "force", limit, limit
            return "adc", 255.0, 255.0
        return self._mt_chart_scale()

    def _mx_force_limit_raw(self, module_id):
        if not 0 <= module_id < len(MX_FORCE_LIMITS_RAW):
            raise IndexError(f"mx_* module ID {module_id} is out of range")

        side = self._hand_side
        side_name = str(getattr(side, "name", side) or "").lower()
        try:
            side_value = int(side)
        except (TypeError, ValueError):
            side_value = None

        if side_name == "right" or side_name.endswith(".right") or side_value == 1:
            return MX_FORCE_LIMITS_RAW_RIGHT[module_id]
        if side_name == "left" or side_name.endswith(".left") or side_value == 0:
            return MX_FORCE_LIMITS_RAW_LEFT[module_id]
        return MX_FORCE_LIMITS_RAW[module_id]

    def _read_read_mode(self):
        if not self.device:
            return
        if not self.has_mt_touch:
            return
        async def fetch():
            try:
                val = await self.device.get_touch_read_mode(self.slave_id)
                val_int = int(val)
                mode_str = (
                    "Legacy Secondary-Calibrated Force Summary"
                    if val_int == 1
                    else "Point Array"
                )
                logger.info(f"Fetched touch read mode: {val_int} ({mode_str})")
                # block signals temporarily to avoid triggering currentIndexChanged
                self.read_mode_combo.blockSignals(True)
                self.read_mode_combo.setCurrentIndex(1 if val_int == 1 else 0)
                self.read_mode_combo.blockSignals(False)
                self._refresh_detail_chart_units()
            except Exception as e:
                logger.error(f"Failed to read touch read mode: {e}")
        run_async(fetch)

    def _zero_calibrate(self):
        if not self.device:
            return
        logger.info("Calibrating touch sensor zero drift...")
        for card in getattr(self, "hp_force_torque_cards", []):
            if card is not None:
                card.clear_chart()
        if hasattr(self, "summary_chart") and self.summary_chart is not None:
            self.summary_chart.clear()
        try:
            if self.has_mt_touch and hasattr(self.device, "calibrate_touch_zero"):
                run_async(lambda: self.device.calibrate_touch_zero(self.slave_id))
            else:
                run_async(lambda: self.device.calibrate_touch_zero(self.slave_id))
        except Exception as e:
            logger.error(f"Failed to calibrate touch zero drift: {e}")

    def _zero_cancel(self):
        if not self.device:
            return
        if not self.has_mx_touch:
            logger.info("mt_* touch does not support tare cancellation; ignoring request.")
            return
        logger.info("Canceling global touch sensor zero drift...")
        try:
            run_async(lambda: self.device.set_touch_tare(self.slave_id, 2))
        except Exception as e:
            logger.error(f"Failed to cancel global touch zero drift: {e}")

    def _update_zero_buttons(self, enabled: bool):
        has_touch = self.has_hp_touch or self.has_mt_touch or self.has_mx_touch
        if hasattr(self, "zero_calibrate_btn") and self.zero_calibrate_btn:
            self.zero_calibrate_btn.setEnabled(enabled and has_touch)
            self.zero_calibrate_btn.setVisible(has_touch)
        if hasattr(self, "zero_cancel_btn") and self.zero_cancel_btn:
            self.zero_cancel_btn.setEnabled(enabled and self.has_mx_touch)
            self.zero_cancel_btn.setVisible(self.has_mx_touch)
        if hasattr(self, "restart_btn") and self.restart_btn:
            self.restart_btn.setEnabled(enabled and self.has_mx_touch)
            self.restart_btn.setVisible(self.has_mx_touch)

    def _update_mx_read_buttons(self, enabled: bool):
        is_matrix = bool(enabled and self.device and self.has_mx_touch)
        read_sn_btn = getattr(self, "read_sn_btn", None)
        if read_sn_btn is not None:
            supported = is_matrix and hasattr(
                self.device, "get_touch_module_serial_numbers"
            )
            read_sn_btn.setEnabled(supported)
            read_sn_btn.setVisible(supported)

        read_output_mode_btn = getattr(self, "read_output_mode_btn", None)
        if read_output_mode_btn is not None:
            supported = bool(
                enabled
                and self.device
                and (self.has_mt_touch or self.has_mx_touch)
                and hasattr(self.device, "get_touch_value_mode")
            )
            read_output_mode_btn.setEnabled(supported)
            read_output_mode_btn.setVisible(supported)

        button_specs = [
            (getattr(self, "read_points_btn", None), "get_touch_module_point_counts"),
            (
                getattr(self, "read_tare_status_btn", None),
                "get_touch_module_tare_statuses",
                "get_touch_tare_status",
            ),
        ]
        for spec in button_specs:
            btn = spec[0]
            if btn is None:
                continue
            api_names = spec[1:]
            supported = is_matrix and any(hasattr(self.device, api_name) for api_name in api_names)
            btn.setEnabled(supported)
            btn.setVisible(supported)

    def _restart_touch(self):
        if not self.device or not hasattr(self.device, "restart_touch_modules"):
            return
        logger.info("Restarting supported mx_* touch modules")
        run_async(lambda: self.device.restart_touch_modules(self.slave_id))

    def _module_layout_id(self, module_id):
        for module in list(getattr(self._active_touch_layout, "modules", []) or []):
            if int(getattr(module, "module_id", -1)) == int(module_id):
                return str(getattr(module, "layout_id", "") or "")
        return ""

    def _mx_modules(self):
        return [
            module
            for module in list(getattr(self._active_touch_layout, "modules", []) or [])
            if str(getattr(module, "layout_id", "") or "").startswith("mx_")
        ]

    def _mx_values_by_public_module_id(self, values, default):
        return map_touch_metadata_by_public_module_id(
            self._active_touch_layout, "mx_", values, default
        )

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
        title.setStyleSheet("color: #00FF66; font-size: 11px;")
        layout.addWidget(title)

        # Zero tare for the current module only.
        module_layout_id = self._module_layout_id(mod_idx)
        module_family = "MT" if module_layout_id.startswith("mt_") else "MX"
        tare_btn = QPushButton(f"当前 {module_family} 模块清零")
        tare_btn.setToolTip(f"仅校准当前模块：{mod_name}")
        tare_btn.clicked.connect(lambda: self._on_module_tare(mod_idx))
        layout.addWidget(tare_btn)

        if module_layout_id.startswith("mx_"):
            mode_label = QLabel("Value Mode:")
            layout.addWidget(mode_label)
            mode_combo = QComboBox()
            current_mode = (
                self.mx_modes[mod_idx]
                if mod_idx < len(self.mx_modes)
                else TOUCH_VALUE_MODE_ADC
            )
            self._populate_value_mode_combo(
                mode_combo,
                False,
                True,
                current_mode,
            )
            mode_combo.currentIndexChanged.connect(
                lambda idx, mid=mod_idx: self._on_module_mode_change(mid, idx)
            )
            mode_combo.setObjectName(f"mode_{mod_idx}")
            layout.addWidget(mode_combo)

            cancel_btn = QPushButton("Cancel Tare")
            cancel_btn.clicked.connect(lambda: self._on_module_tare_cancel(mod_idx))
            layout.addWidget(cancel_btn)

            restart_btn = QPushButton("Restart Module")
            restart_btn.clicked.connect(lambda: self._on_module_restart(mod_idx))
            layout.addWidget(restart_btn)

            status_label = QLabel("Zero Status: --")
            status_label.setObjectName(f"status_{mod_idx}")
            layout.addWidget(status_label)

        layout.addStretch()
        return frame

    def _on_module_tare(self, mod_idx):
        if not self.device:
            return
        logger.info(f"Triggering single module {mod_idx} zero tare")
        run_async(lambda: self.device.calibrate_touch_zero_single(self.slave_id, mod_idx))

    def _on_module_tare_cancel(self, mod_idx):
        if not self.device or not self._module_layout_id(mod_idx).startswith("mx_"):
            return
        logger.info(f"Canceling single module {mod_idx} zero tare")
        run_async(lambda: self.device.set_touch_module_tare(self.slave_id, mod_idx, 2))

    def _on_module_restart(self, mod_idx):
        if not self.device or not self._module_layout_id(mod_idx).startswith("mx_"):
            return
        logger.info(f"Restarting mx_* touch module {mod_idx}")
        run_async(lambda: self.device.restart_touch_module(self.slave_id, mod_idx))

    def _on_module_mode_change(self, mod_idx, mode_idx):
        if not self.device or not self._module_layout_id(mod_idx).startswith("mx_"):
            return
        combo = self.findChild(QComboBox, f"mode_{mod_idx}")
        mode_value = self._combo_value_mode(combo, mode_idx) if combo else int(mode_idx)
        logger.info(
            f"Setting module {mod_idx} value mode to {mode_value} "
            "(0=ADC, 2=Force)"
        )
        if mod_idx < len(self.mx_modes):
            self.mx_modes[mod_idx] = mode_value
        if self.summary_chart is not None:
            self.summary_chart.clear()
        self._refresh_detail_chart_units()
        run_async(
            lambda: self.device.set_touch_module_value_mode(
                self.slave_id, mod_idx, mode_value
            )
        )

    async def _refresh_active_tab_mx_modes(self):
        if not self.device or not self.has_mx_touch:
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
                if hasattr(self.device, "get_touch_module_value_mode"):
                    mode = await self.device.get_touch_module_value_mode(self.slave_id, mid)
                    mode_val = int(mode)
                    mode_changed = mid < len(self.mx_modes) and self.mx_modes[mid] != mode_val
                    if mid < len(self.mx_modes):
                        self.mx_modes[mid] = mode_val
                    if mode_changed and self.summary_chart is not None:
                        self.summary_chart.clear()
                    combo = self.findChild(QComboBox, f"mode_{mid}")
                    if combo:
                        combo.blockSignals(True)
                        combo_index = combo.findData(mode_val)
                        if combo_index >= 0:
                            combo.setCurrentIndex(combo_index)
                        combo.blockSignals(False)
            except Exception as e:
                logger.error(f"Failed to fetch module {mid} output mode: {e}")
        self._refresh_detail_chart_units()

    def _read_modules_enabled(self):
        if not self.device:
            return
        async def fetch():
            try:
                # Fetch enabled mask
                bits = await self.device.get_all_touch_modules_enabled(self.slave_id)
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

    def _set_all_modules_enabled(self, enabled):
        if not self.device or not hasattr(self.device, "set_all_touch_modules_enabled"):
            return
        modules = list(getattr(self._active_touch_layout, "modules", []) or [])
        mask = 0
        if enabled:
            for module in modules:
                module_id = int(getattr(module, "module_id", -1))
                if 0 <= module_id < 16:
                    mask |= 1 << module_id

        async def apply():
            try:
                await self.device.set_all_touch_modules_enabled(self.slave_id, mask)
                await self._fetch_enabled_mask()
            except Exception as e:
                logger.error(f"Failed to set touch enabled mask 0x{mask:04X}: {e}")

        run_async(apply)

    async def _fetch_enabled_mask(self):
        bits = await self.device.get_all_touch_modules_enabled(self.slave_id)
        logger.info(f"Fetched touch modules enabled bitmask: {bin(bits)}")
        for cb, item in zip(self.module_checks, self.module_info):
            mod_id = item[0]
            cb.blockSignals(True)
            cb.setChecked(bool((bits >> mod_id) & 1))
            cb.blockSignals(False)
        return bits

    def _on_module_toggle(self, module_id, enabled):
        if not self.device:
            return
        logger.info(f"Toggling touch module {module_id} -> {enabled}")
        try:
            run_async(lambda: self.device.set_touch_module_enabled(self.slave_id, module_id, enabled))
        except Exception as e:
            logger.error(f"Failed to set touch module {module_id} enabled: {e}")
            # Re-read to sync back on error
            self._read_modules_enabled()

    def _read_all_settings(self):
        if self.has_mt_touch:
            self._read_read_mode()
        if self.has_mt_touch or self.has_mx_touch:
            self._read_mx_output_mode()
        self._read_modules_enabled()

    def _read_touch_snapshot(self):
        if not self.device or not hasattr(self.device, "get_all_touch_data"):
            return

        async def fetch():
            try:
                snapshot = await self.device.get_all_touch_data(self.slave_id)
                self.update_data(snapshot)
                logger.info("Fetched one touch snapshot")
            except Exception as e:
                logger.error(f"Failed to read touch snapshot: {e}")

        run_async(fetch)

    async def _fetch_touch_layout(self):
        try:
            layout = None
            if hasattr(self.device, "get_touch_layout"):
                layout = await self.device.get_touch_layout(self.slave_id)
            elif hasattr(self.device, "touch_layout"):
                layout = self.device.touch_layout
            elif hasattr(getattr(self.device, "hand", None), "touch"):
                layout = self.device.hand.touch.layout

            modules = getattr(layout, "modules", []) or []
            self._active_touch_layout = layout
            if self._detected_touch_layout is None and layout is not None:
                self._detected_touch_layout = layout
            layout_ids = [str(getattr(m, "layout_id", "")) for m in modules]

            self.has_hp_touch = any(lid.startswith("hp_") for lid in layout_ids)
            self.has_mx_touch = any(lid.startswith("mx_") for lid in layout_ids)
            self.has_mt_touch = any(lid.startswith("mt_") for lid in layout_ids)
            self.is_hybrid = self.has_hp_touch and (
                self.has_mx_touch or self.has_mt_touch
            )

            if self.has_hp_touch and not self.is_hybrid:
                if hasattr(self, "modules_group") and self.modules_group:
                    self.modules_group.setTitle("Active Fingertip Modules (5 指尖触觉使能)")
                    self.modules_group.setVisible(True)
                hp_labels = [
                    "👍 拇指尖 (ThumbTip)",
                    "👆 食指尖 (IndexTip)",
                    "🖕 中指尖 (MiddleTip)",
                    "💍 无名指尖 (RingTip)",
                    "🤙 小指尖 (PinkyTip)",
                ]
                for i, cb in enumerate(self.module_checks):
                    if i < 5:
                        cb.setText(hp_labels[i])
                        cb.setVisible(True)
                        cb.setEnabled(True)
                    else:
                        cb.setVisible(False)

                if hasattr(self, "ctrl_container") and self.ctrl_container:
                    self.ctrl_container.setVisible(True)
                if hasattr(self, "read_mode_label"):
                    self.read_mode_label.setVisible(False)
                if hasattr(self, "read_mode_combo"):
                    self.read_mode_combo.setVisible(False)
                if hasattr(self, "read_btn"):
                    self.read_btn.setVisible(True)
                    self.read_btn.setEnabled(True)
                if hasattr(self, "zero_calibrate_btn"):
                    self.zero_calibrate_btn.setVisible(True)
            else:
                if hasattr(self, "modules_group") and self.modules_group:
                    self.modules_group.setTitle("Active Touch Modules (激活触觉模块)")
                    self.modules_group.setVisible(True)
                hybrid_labels = {
                    0: "手掌 (Palm)",
                    1: "拇指尖 (Thumb Tip)",
                    2: "拇指指腹 (Thumb Pad)",
                    3: "食指尖 (Index Tip)",
                    4: "食指指腹 (Index Pad)",
                    5: "中指尖 (Middle Tip)",
                    6: "中指指腹 (Middle Pad)",
                    7: "无名指尖 (Ring Tip)",
                    8: "无名指指腹 (Ring Pad)",
                    9: "小指尖 (Pinky Tip)",
                    10: "小指指腹 (Pinky Pad)",
                }
                for i, (cb, item) in enumerate(zip(self.module_checks, self.module_info)):
                    mod_id, name_en, name_zh, _, _ = item
                    cb.setText(
                        hybrid_labels[mod_id]
                        if self.is_hybrid
                        else f"{name_zh} ({name_en})"
                    )
                    cb.setVisible(True)
                    cb.setEnabled(True)
                if hasattr(self, "ctrl_container") and self.ctrl_container:
                    self.ctrl_container.setVisible(True)
                if hasattr(self, "read_mode_label"):
                    self.read_mode_label.setVisible(self.has_mt_touch)
                if hasattr(self, "read_mode_combo"):
                    self.read_mode_combo.setVisible(self.has_mt_touch)
                if hasattr(self, "zero_calibrate_btn"):
                    self.zero_calibrate_btn.setVisible(True)

            if hasattr(self, "layout_combo") and self.layout_combo is not None:
                self.layout_combo.blockSignals(True)
                if self.is_hybrid:
                    if self.has_mt_touch:
                        self.layout_combo.setCurrentIndex(1)
                    elif self.has_mx_touch:
                        self.layout_combo.setCurrentIndex(2)
                elif self.has_hp_touch:
                    self.layout_combo.setCurrentIndex(3)
                elif self.has_mt_touch:
                    self.layout_combo.setCurrentIndex(4)
                elif self.has_mx_touch:
                    self.layout_combo.setCurrentIndex(5)
                else:
                    self.layout_combo.setCurrentIndex(0)
                self.layout_combo.setEnabled(self._touch_layout_override_supported)
                self.layout_combo.blockSignals(False)

            if hasattr(self, "read_mode_combo") and self.read_mode_combo is not None:
                self.read_mode_combo.blockSignals(True)
                self.read_mode_combo.setCurrentIndex(0)
                self.read_mode_combo.setEnabled(self.has_mt_touch)
                self.read_mode_combo.blockSignals(False)

            if hasattr(self, "value_mode_combo") and self.value_mode_combo is not None:
                self._populate_value_mode_combo(
                    self.value_mode_combo,
                    self.has_mt_touch,
                    self.has_mx_touch,
                    self._global_value_mode,
                )
                self.value_mode_combo.setEnabled(self.has_mt_touch or self.has_mx_touch)
            if not self.has_mx_touch:
                self.tabs.setCurrentIndex(0)
            self._update_zero_button_texts()
            if hasattr(self, "zero_cancel_btn") and self.zero_cancel_btn:
                self.zero_cancel_btn.setText(
                    tr("btn_touch_zero_cancel")
                    if tr("btn_touch_zero_cancel") != "btn_touch_zero_cancel"
                    else "Cancel Tare"
                )
            self._update_zero_buttons(True)
            self._update_mx_read_buttons(True)
            self._rebuild_status_cards()
            self._rebuild_detail_tabs()
            await self._fetch_all_settings()
            self.update_texts()
            self.touch_layout_updated.emit(layout)
        except Exception as e:
            logger.error(f"Failed to read touch layout: {e}")

    def _read_touch_layout(self):
        if not self.device:
            return
        run_async(self._fetch_touch_layout)

    def _read_mx_settings(self):
        if not self.device or not self.has_mx_touch:
            return

        async def fetch():
            await self._fetch_mx_settings()

        run_async(fetch)

    def _read_mx_module_sns(self):
        if not self.device:
            return

        async def fetch():
            await self._fetch_mx_module_sns()

        run_async(fetch)

    def _read_mx_point_counts(self):
        if not self.device or not self.has_mx_touch:
            return

        async def fetch():
            await self._fetch_mx_point_counts(rebuild_tabs=True)

        run_async(fetch)

    def _read_mx_output_mode(self):
        if not self.device or not (self.has_mt_touch or self.has_mx_touch):
            return

        async def fetch():
            await self._fetch_mx_output_mode()

        run_async(fetch)

    def _read_mx_tare_status(self):
        if not self.device or not self.has_mx_touch:
            return

        async def fetch():
            await self._fetch_mx_tare_statuses()

        run_async(fetch)

    async def _fetch_all_settings(self):
        if self.has_mt_touch:
            try:
                mode = await self.device.get_touch_read_mode(self.slave_id)
                if hasattr(self, "read_mode_combo") and self.read_mode_combo is not None:
                    self.read_mode_combo.blockSignals(True)
                    self.read_mode_combo.setCurrentIndex(1 if int(mode) == 1 else 0)
                    self.read_mode_combo.blockSignals(False)
                self._refresh_detail_chart_units()
            except Exception as e:
                logger.error(f"Failed to read mt_* touch read mode: {e}")

        if self.has_mt_touch or self.has_mx_touch:
            await self._fetch_mx_output_mode()

        try:
            bits = await self.device.get_all_touch_modules_enabled(self.slave_id)
            logger.info(f"Fetched touch modules enabled bitmask: {bin(bits)}")
            if self.has_hp_touch and not self.is_hybrid:
                for i, cb in enumerate(self.module_checks[:5]):
                    is_on = bool((bits >> i) & 1)
                    cb.blockSignals(True)
                    cb.setChecked(is_on)
                    cb.blockSignals(False)
            else:
                for cb, item in zip(self.module_checks, self.module_info):
                    mod_id = item[0]
                    is_on = bool((bits >> mod_id) & 1)
                    cb.blockSignals(True)
                    cb.setChecked(is_on)
                    cb.blockSignals(False)
        except Exception as e:
            logger.error(f"Failed to read touch modules enabled status: {e}")

    async def _fetch_mx_module_sns(self):
        try:
            if hasattr(self.device, "get_touch_module_serial_numbers"):
                raw_sns = await self.device.get_touch_module_serial_numbers(self.slave_id)
                if self.has_mx_touch:
                    self.mx_module_sns = self._mx_values_by_public_module_id(
                        [sn if sn else "" for sn in raw_sns], ""
                    )
                else:
                    self.mx_module_sns = [sn if sn else "" for sn in raw_sns]
                logger.info(f"Touch module SNs: {self.mx_module_sns}")
        except Exception as e:
            logger.error(f"Failed to read mx_* touch module SNs: {e}")

    async def _fetch_mx_point_counts(self, rebuild_tabs=False):
        try:
            raw_counts = []
            if hasattr(self.device, "get_touch_module_point_counts"):
                raw_counts = await self.device.get_touch_module_point_counts(self.slave_id)
                if not raw_counts or not all(count > 0 for count in raw_counts):
                    raise RuntimeError(
                        "mx_* touch point counts must contain one positive value per mx_* module"
                    )
                self.mx_point_counts = self._mx_values_by_public_module_id(
                    raw_counts, 0
                )
                self._mx_frame_counts_synced = True
                logger.info(f"mx_* touch point counts: {self.mx_point_counts}")
                if rebuild_tabs:
                    self._rebuild_status_cards()
                    self._rebuild_detail_tabs()
                    self._refresh_detail_chart_units()
            return raw_counts
        except Exception as e:
            logger.error(f"Failed to read mx_* touch point counts: {e}")
            return []

    async def _fetch_mx_output_mode(self):
        try:
            if hasattr(self.device, "get_touch_value_mode"):
                mode = await self.device.get_touch_value_mode(self.slave_id)
                mode_value = int(mode)
                logger.info(
                    f"Touch value mode: {mode_value} "
                    "(0=ADC, 2=Force)"
                )
                self._global_value_mode = mode_value
                self.mx_modes = [mode_value] * 11
                self._populate_value_mode_combo(
                    self.value_mode_combo,
                    self.has_mt_touch,
                    self.has_mx_touch,
                    mode_value,
                )
                for module in list(
                    getattr(self._active_touch_layout, "modules", []) or []
                ):
                    module_id = int(getattr(module, "module_id", -1))
                    combo = self.findChild(QComboBox, f"mode_{module_id}")
                    if combo is None:
                        continue
                    combo.blockSignals(True)
                    combo_index = combo.findData(mode_value)
                    if combo_index >= 0:
                        combo.setCurrentIndex(combo_index)
                    combo.blockSignals(False)
                self._refresh_detail_chart_units()
                if self.has_mx_touch:
                    await self._refresh_active_tab_mx_modes()
        except Exception as e:
            logger.error(f"Failed to read mx_* touch value mode: {e}")

    async def _fetch_mx_tare_statuses(self):
        try:
            if hasattr(self.device, "get_touch_tare_status"):
                status = await self.device.get_touch_tare_status(self.slave_id)
                logger.info(f"mx_* touch tare status: {int(status)}")

            # Read all 11 modules' tare statuses in one Modbus pass
            if hasattr(self.device, "get_touch_module_tare_statuses"):
                statuses = await self.device.get_touch_module_tare_statuses(self.slave_id)
                for mod_idx, status_val in enumerate(statuses):
                    if status_val is None:
                        continue
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
            logger.error(f"Failed to read mx_* touch tare status: {e}")

    async def _fetch_mx_settings(self):
        try:
            await self._fetch_mx_module_sns()
            await self._fetch_mx_point_counts(rebuild_tabs=True)
            await self._fetch_mx_output_mode()
            await self._fetch_mx_tare_statuses()

            # Refresh active tab modes to keep UI dropdowns in sync immediately
            await self._refresh_active_tab_mx_modes()
        except Exception as e:
            logger.error(f"Failed to read mx_* touch settings: {e}")

    def set_device(self, device, slave_id, device_info=None, shared_data=None):
        self.device = device
        self.slave_id = slave_id
        resolved_device_info = device_info or getattr(shared_data, "device_info", None)
        self._hand_side = getattr(resolved_device_info, "hand_side", None)
        self.mx_modes = [TOUCH_VALUE_MODE_ADC] * 11
        self._mx_frame_counts_synced = False
        self.has_hp_touch = False
        self.has_mx_touch = False
        self.has_mt_touch = False
        self.is_hybrid = False
        self._active_touch_layout = None
        self._detected_touch_layout = None
        self._global_value_mode = TOUCH_VALUE_MODE_ADC
        self._touch_layout_override_supported = bool(
            getattr(device, "supports_touch_layout_override", False)
            or getattr(device, "is_mock", False)
        )
        # Enable controls
        if hasattr(self, "layout_combo") and self.layout_combo is not None:
            self.layout_combo.setEnabled(self._touch_layout_override_supported)
        if hasattr(self, "read_mode_combo") and self.read_mode_combo is not None:
            self.read_mode_combo.setEnabled(True)
        if hasattr(self, "value_mode_combo") and self.value_mode_combo is not None:
            self.value_mode_combo.setEnabled(True)
        if hasattr(self, "read_btn") and self.read_btn is not None:
            self.read_btn.setEnabled(True)
        self.snapshot_btn.setEnabled(True)
        self.enable_all_btn.setEnabled(True)
        self.disable_all_btn.setEnabled(True)
        self._update_mx_read_buttons(False)
        self._update_zero_buttons(True)
        for cb in self.module_checks:
            cb.setEnabled(True)
        self._read_touch_layout()

    def clear_device(self):
        self.device = None
        self._hand_side = None
        self.has_hp_touch = False
        self.is_hybrid = False
        self.has_mx_touch = False
        self.has_mt_touch = False
        self._active_touch_layout = None
        self._detected_touch_layout = None
        self._global_value_mode = TOUCH_VALUE_MODE_ADC
        self._touch_layout_override_supported = False
        self.update_fps(0.0)
        if hasattr(self, "layout_combo") and self.layout_combo is not None:
            self.layout_combo.setEnabled(False)
        if hasattr(self, "read_mode_combo") and self.read_mode_combo is not None:
            self.read_mode_combo.setEnabled(False)
        if hasattr(self, "value_mode_combo") and self.value_mode_combo is not None:
            self.value_mode_combo.setEnabled(False)
        if hasattr(self, "read_btn") and self.read_btn is not None:
            self.read_btn.setEnabled(False)
        self.snapshot_btn.setEnabled(False)
        self.enable_all_btn.setEnabled(False)
        self.disable_all_btn.setEnabled(False)
        self._update_mx_read_buttons(False)
        self._update_zero_buttons(False)
        for cb in self.module_checks:
            cb.setEnabled(False)
            cb.setChecked(False)
        self._update_zero_button_texts()
        self.zero_cancel_btn.setText(
            tr("btn_touch_zero_cancel")
            if tr("btn_touch_zero_cancel") != "btn_touch_zero_cancel"
            else "Cancel Tare"
        )
        self._rebuild_status_cards()
        self._rebuild_detail_tabs()
