"""Motor Control Panel Revo3 - Revo3 (21 motors, float values)

Revo3 has 21 motors (motor_id 0~20) with float-based control:
  - Position: degrees (float)
  - Velocity: float
  - Current: mA (float)
  - MIT: impedance control (position + velocity + current + Kp + Kd per motor)

Layout: mode selector switches between motor-level control views.
"""

import asyncio
import inspect
import sys
import threading
import time
from pathlib import Path
from typing import Optional, TYPE_CHECKING
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox,
    QSlider, QDoubleSpinBox, QSpinBox, QPushButton, QLabel, QComboBox, QGridLayout,
    QFrame, QSizePolicy, QScrollArea, QStackedWidget
)
from PySide6.QtCore import Qt, QTimer, Signal

from .i18n import tr
from .styles import COLORS, is_dark_mode

# Add parent directory to path for SDK import
sys.path.insert(0, str(Path(__file__).parent.parent))
from common_imports import sdk, logger

if TYPE_CHECKING:
    from .shared_data import SharedDataManager

# Import constants from constants.py
from .constants import REVO3_ULTRA_JOINT_COUNT

REVO3_FINGER_COUNT = 5
SERVO_DRAG_INTERVAL_MS = 15
SERVO_DRAG_DEFAULT_KP = 2.0
SERVO_DRAG_DEFAULT_KD = 0.25
SERVO_DRAG_DEFAULT_VEL_CAP_RPM = 60.0
SERVO_DRAG_FILTER_MODE = 0
SERVO_DRAG_OMEGA = 35.0
SERVO_DRAG_IDLE_TIMEOUT_MS = 300
SERVO_DRAG_KEEPALIVE_MS = 100
COLLISION_UI_FAST_POLL_MS = 50
COLLISION_UI_IDLE_POLL_MS = 500
COLLISION_GUI_CACHE_MS = 80
COLLISION_GUI_AUTO_CLEAR_MS = 1000
COLLISION_GUI_DEFAULT_POSITION_ERROR_DEG = 25.0
COLLISION_GUI_DEFAULT_CURRENT_MA = 500.0
MOTOR_ERROR_DEBUG_LOG_INTERVAL_S = 1.0
FINGER_STATE_LOG_INTERVAL_S = 1.0
GUI_STALL_BLOCK_CONSECUTIVE_SAMPLES = 3
COLLISION_SOURCE_ITEMS = [
    ("collision_src_hardware", "HardwareOnly"),
    ("collision_src_hybrid", "Hybrid"),
    ("collision_src_software", "SoftwareOnly"),
]
COLLISION_STRATEGY_ITEMS = [
    ("collision_strat_softstop", "SoftStop"),
    ("collision_strat_zeroforce", "ZeroForce"),
    ("collision_strat_holdactual", "HoldActualPosition"),
]

# Finger -> motor_id mapping (top-to-bottom order per finger)
REVO3_FINGER_MOTORS = {
    "Thumb":  [18, 17, 16, 19, 20],  # 5 DOF (top-down: 18,17,16 + differential 19,20)
    "Index":  [15, 14, 13, 12],      # 4 DOF (top-down)
    "Middle": [11, 10, 9, 8],        # 4 DOF (top-down)
    "Ring":   [7, 6, 5, 4],          # 4 DOF (top-down)
    "Pinky":  [3, 2, 1, 0],          # 4 DOF (top-down)
}

MOTOR_FAULT_BITS = {
    0: "Over Current",
    1: "Over Voltage",
    2: "Under Voltage",
    3: "Over Temp",
    4: "Current Surge",
    8: "Stall",
}

FINGER_STATE_STYLE_OK = "color: white; background-color: #27ae60; border-radius: 3px; font-size: 11px; font-weight: bold; padding: 2px 6px;"
FINGER_STATE_STYLE_STALL = "color: #1f2933; background-color: #facc15; border-radius: 3px; font-size: 11px; font-weight: bold; padding: 2px 6px;"
FINGER_STATE_STYLE_GUARD = "color: white; background-color: #8b5cf6; border-radius: 3px; font-size: 11px; font-weight: bold; padding: 2px 6px;"
FINGER_STATE_STYLE_COLLISION = "color: white; background-color: #dc2626; border-radius: 3px; font-size: 11px; font-weight: bold; padding: 2px 6px;"
FINGER_STATE_STYLE_ERROR = "color: white; background-color: #f97316; border-radius: 3px; font-size: 11px; font-weight: bold; padding: 2px 6px;"
DIAG_COLOR_OK = "#27ae60"
DIAG_COLOR_STALL = "#facc15"
DIAG_COLOR_GUARD = "#8b5cf6"
DIAG_COLOR_WARN = "#f97316"
DIAG_COLOR_ERROR = "#dc2626"

def decode_motor_fault_code(err_val) -> list:
    """Decode a motor fault-code bitmask into fault names."""
    if err_val == 0:
        return []
    errs = []
    for bit, name in MOTOR_FAULT_BITS.items():
        if (err_val & (1 << bit)) != 0:
            errs.append(name)
    # Check for unknown bits
    known_mask = sum(1 << b for b in MOTOR_FAULT_BITS)
    if (err_val & ~known_mask) != 0:
        errs.append(f"Unknown(0x{err_val:04X})")
    return errs

def build_finger_state_text(motor_ids, active_joints=None, blocked_joints=None, online=None, temps=None, errors=None, dragging_joints=None, is_connected=True):
    if not is_connected:
        return "", "background-color: transparent;", ""
    active_joints = active_joints or set()
    blocked_joints = blocked_joints or set()
    dragging_joints = dragging_joints or set()
    errors = errors or []

    dragging = []
    collisions = []
    stall_guards = []
    stalls = []
    other_errors = []
    offline = []
    details = []

    for mid in motor_ids:
        label = f"M{mid:02d}"
        if mid in dragging_joints:
            dragging.append(label)
            details.append(f"{label}: Dragging")

        if mid in active_joints:
            collisions.append(label)
            details.append(f"{label}: Collision")
        if mid in blocked_joints:
            stall_guards.append(label)
            details.append(f"{label}: Stall guard")

        if online is not None and (online & (1 << mid)) == 0:
            offline.append(label)
            details.append(f"{label}: Offline")

        err_val = errors[mid] if mid < len(errors) else 0
        err_names = decode_motor_fault_code(err_val)
        if "Stall" in err_names:
            stalls.append(label)
            details.append(f"{label}: Stall")
        remaining_errors = [name for name in err_names if name != "Stall"]
        if remaining_errors:
            other_errors.append(label)
            details.append(f"{label}: {' + '.join(remaining_errors)}")

    parts = []
    if dragging:
        parts.append("Drag: " + ", ".join(dragging))
    if collisions:
        parts.append("Collision: " + ", ".join(collisions))
    if stall_guards:
        parts.append("Stall guard: " + ", ".join(stall_guards))
    if stalls:
        parts.append("Stall: " + ", ".join(stalls))
    if other_errors:
        parts.append("Error: " + ", ".join(other_errors))
    if offline:
        parts.append("Offline: " + ", ".join(offline))

    if not parts:
        return "OK", FINGER_STATE_STYLE_OK, "OK"
    if collisions:
        style = FINGER_STATE_STYLE_COLLISION
    elif stalls:
        style = FINGER_STATE_STYLE_STALL
    elif stall_guards:
        style = FINGER_STATE_STYLE_GUARD
    elif other_errors or offline:
        style = FINGER_STATE_STYLE_ERROR
    else:
        style = FINGER_STATE_STYLE_OK
    return " | ".join(parts), style, "\n".join(details)

def _format_motor_labels(motor_ids):
    return ", ".join(f"M{mid:02d}" for mid in sorted(motor_ids))

def motor_diag_style(color, text_color="white"):
    return f"color: {text_color}; background-color: {color}; border-radius: 3px; font-size: 9px; padding: 1px;"

def motor_diag_color_and_text(temp, err_val, collision_active=False, stall_guard_active=False):
    if collision_active:
        return DIAG_COLOR_ERROR, "white", "!", ["Collision"]
    if stall_guard_active:
        return DIAG_COLOR_GUARD, "white", "G", ["Stall Guard"]
    err_names = decode_motor_fault_code(err_val)
    if err_names:
        if "Stall" in err_names:
            return DIAG_COLOR_STALL, "#1f2933", "⚠", err_names
        return DIAG_COLOR_WARN, "white", "⚠", err_names
    if temp >= 60:
        return DIAG_COLOR_WARN, "white", f"{int(temp)}°", err_names
    if temp >= 45:
        return DIAG_COLOR_WARN, "white", f"{int(temp)}°", err_names
    return DIAG_COLOR_OK, "white", f"{int(temp)}°", err_names

REVO3_FINGER_NAMES = ["Thumb", "Index", "Middle", "Ring", "Pinky"]

def get_revo3_finger_names():
    """Get active finger names based on protocol."""
    return ["Thumb", "Index", "Middle", "Ring", "Pinky"]

def get_revo3_finger_motors():
    """Get active finger-motor mapping based on protocol."""
    return REVO3_FINGER_MOTORS

def get_revo3_motor_count():
    """Get motor/joint count based on protocol."""
    return REVO3_ULTRA_JOINT_COUNT

# Control modes
MODE_POSITION = 0
MODE_CURRENT = 1
MODE_IMPEDANCE = 2
MODE_DAMPING = 3
MODE_MIT = 4
MODE_TRAJECTORY = 5

# Per-motor position ranges (degrees) based on joint specs
# Pinky  (M0~M3):  Abd [-15,15], MCP [0,85], PIP [0,85], DIP [0,85]
# Ring   (M4~M7):  Abd [-15,15], MCP [0,85], PIP [0,85], DIP [0,85]
# Middle (M8~M11): Abd [-15,15], MCP [0,85], PIP [0,85], DIP [0,85]
# Index  (M12~M15):Abd [-15,15], MCP [0,85], PIP [0,85], DIP [0,85]
# Thumb  (M16~M20):CMC-Rot [0,50], MCP [0,85], IP [0,85], CMC-Abd [0,110], CMC-Flex [0,115]
MOTOR_POSITION_RANGES = {
    # Pinky: [0]=Abd, [1]=MCP, [2]=PIP, [3]=DIP
    0:  (-15.0, 15.0),   # Pinky Abduction
    1:  (0.0, 85.0),     # Pinky MCP
    2:  (0.0, 85.0),     # Pinky PIP
    3:  (0.0, 85.0),     # Pinky DIP
    # Ring: [4]=Abd, [5]=MCP, [6]=PIP, [7]=DIP
    4:  (-15.0, 15.0),   # Ring Abduction
    5:  (0.0, 85.0),     # Ring MCP
    6:  (0.0, 85.0),     # Ring PIP
    7:  (0.0, 85.0),     # Ring DIP
    # Middle: [8]=Abd, [9]=MCP, [10]=PIP, [11]=DIP
    8:  (-15.0, 15.0),   # Middle Abduction
    9:  (0.0, 85.0),     # Middle MCP
    10: (0.0, 85.0),     # Middle PIP
    11: (0.0, 85.0),     # Middle DIP
    # Index: [12]=Abd, [13]=MCP, [14]=PIP, [15]=DIP
    12: (-15.0, 15.0),   # Index Abduction
    13: (0.0, 85.0),     # Index MCP
    14: (0.0, 85.0),     # Index PIP
    15: (0.0, 85.0),     # Index DIP
    # Thumb: [16]=CMC-Rot, [17]=MCP, [18]=IP, [19]=CMC-Abd(diff), [20]=CMC-Flex(diff)
    16: (0.0, 50.0),     # Thumb CMC Rotation
    17: (0.0, 85.0),     # Thumb MCP
    18: (0.0, 85.0),     # Thumb IP
    19: (0.0, 110.0),    # Thumb CMC Abduction (differential)
    20: (0.0, 115.0),    # Thumb CMC Flexion (differential)
}

# Joint labels for display (motor_id -> label)
MOTOR_JOINT_LABELS = {
    0: "Abd", 1: "MCP", 2: "PIP", 3: "DIP",       # Pinky
    4: "Abd", 5: "MCP", 6: "PIP", 7: "DIP",       # Ring
    8: "Abd", 9: "MCP", 10: "PIP", 11: "DIP",     # Middle
    12: "Abd", 13: "MCP", 14: "PIP", 15: "DIP",   # Index
    16: "Rot", 17: "MCP", 18: "IP",                # Thumb
    19: "Abd", 20: "Flex",                          # Thumb CMC (diff)
}

def get_motor_position_range(motor_id):
    """Get position range for a specific motor based on product joint specs."""
    return MOTOR_POSITION_RANGES.get(motor_id, (-90.0, 90.0))

# Joint type classification: flexion joints participate in open/close,
# abduction/rotation/wrist joints stay neutral.
# "flexion" joints: MCP, PIP, DIP, IP, Flex
# "neutral" joints: Abd, Rot, Wrist
FLEXION_MOTOR_IDS = {
    1, 2, 3,          # Pinky MCP, PIP, DIP
    5, 6, 7,          # Ring MCP, PIP, DIP
    9, 10, 11,        # Middle MCP, PIP, DIP
    13, 14, 15,       # Index MCP, PIP, DIP
    17, 18, 20,       # Thumb MCP, IP, CMC-Flex(diff)
}

def get_motor_open_position(motor_id):
    """Get 'open hand' target for a motor. Flexion → 0°, others → 0° (neutral)."""
    return 0.0

def get_motor_close_position(motor_id):
    """Get 'close hand' target for a motor. Flexion → max range, others → 0° (neutral)."""
    if motor_id in FLEXION_MOTOR_IDS:
        _, max_pos = get_motor_position_range(motor_id)
        return max_pos
    return 0.0  # Abduction, rotation, wrist → neutral

# Value ranges per mode (user-facing, used as default; position mode overrides per motor)
MODE_RANGES = {
    MODE_POSITION:  (-30.0, 110.0, 1.0, "°"),  # envelope of all motor ranges
    MODE_TRAJECTORY:(-30.0, 110.0, 1.0, "°"),  # same as position
    MODE_CURRENT:   (0.0, 3.0, 0.1, "A"),
    MODE_IMPEDANCE: (0.0, 10.0, 0.1, ""),    # impedance coefficient (Kp), 0~10.0
    MODE_DAMPING:   (0.0, 10.0, 0.1, ""),    # damping coefficient (Kd), 0~10.0
}

# MIT parameter ranges (position uses per-motor range via get_motor_position_range)
MIT_POS_RANGE = (-30.0, 110.0, 1.0)  # envelope range for UI default
MIT_VEL_RANGE = (0.0, 110.0, 1.0)
MIT_CUR_RANGE = (0.0, 3.0, 0.1)
MIT_KP_RANGE = (0.0, 5.0, 0.1)
MIT_KD_RANGE = (0.0, 5.0, 0.1)

def enum_display_name(value) -> str:
    if value is None:
        return "--"
    if hasattr(value, "name"):
        return value.name
    text = str(value)
    return text.split(".")[-1] if text else "--"


def touch_layout_display_name(device) -> str:
    layout = getattr(getattr(getattr(device, "hand", None), "touch", None), "layout", None)
    modules = list(getattr(layout, "modules", []) or [])
    if not modules:
        return "--"
    layout_ids = sorted({str(getattr(module, "layout_id", "")) for module in modules})
    layout_ids = [layout_id for layout_id in layout_ids if layout_id]
    if not layout_ids:
        return "--"
    if len(layout_ids) == 1:
        return layout_ids[0]
    return f"{layout_ids[0]} (+{len(layout_ids) - 1})"


class DeviceInfoPanel(QWidget):
    """Device info summary panel for the empty grid slot."""
    def __init__(self):
        super().__init__()
        vl = QVBoxLayout()
        vl.setContentsMargins(4, 8, 4, 4)
        vl.setSpacing(12)
        self.setLayout(vl)

        self.group_dev = QGroupBox(tr("device_info"))
        self.group_motor = QGroupBox(tr("v3_motor_status_info"))

        is_dark = is_dark_mode()
        bg_dev = "#2d3748" if is_dark else "#f8f9fa"
        bg_motor = "#2d3748" if is_dark else "#fdfbf7"
        text_color = "#ecf0f1" if is_dark else "#2c3e50"

        style_dev = f"""
            QGroupBox {{
                font-weight: bold;
                background-color: {bg_dev};
                border: 2px solid #5D9CEC;
                border-radius: 6px;
                margin-top: 8px;
                padding: 10px 8px 8px 8px;
                color: {text_color};
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: 12px;
                padding: 0 6px;
                background-color: transparent;
                color: #5D9CEC;
                font-size: 14px;
            }}
            QLabel {{ font-size: 14px; color: {text_color}; }}
        """
        self.group_dev.setStyleSheet(style_dev)
        style_motor = style_dev.replace("#5D9CEC", "#e67e22").replace(bg_dev, bg_motor)
        self.group_motor.setStyleSheet(style_motor)
        self._info_values = {
            "model": "--",
            "hw": "--",
            "fw": "--",
            "sn": "--",
            "sku": "--",
            "touch_layout": "--",
        }

        # Device info UI
        l_dev = QVBoxLayout()
        self.lbl_type = QLabel(f"{tr('v3_model')}: --")
        self.lbl_hw = QLabel(f"{tr('v3_hw')}: --")
        self.lbl_fw = QLabel(f"{tr('v3_fw')}: --")
        self.lbl_sn = QLabel(f"{tr('v3_sn')}: --")
        self.lbl_sku = QLabel(f"{tr('v3_sku')}: --")
        self.lbl_touch_layout = QLabel(f"{tr('v3_touch_layout')}: --")
        self.lbl_online = QLabel(f"{tr('v3_online')}: --")
        for lbl in [
            self.lbl_type,
            self.lbl_hw,
            self.lbl_fw,
            self.lbl_sn,
            self.lbl_sku,
            self.lbl_touch_layout,
            self.lbl_online,
        ]:
            l_dev.addWidget(lbl)
        self.group_dev.setLayout(l_dev)

        # Motor status UI
        l_motor = QVBoxLayout()
        self.lbl_temp = QLabel(f"{tr('v3_temp')}: --")
        self.lbl_errors = QLabel(f"{tr('v3_errors')}: --")
        self.lbl_last_update = QLabel("")
        self.lbl_last_update.setStyleSheet("color: #999; font-size: 10px;")
        for lbl in [self.lbl_temp, self.lbl_errors, self.lbl_last_update]:
            l_motor.addWidget(lbl)
        self.group_motor.setLayout(l_motor)

        vl.addWidget(self.group_dev)
        vl.addWidget(self.group_motor)
        vl.addStretch()

    def update_info(
        self,
        hw=None,
        fw=None,
        sn=None,
        online=None,
        temps=None,
        errors=None,
        model=None,
        sku=None,
        touch_layout=None,
    ):
        """Update all device info labels."""
        import time
        if model is not None:
            self._info_values["model"] = enum_display_name(model)
        if hw is not None:
            self._info_values["hw"] = hw
        if fw is not None:
            self._info_values["fw"] = fw
        if sn is not None:
            self._info_values["sn"] = sn if sn else "(empty)"
        if sku is not None:
            self._info_values["sku"] = enum_display_name(sku)
        if touch_layout is not None:
            self._info_values["touch_layout"] = touch_layout
        self._refresh_static_info_labels()
        if online is not None:
            total = 21
            cnt = bin(online).count('1')
            offline = [f"M{i}" for i in range(total) if not (online & (1 << i))]
            if offline:
                self.lbl_online.setText(f"{tr('v3_online')}: ⚠ {cnt}/{total}")
                self.lbl_online.setToolTip(f"{tr('v3_offline')}: {', '.join(offline)}")
                self.lbl_online.setStyleSheet("color: #e74c3c; font-weight: bold;")
            else:
                self.lbl_online.setText(f"{tr('v3_online')}: ✅ {cnt}/{total}")
                self.lbl_online.setToolTip("")
                self.lbl_online.setStyleSheet("")
        if temps is not None and len(temps) >= 21:
            max_t = max(temps[:21])
            max_i = temps[:21].index(max_t)
            color = "#e74c3c" if max_t >= 60 else ("#e67e22" if max_t >= 45 else "")
            self.lbl_temp.setText(f"{tr('v3_temp')}: {int(max_t)}°C {tr('v3_max_temp')} (M{max_i})")
            self.lbl_temp.setStyleSheet(f"color: {color};" if color else "")
        if errors is not None:
            err_count = sum(1 for e in errors[:21] if e != 0)
            if err_count:
                self.lbl_errors.setText(f"{tr('v3_errors')}: ❌ {err_count}")
                self.lbl_errors.setStyleSheet("color: #e74c3c; font-weight: bold;")
            else:
                self.lbl_errors.setText(f"{tr('v3_errors')}: ✅ {tr('v3_no_errors')}")
                self.lbl_errors.setStyleSheet(f"color: {COLORS['primary']};")
        self.lbl_last_update.setText(f"Updated: {time.strftime('%H:%M:%S')}")

    def clear_info(self):
        """Reset all labels."""
        for lbl in [
            self.lbl_type,
            self.lbl_hw,
            self.lbl_fw,
            self.lbl_sn,
            self.lbl_sku,
            self.lbl_touch_layout,
            self.lbl_online,
            self.lbl_temp,
            self.lbl_errors,
        ]:
            lbl.setText(lbl.text().split(':')[0] + ": --")
            lbl.setStyleSheet("")
        self._info_values = {key: "--" for key in self._info_values}
        self._refresh_static_info_labels()
        self.lbl_last_update.setText("")

    def _refresh_static_info_labels(self):
        self.lbl_type.setText(f"{tr('v3_model')}: {self._info_values['model']}")
        self.lbl_hw.setText(f"{tr('v3_hw')}: {self._info_values['hw']}")
        self.lbl_fw.setText(f"{tr('v3_fw')}: {self._info_values['fw']}")
        self.lbl_sn.setText(f"{tr('v3_sn')}: {self._info_values['sn']}")
        self.lbl_sku.setText(f"{tr('v3_sku')}: {self._info_values['sku']}")
        self.lbl_touch_layout.setText(f"{tr('v3_touch_layout')}: {self._info_values['touch_layout']}")

    def update_texts(self):
        self.group_dev.setTitle(tr("device_info"))
        self.group_motor.setTitle(tr("v3_motor_status_info"))
        self._refresh_static_info_labels()
        # Simplistic approach: if not connected, just reset format, else it updates automatically on next poll
        if "⚠" not in self.lbl_online.text() and "✅" not in self.lbl_online.text():
            self.lbl_online.setText(f"{tr('v3_online')}: --")
        if "max" not in self.lbl_temp.text() and "最高" not in self.lbl_temp.text():
            self.lbl_temp.setText(f"{tr('v3_temp')}: --")
        if "❌" not in self.lbl_errors.text() and "✅" not in self.lbl_errors.text():
            self.lbl_errors.setText(f"{tr('v3_errors')}: --")


class _GuiAsyncRunner:
    """Runs GUI SDK coroutines on one persistent background event loop."""

    def __init__(self):
        self._loop = None
        self._thread = None
        self._ready = threading.Event()
        self._lock = threading.Lock()

    def submit(self, coro_fn):
        self._ensure_started()

        async def _wrapper():
            try:
                result = coro_fn()
                if inspect.isawaitable(result):
                    return await result
                return result
            except Exception as e:
                print(f"[GUI Async Task] Warning/Error: {str(e)}")
                return None

        return asyncio.run_coroutine_threadsafe(_wrapper(), self._loop)

    def _ensure_started(self):
        with self._lock:
            if self._thread and self._thread.is_alive() and self._loop:
                return
            self._ready.clear()
            self._thread = threading.Thread(target=self._run_loop, daemon=True)
            self._thread.start()
        self._ready.wait(timeout=2.0)

    def _run_loop(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._loop = loop
        self._ready.set()
        loop.run_forever()


_gui_async_runner = _GuiAsyncRunner()
_gui_control_runner = _GuiAsyncRunner()


def run_async(coro_fn):
    """Run an SDK coroutine from Qt callbacks without blocking the GUI thread."""
    return _gui_async_runner.submit(coro_fn)


def run_control_async(coro_fn):
    """Run latency-sensitive control coroutines on a dedicated event loop."""
    return _gui_control_runner.submit(coro_fn)


# ============================================================================
# Motor Slider (shared by Position/Current modes)
# ============================================================================

class Revo3MotorSlider(QWidget):
    """Single motor control: slider + spinbox + status label"""

    def __init__(self, motor_id, send_callback):
        super().__init__()
        self.motor_id = motor_id
        self.send_callback = send_callback
        self.run_callback = None
        self._slider_scale = 10
        self.live_update = True
        self.current_mode = MODE_POSITION # 默认是位置模式

        # 轨迹限频控制 (80ms 间隔 / 12.5Hz 刷新率，支持尾部补偿与瞬时物理打断)
        self._last_traj_send_time = 0.0
        self._traj_pending_value = None
        self._traj_throttle_timer = QTimer()
        self._traj_throttle_timer.setSingleShot(True)
        self._traj_throttle_timer.timeout.connect(self._on_traj_throttle_timeout)

        self._setup_ui()

    def _setup_ui(self):
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        self.setLayout(layout)

        joint = MOTOR_JOINT_LABELS.get(self.motor_id, "")
        label_text = f"M{self.motor_id:02d} {joint}" if joint else f"M{self.motor_id:02d}"
        self.id_label = QLabel(label_text)
        self.id_label.setFixedWidth(60)
        self.id_label.setStyleSheet("font-size: 11px; font-weight: bold;")
        layout.addWidget(self.id_label)

        self.diag_label = QLabel("")
        self.diag_label.setFixedWidth(55)
        self.diag_label.setAlignment(Qt.AlignCenter)
        self.diag_label.setStyleSheet("font-size: 11px; border-radius: 3px;")
        layout.addWidget(self.diag_label)

        min_pos, max_pos = get_motor_position_range(self.motor_id)
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(int(min_pos * self._slider_scale), int(max_pos * self._slider_scale))
        self.slider.setTracking(True)
        self.slider.setValue(0)
        self.slider.valueChanged.connect(self._on_slider_changed)
        self.slider.sliderMoved.connect(self._on_slider_moved)
        self.slider.sliderReleased.connect(self._on_slider_released)
        self.slider.sliderPressed.connect(self._on_slider_pressed)
        layout.addWidget(self.slider, 1)

        self.spin = QDoubleSpinBox()
        self.spin.setRange(min_pos, max_pos)
        self.spin.setDecimals(1)
        self.spin.setSingleStep(1.0)
        self.spin.setFixedWidth(85)
        self.spin.valueChanged.connect(self._on_spin_changed)
        self.spin.editingFinished.connect(self._on_spin_editing_finished)
        layout.addWidget(self.spin)

        self.run_btn = QPushButton("▶")
        self.run_btn.setFixedWidth(24)
        self.run_btn.setStyleSheet("font-size: 10px; font-weight: bold; padding: 2px;")
        self.run_btn.setToolTip("Run Trajectory")
        self.run_btn.clicked.connect(self._on_run_clicked)
        self.run_btn.hide()
        layout.addWidget(self.run_btn)

        self.status_label = QLabel("--")
        self.status_label.setFixedWidth(55)
        self.status_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.status_label.setStyleSheet(f"color: {COLORS['primary']}; font-size: 11px;")
        layout.addWidget(self.status_label)

    def set_mode_range(self, min_val, max_val, step, mode=None):
        if mode is not None:
            self.current_mode = mode
        if mode == MODE_POSITION or mode == MODE_TRAJECTORY:
            min_val, max_val = get_motor_position_range(self.motor_id)
        self.slider.blockSignals(True)
        self.spin.blockSignals(True)
        self._slider_scale = 1 if max_val > 1000 else 10
        self.slider.setRange(int(min_val * self._slider_scale), int(max_val * self._slider_scale))
        self.slider.setValue(0)
        self.spin.setRange(min_val, max_val)
        self.spin.setSingleStep(step)
        self.spin.setValue(0.0)
        self.slider.blockSignals(False)
        self.spin.blockSignals(False)

    def _on_slider_changed(self, value):
        float_val = value / self._slider_scale
        self.spin.blockSignals(True)
        self.spin.setValue(float_val)
        self.spin.blockSignals(False)

        if self.current_mode == MODE_TRAJECTORY:
            import time
            now = time.time()
            interval = 0.08 # 80ms interval (12.5Hz) for physical following
            self._traj_pending_value = float_val
            if now - self._last_traj_send_time >= interval:
                self._send_pending_trajectory()
            else:
                rem = interval - (now - self._last_traj_send_time)
                self._traj_throttle_timer.start(int(rem * 1000))
        else:
            if self.live_update and not (self.current_mode == MODE_POSITION and self.slider.isSliderDown()):
                self.send_callback(self.motor_id, float_val)

    def _on_slider_moved(self, value):
        if self.current_mode != MODE_POSITION or not hasattr(self.send_callback, "__self__"):
            return
        owner = self.send_callback.__self__
        float_val = value / self._slider_scale
        if self.motor_id in getattr(owner, "_servo_drag_blocked_until_release", set()):
            return
        collision_active = getattr(owner, "_collision_active", [])
        if self.motor_id < len(collision_active) and collision_active[self.motor_id]:
            return
        if hasattr(owner, "_start_servo_drag") and self.motor_id not in getattr(owner, "_active_servo_drags", set()):
            owner._start_servo_drag(self.motor_id, float_val)
        if hasattr(owner, "_update_servo_drag_target"):
            owner._update_servo_drag_target(self.motor_id, float_val)

    def _on_spin_changed(self, value):
        self.slider.blockSignals(True)
        self.slider.setValue(int(value * self._slider_scale))
        self.slider.blockSignals(False)

        if self.current_mode == MODE_TRAJECTORY:
            import time
            now = time.time()
            interval = 0.08
            self._traj_pending_value = value
            if now - self._last_traj_send_time >= interval:
                self._send_pending_trajectory()
            else:
                rem = interval - (now - self._last_traj_send_time)
                self._traj_throttle_timer.start(int(rem * 1000))
        else:
            if self.live_update:
                self.send_callback(self.motor_id, value)

    def _send_pending_trajectory(self):
        if self.current_mode == MODE_TRAJECTORY and self._traj_pending_value is not None:
            import time
            self._last_traj_send_time = time.time()
            val = self._traj_pending_value
            self._traj_pending_value = None
            self._traj_throttle_timer.stop()
            if self.run_callback:
                self.run_callback(self.motor_id, val)

    def _on_traj_throttle_timeout(self):
        self._send_pending_trajectory()

    def _on_run_clicked(self):
        if self.run_callback:
            self.run_callback(self.motor_id, self.spin.value())

    def _on_slider_pressed(self):
        if self.current_mode == MODE_POSITION and hasattr(self.send_callback, "__self__"):
            owner = self.send_callback.__self__
            collision_active = getattr(owner, "_collision_active", [])
            if (
                self.motor_id in getattr(owner, "_servo_drag_blocked_until_release", set())
                or self.motor_id < len(collision_active) and collision_active[self.motor_id]
            ):
                return
            if hasattr(owner, "_start_servo_drag"):
                owner._start_servo_drag(self.motor_id, self.spin.value())

    def _on_slider_released(self):
        slider_value = self.slider.value() / self._slider_scale
        self.spin.blockSignals(True)
        self.spin.setValue(slider_value)
        self.spin.blockSignals(False)
        if self.current_mode == MODE_POSITION and hasattr(self.send_callback, "__self__"):
            owner = self.send_callback.__self__
            was_blocked = self.motor_id in getattr(owner, "_servo_drag_blocked_until_release", set())
            collision_active = getattr(owner, "_collision_active", [])
            is_collision_active = self.motor_id < len(collision_active) and collision_active[self.motor_id]
            if hasattr(owner, "_release_servo_drag_block"):
                owner._release_servo_drag_block(self.motor_id)
            if was_blocked or is_collision_active:
                if was_blocked and hasattr(owner, "_end_servo_drag_control_priority"):
                    owner._end_servo_drag_control_priority()
                if hasattr(owner, "_update_collision_status_label"):
                    owner._update_collision_status_label()
                if hasattr(owner, "_update_finger_collision_state"):
                    owner._update_finger_collision_state()
                if hasattr(owner, "_update_motor_diagnostic_badges"):
                    owner._update_motor_diagnostic_badges()
                return
            if hasattr(owner, "_stop_servo_drag") and self.motor_id in getattr(owner, "_active_servo_drags", set()):
                owner._stop_servo_drag(self.motor_id, slider_value)
                return

        # Force a terminal absolute target update on mouse release
        if self.run_callback:
            self._traj_throttle_timer.stop()
            self._traj_pending_value = None
            self.run_callback(self.motor_id, slider_value)

    def _on_spin_editing_finished(self):
        if self.current_mode == MODE_POSITION and hasattr(self.send_callback, "__self__"):
            owner = self.send_callback.__self__
            was_blocked = self.motor_id in getattr(owner, "_servo_drag_blocked_until_release", set())
            collision_active = getattr(owner, "_collision_active", [])
            is_collision_active = self.motor_id < len(collision_active) and collision_active[self.motor_id]
            if hasattr(owner, "_release_servo_drag_block"):
                owner._release_servo_drag_block(self.motor_id)
            if was_blocked or is_collision_active:
                if was_blocked and hasattr(owner, "_end_servo_drag_control_priority"):
                    owner._end_servo_drag_control_priority()
                if hasattr(owner, "_update_collision_status_label"):
                    owner._update_collision_status_label()
                if hasattr(owner, "_update_finger_collision_state"):
                    owner._update_finger_collision_state()
                if hasattr(owner, "_update_motor_diagnostic_badges"):
                    owner._update_motor_diagnostic_badges()
                return
            if hasattr(owner, "_stop_servo_drag") and self.motor_id in getattr(owner, "_active_servo_drags", set()):
                owner._stop_servo_drag(self.motor_id, self.spin.value())
                return

        if self.run_callback:
            self._traj_throttle_timer.stop()
            self._traj_pending_value = None
            self.run_callback(self.motor_id, self.spin.value())

    def update_diagnostics(self, temp, is_online, err_val=0, collision_active=False, stall_guard_active=False):
        if not is_online:
            self.diag_label.setText("OFF")
            self.diag_label.setStyleSheet(motor_diag_style(DIAG_COLOR_WARN))
            self.diag_label.setToolTip('<span style="font-size:14px;">Offline</span>')
        else:
            color, text_color, text, real_errs = motor_diag_color_and_text(temp, err_val, collision_active, stall_guard_active)
            self.diag_label.setText(text)
            self.diag_label.setStyleSheet(motor_diag_style(color, text_color))

            if not real_errs:
                self.diag_label.setToolTip(f'<span style="font-size:14px;">Temperature: {temp}°C</span>')
            else:
                err_text = ', '.join(real_errs)
                self.diag_label.setToolTip(f'<span style="font-size:14px;">Temperature: {temp}°C<br/>⚠ {err_text}</span>')

    def set_value_silent(self, value):
        self.slider.blockSignals(True)
        self.spin.blockSignals(True)
        self.slider.setValue(int(value * self._slider_scale))
        self.spin.setValue(value)
        self.slider.blockSignals(False)
        self.spin.blockSignals(False)

    def update_status(self, value):
        self.status_label.setText(f"{value:.1f}")


# ============================================================================
# Finger Group (shared by Position/Current modes)
# ============================================================================

class FingerGroup(QGroupBox):
    """A finger group containing multiple motor sliders"""

    def __init__(self, finger_name, motor_ids, send_callback, finger_action_callback=None):
        super().__init__(finger_name)
        self.finger_name = finger_name
        self.motor_ids = motor_ids
        self.motor_sliders = {}
        self.finger_action_callback = finger_action_callback
        self.run_finger_callback = None
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        layout = QVBoxLayout()
        layout.setSpacing(4)
        layout.setContentsMargins(8, 16, 8, 8)
        self.setLayout(layout)

        # Header row with Open/Close buttons
        header = QHBoxLayout()
        header.setSpacing(4)
        self.open_btn = QPushButton(tr("btn_open"))
        self.open_btn.setFixedHeight(32)
        self.open_btn.setStyleSheet("font-size: 13px; font-weight: bold; padding: 4px 14px; min-width: 60px;")
        self.open_btn.clicked.connect(self._on_open)
        header.addWidget(self.open_btn)
        self.close_btn = QPushButton(tr("btn_close"))
        self.close_btn.setFixedHeight(32)
        self.close_btn.setStyleSheet("font-size: 13px; font-weight: bold; padding: 4px 14px; min-width: 60px;")
        self.close_btn.clicked.connect(self._on_close)
        header.addWidget(self.close_btn)

        self.run_finger_btn = QPushButton(tr("btn_run_finger"))
        self.run_finger_btn.setFixedHeight(32)
        self.run_finger_btn.setStyleSheet("font-size: 13px; font-weight: bold; padding: 4px 10px;")
        self.run_finger_btn.clicked.connect(self._on_run_finger)
        self.run_finger_btn.hide()
        header.addWidget(self.run_finger_btn)

        header.addStretch()
        self.state_label = QLabel("OK")
        self.state_label.setAlignment(Qt.AlignCenter)
        self.state_label.setFixedHeight(22)
        self.state_label.setMinimumWidth(80)
        self.state_label.setStyleSheet(FINGER_STATE_STYLE_OK)
        header.addWidget(self.state_label)
        layout.addLayout(header)

        for mid in motor_ids:
            slider = Revo3MotorSlider(mid, send_callback)
            self.motor_sliders[mid] = slider
            layout.addWidget(slider)

    def _on_open(self):
        if self.finger_action_callback:
            self.finger_action_callback(self.finger_name, "open")

    def _on_close(self):
        if self.finger_action_callback:
            self.finger_action_callback(self.finger_name, "close")

    def _on_run_finger(self):
        if self.run_finger_callback:
            targets = {mid: slider.spin.value() for mid, slider in self.motor_sliders.items()}
            self.run_finger_callback(self.finger_name, targets)

    def set_mode_range(self, min_val, max_val, step, mode=None):
        for slider in self.motor_sliders.values():
            slider.set_mode_range(min_val, max_val, step, mode)
        # Show Open/Close only in Position mode
        visible = (mode == MODE_POSITION) if mode is not None else True
        self.open_btn.setVisible(visible)
        self.close_btn.setVisible(visible)

    def update_motor_status(self, motor_id, value):
        if motor_id in self.motor_sliders:
            self.motor_sliders[motor_id].update_status(value)

    def update_state(self, active_joints=None, blocked_joints=None, online=None, temps=None, errors=None, dragging_joints=None, is_connected=True):
        text, style, tooltip = build_finger_state_text(
            self.motor_ids, active_joints, blocked_joints, online, temps, errors, dragging_joints, is_connected
        )
        self.state_label.setText(text)
        self.state_label.setStyleSheet(style)
        self.state_label.setToolTip(tooltip)

    def set_all_values(self, value):
        for slider in self.motor_sliders.values():
            slider.set_value_silent(value)
            slider._on_spin_changed(value)


    def update_texts(self):
        self.open_btn.setText(tr("btn_open"))
        self.close_btn.setText(tr("btn_close"))
        self.run_finger_btn.setText(tr("btn_run_finger"))

# ============================================================================
# MIT Motor Row (per motor: position + velocity + current + Kp + Kd)
# ============================================================================

class MitMotorRow(QWidget):
    """Single motor MIT control: 5 spinboxes in a row"""

    def __init__(self, motor_id, send_callback):
        super().__init__()
        self.motor_id = motor_id
        self.send_callback = send_callback
        self._setup_ui()

    def _setup_ui(self):
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        self.setLayout(layout)

        joint = MOTOR_JOINT_LABELS.get(self.motor_id, "")
        label_text = f"M{self.motor_id:02d} {joint}" if joint else f"M{self.motor_id:02d}"
        self.id_label = QLabel(label_text)
        self.id_label.setFixedWidth(60)
        self.id_label.setStyleSheet("font-size: 11px; font-weight: bold;")
        layout.addWidget(self.id_label)

        self.diag_label = QLabel("")
        self.diag_label.setFixedWidth(26)
        self.diag_label.setAlignment(Qt.AlignCenter)
        self.diag_label.setStyleSheet("font-size: 9px;")
        layout.addWidget(self.diag_label)

        min_pos, max_pos = get_motor_position_range(self.motor_id)

        # Position spinbox (per-motor range)
        self.pos_spin = QDoubleSpinBox()
        self.pos_spin.setRange(min_pos, max_pos)
        self.pos_spin.setDecimals(1)
        self.pos_spin.setSingleStep(MIT_POS_RANGE[2])
        self.pos_spin.setPrefix("P:")
        self.pos_spin.setFixedWidth(80)
        self.pos_spin.valueChanged.connect(self._on_changed)
        layout.addWidget(self.pos_spin)

        # Velocity spinbox
        self.vel_spin = QDoubleSpinBox()
        self.vel_spin.setRange(*MIT_VEL_RANGE[:2])
        self.vel_spin.setDecimals(1)
        self.vel_spin.setSingleStep(MIT_VEL_RANGE[2])
        self.vel_spin.setPrefix("V:")
        self.vel_spin.setFixedWidth(80)
        self.vel_spin.valueChanged.connect(self._on_changed)
        layout.addWidget(self.vel_spin)

        # Current spinbox
        self.cur_spin = QDoubleSpinBox()
        self.cur_spin.setRange(*MIT_CUR_RANGE[:2])
        self.cur_spin.setDecimals(2)
        self.cur_spin.setSingleStep(MIT_CUR_RANGE[2])
        self.cur_spin.setPrefix("I:")
        self.cur_spin.setFixedWidth(80)
        self.cur_spin.valueChanged.connect(self._on_changed)
        layout.addWidget(self.cur_spin)

        # Kp spinbox
        self.kp_spin = QDoubleSpinBox()
        self.kp_spin.setRange(*MIT_KP_RANGE[:2])
        self.kp_spin.setDecimals(2)
        self.kp_spin.setSingleStep(MIT_KP_RANGE[2])
        self.kp_spin.setPrefix("Kp:")
        self.kp_spin.setFixedWidth(85)
        self.kp_spin.valueChanged.connect(self._on_changed)
        layout.addWidget(self.kp_spin)

        # Kd spinbox
        self.kd_spin = QDoubleSpinBox()
        self.kd_spin.setRange(*MIT_KD_RANGE[:2])
        self.kd_spin.setDecimals(2)
        self.kd_spin.setSingleStep(MIT_KD_RANGE[2])
        self.kd_spin.setPrefix("Kd:")
        self.kd_spin.setFixedWidth(85)
        self.kd_spin.valueChanged.connect(self._on_changed)
        layout.addWidget(self.kd_spin)

        # Status label
        self.status_label = QLabel("--")
        self.status_label.setFixedWidth(45)
        self.status_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.status_label.setStyleSheet(f"color: {COLORS['primary']}; font-size: 11px;")
        layout.addWidget(self.status_label)

    def _on_changed(self, _value):
        """Send MIT command with all 5 params"""
        params = {
            'position': self.pos_spin.value(),
            'velocity': self.vel_spin.value(),
            'current': self.cur_spin.value(),
            'kp': self.kp_spin.value(),
            'kd': self.kd_spin.value(),
        }
        self.send_callback(self.motor_id, params)

    def set_gains_silent(self, kp, kd):
        self.kp_spin.blockSignals(True)
        self.kd_spin.blockSignals(True)
        self.kp_spin.setValue(kp)
        self.kd_spin.setValue(kd)
        self.kp_spin.blockSignals(False)
        self.kd_spin.blockSignals(False)

    def update_status(self, value):
        self.status_label.setText(f"{value:.1f}")

    def update_diagnostics(self, temp, is_online, err_val=0, collision_active=False, stall_guard_active=False):
        if not is_online:
            self.diag_label.setText("OFF")
            self.diag_label.setStyleSheet(motor_diag_style(DIAG_COLOR_WARN))
            self.diag_label.setToolTip('<span style="font-size:14px;">Offline</span>')
        else:
            color, text_color, text, real_errs = motor_diag_color_and_text(temp, err_val, collision_active, stall_guard_active)
            self.diag_label.setText(text)
            self.diag_label.setStyleSheet(motor_diag_style(color, text_color))

            if not real_errs:
                self.diag_label.setToolTip(f'<span style="font-size:14px;">Temperature: {temp}°C</span>')
            else:
                err_text = ', '.join(real_errs)
                self.diag_label.setToolTip(f'<span style="font-size:14px;">Temperature: {temp}°C<br/>⚠ {err_text}</span>')

    def zero_all(self):
        for spin in [self.pos_spin, self.vel_spin, self.cur_spin, self.kp_spin, self.kd_spin]:
            spin.blockSignals(True)
            spin.setValue(0.0)
            spin.blockSignals(False)


# ============================================================================
# MIT Finger Group
# ============================================================================

class MitFingerGroup(QGroupBox):
    """MIT finger group with 5-param rows per motor"""

    def __init__(self, finger_name, motor_ids, send_callback):
        super().__init__(finger_name)
        self.motor_ids = motor_ids
        self.motor_rows = {}
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        layout = QVBoxLayout()
        layout.setSpacing(4)
        layout.setContentsMargins(8, 16, 8, 8)
        self.setLayout(layout)

        header = QHBoxLayout()
        header.setSpacing(4)
        header.addStretch()
        self.state_label = QLabel("OK")
        self.state_label.setAlignment(Qt.AlignCenter)
        self.state_label.setFixedHeight(22)
        self.state_label.setMinimumWidth(80)
        self.state_label.setStyleSheet(FINGER_STATE_STYLE_OK)
        header.addWidget(self.state_label)
        layout.addLayout(header)

        for mid in motor_ids:
            row = MitMotorRow(mid, send_callback)
            self.motor_rows[mid] = row
            layout.addWidget(row)

    def update_motor_status(self, motor_id, value):
        if motor_id in self.motor_rows:
            self.motor_rows[motor_id].update_status(value)

    def update_state(self, active_joints=None, blocked_joints=None, online=None, temps=None, errors=None, dragging_joints=None, is_connected=True):
        text, style, tooltip = build_finger_state_text(
            self.motor_ids, active_joints, blocked_joints, online, temps, errors, dragging_joints, is_connected
        )
        self.state_label.setText(text)
        self.state_label.setStyleSheet(style)
        self.state_label.setToolTip(tooltip)

    def zero_all(self):
        for row in self.motor_rows.values():
            row.zero_all()


# ============================================================================
# Main Revo3 Motor Control Panel
# ============================================================================

class Revo3MotorControlPanel(QWidget):
    """Motor Control Panel for Revo3 (21 motors, float values)

    Modes:
      - Position / Current: per-motor slider control
      - MIT: per-motor impedance control (pos + vel + cur + Kp + Kd)
    """

    sig_diag_fetched = Signal(bool, str, int, list, list)
    sig_toggles_fetched = Signal(bool, bool, bool, bool, bool, bool, bool)
    sig_collision_active_fetched = Signal(list)
    sig_control_priority = Signal(bool, int)
    sig_servo_drag_inactive = Signal(int)
    sig_servo_drag_stopped = Signal(int, object)
    sig_collision_apply_finished = Signal()
    sig_collision_reset_finished = Signal()

    def __init__(self):
        super().__init__()
        self.shared_data: Optional['SharedDataManager'] = None
        self._device = None
        self._slave_id = 1
        self.current_mode = MODE_POSITION
        self._active_servo_drags = set()
        self._servo_drag_starting = set()
        self._servo_drag_latest_targets = {}
        self._servo_drag_pending_stop = {}
        self._servo_drag_blocked_until_release = set()
        self._servo_drag_stall_counts = {}
        self._servo_drag_started_at = {}
        self._servo_drag_first_stall_at = {}
        self._servo_drag_first_stall_seq = {}
        self._collision_reset_succeeded = False
        self._servo_drag_next_token = 0
        self._servo_drag_locks = {}
        self._servo_drag_tokens = {}
        self._collision_active = [False] * REVO3_ULTRA_JOINT_COUNT
        self._last_motor_online = None
        self._last_motor_temps = []
        self._last_motor_fault_codes = []
        self._last_finger_state_signature = None
        self._last_finger_state_log_signature = None
        self._last_finger_state_log_time = 0.0
        self._last_motor_status_sequence = 0
        self._last_motor_status_sample_time = 0.0
        self._last_motor_fault_debug_signature = None
        self._last_motor_fault_debug_log_time = 0.0
        self.enable_motor_fault_debug = False

        self._setup_ui()
        self.update_texts()

        self.sig_diag_fetched.connect(self._update_diag_ui)
        self.sig_toggles_fetched.connect(self._update_toggles_ui)
        self.sig_collision_active_fetched.connect(self._apply_collision_active)
        self.sig_control_priority.connect(self._set_servo_drag_control_priority)
        self.sig_servo_drag_inactive.connect(self._handle_servo_drag_inactive)
        self.sig_servo_drag_stopped.connect(self._handle_servo_drag_stopped)
        self.sig_collision_apply_finished.connect(self._finish_collision_apply)
        self.sig_collision_reset_finished.connect(self._finish_collision_reset)

        # Timer for reading from shared Revo3 data.
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self._update_status_from_shared)
        self.update_timer.setInterval(50)  # 20Hz UI update

        self.collision_ui_timer = QTimer()
        self.collision_ui_timer.timeout.connect(self._refresh_collision_ui_realtime)
        self.collision_ui_timer.setInterval(COLLISION_UI_IDLE_POLL_MS)

        # Timer for periodic diagnostics refresh (5s)
        self.diag_timer = QTimer()
        self.diag_timer.timeout.connect(self._on_read_diagnostics)
        self.diag_timer.setInterval(5000)  # 5 seconds
        self.diag_consecutive_failures = 0

    @property
    def device(self):
        if self.shared_data and self.shared_data.device:
            return self.shared_data.device
        return self._device

    @property
    def slave_id(self):
        if self.shared_data:
            return self.shared_data.slave_id
        return self._slave_id

    def _setup_ui(self):
        layout = QVBoxLayout()
        layout.setSpacing(8)
        layout.setContentsMargins(12, 12, 12, 12)
        self.setLayout(layout)

        # Top bar: mode + global buttons
        top_layout = QHBoxLayout()
        top_layout.setSpacing(12)

        self.mode_label = QLabel(tr("mode") + ":")
        top_layout.addWidget(self.mode_label)

        self.mode_combo = QComboBox()
        self.mode_combo.addItems([
            tr("mode_position"), tr("mode_current"),
            tr("mode_impedance"), tr("mode_damping"),
            tr("mode_mit"), tr("mode_trajectory")
        ])
        self.mode_combo.setMinimumWidth(120)
        self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        top_layout.addWidget(self.mode_combo)

        top_layout.addWidget(QLabel("|"))

        self.open_all_btn = QPushButton(tr("btn_open_all"))
        self.open_all_btn.clicked.connect(self._open_all)
        top_layout.addWidget(self.open_all_btn)

        self.close_all_btn = QPushButton(tr("btn_close_all"))
        self.close_all_btn.clicked.connect(self._close_all)
        top_layout.addWidget(self.close_all_btn)

        self.default_gesture_btn = QPushButton("默认手势")
        self.default_gesture_btn.clicked.connect(self._default_gesture)
        top_layout.addWidget(self.default_gesture_btn)

        self.btn_half = QPushButton("1/2")
        self.btn_half.setFixedWidth(40)
        self.btn_half.clicked.connect(lambda: self._move_all_to_ratio(1/2))
        top_layout.addWidget(self.btn_half)

        self.btn_third = QPushButton("1/3")
        self.btn_third.setFixedWidth(40)
        self.btn_third.clicked.connect(lambda: self._move_all_to_ratio(1/3))
        top_layout.addWidget(self.btn_third)

        self.btn_quarter = QPushButton("1/4")
        self.btn_quarter.setFixedWidth(40)
        self.btn_quarter.clicked.connect(lambda: self._move_all_to_ratio(1/4))
        top_layout.addWidget(self.btn_quarter)

        self.btn_fifth = QPushButton("1/5")
        self.btn_fifth.setFixedWidth(40)
        self.btn_fifth.clicked.connect(lambda: self._move_all_to_ratio(1/5))
        top_layout.addWidget(self.btn_fifth)

        self.btn_two_thirds = QPushButton("2/3")
        self.btn_two_thirds.setFixedWidth(40)
        self.btn_two_thirds.clicked.connect(lambda: self._move_all_to_ratio(2/3))
        top_layout.addWidget(self.btn_two_thirds)

        self.btn_three_quarters = QPushButton("3/4")
        self.btn_three_quarters.setFixedWidth(40)
        self.btn_three_quarters.clicked.connect(lambda: self._move_all_to_ratio(3/4))
        top_layout.addWidget(self.btn_three_quarters)

        self.btn_four_fifths = QPushButton("4/5")
        self.btn_four_fifths.setFixedWidth(40)
        self.btn_four_fifths.clicked.connect(lambda: self._move_all_to_ratio(4/5))
        top_layout.addWidget(self.btn_four_fifths)

        self.zero_all_btn = QPushButton(tr("btn_zero_all"))
        self.zero_all_btn.clicked.connect(self._zero_all)
        top_layout.addWidget(self.zero_all_btn)

        top_layout.addWidget(QLabel("|"))

        self.btn_read_diag = QPushButton(tr("v3_diag_read"))
        self.btn_read_diag.clicked.connect(self._on_read_diagnostics)
        top_layout.addWidget(self.btn_read_diag)

        self.clear_faults_btn = QPushButton(tr("v3_clear_faults"))
        self.clear_faults_btn.clicked.connect(self._on_clear_motor_faults)
        top_layout.addWidget(self.clear_faults_btn)

        self.manual_calib_btn = QPushButton(tr("v3_manual_calibration"))
        self.manual_calib_btn.clicked.connect(self._on_manual_calibration)
        top_layout.addWidget(self.manual_calib_btn)

        self.reset_finger_btn = QPushButton(tr("v3_reset_finger_defaults"))
        self.reset_finger_btn.clicked.connect(self._on_reset_finger_defaults)
        top_layout.addWidget(self.reset_finger_btn)

        self.fps_badge = QLabel("FPS: --")
        self.fps_badge.setStyleSheet(
            "background-color: rgba(39, 174, 96, 0.15); "
            "border: 1px solid #27ae60; color: #27ae60; "
            "border-radius: 4px; padding: 2px 8px; "
            "font-weight: bold; font-size: 11px; "
            "font-family: 'SF Mono', 'Segoe UI Mono', monospace;"
        )
        top_layout.addWidget(self.fps_badge)
        top_layout.addStretch()

        self.lbl_diag_result = QLabel("")
        self.lbl_diag_result.setVisible(False)

        layout.addLayout(top_layout)

        # Top bar 2: Additional settings/actions (moved from bottom settings panel)
        top_layout2 = QHBoxLayout()
        top_layout2.setSpacing(12)

        # --- Quick actions ---
        self.auto_calib_cb = QPushButton(tr("v3_auto_calibration"))
        self.auto_calib_cb.setCheckable(True)
        self.auto_calib_cb.clicked.connect(self._on_set_power_on_auto_calibration)
        top_layout2.addWidget(self.auto_calib_cb)

        self.touch_screen_cb = QPushButton(tr("v3_touch_screen"))
        self.touch_screen_cb.setCheckable(True)
        self.touch_screen_cb.clicked.connect(self._on_touch_screen_changed)
        top_layout2.addWidget(self.touch_screen_cb)

        self.buzzer_cb = QPushButton(tr("buzzer"))
        self.buzzer_cb.setCheckable(True)
        self.buzzer_cb.clicked.connect(self._on_buzzer_changed)
        top_layout2.addWidget(self.buzzer_cb)

        self.vibration_cb = QPushButton(tr("vibration"))
        self.vibration_cb.setCheckable(True)
        self.vibration_cb.clicked.connect(self._on_vibration_changed)
        top_layout2.addWidget(self.vibration_cb)

        self.teaching_mode_cb = QPushButton(tr("v3_teaching_mode"))
        self.teaching_mode_cb.setCheckable(True)
        self.teaching_mode_cb.clicked.connect(self._on_teaching_mode_changed)
        top_layout2.addWidget(self.teaching_mode_cb)

        self.software_e_stop_cb = QPushButton(tr("v3_software_e_stop"))
        self.software_e_stop_cb.setCheckable(True)
        self.software_e_stop_cb.clicked.connect(self._on_software_e_stop_changed)
        top_layout2.addWidget(self.software_e_stop_cb)

        self.use_broadcast_id_cb = QPushButton(tr("v3_use_broadcast_id"))
        self.use_broadcast_id_cb.setCheckable(True)
        self.use_broadcast_id_cb.setChecked(True)
        self.use_broadcast_id_cb.clicked.connect(self._on_use_broadcast_id_changed)
        top_layout2.addWidget(self.use_broadcast_id_cb)

        self.err_log_cb = QPushButton(tr("v3_motor_fault_log"))
        self.err_log_cb.setCheckable(True)
        self.err_log_cb.setChecked(False)
        self.err_log_cb.clicked.connect(self._on_motor_fault_log_changed)
        top_layout2.addWidget(self.err_log_cb)

        top_layout2.addStretch()
        layout.addLayout(top_layout2)

        # Collision protection controls for testing SDK-owned servo drag and trajectory loops.
        collision_layout = QHBoxLayout()
        collision_layout.setSpacing(8)

        self.collision_enable_cb = QPushButton(tr("collision_protection"))
        self.collision_enable_cb.setObjectName("collisionProtectionToggle")
        self.collision_enable_cb.setCheckable(True)
        self.collision_enable_cb.setChecked(False)
        self.collision_enable_cb.setStyleSheet(f"""
            QPushButton#collisionProtectionToggle {{
                background-color: #eef1f4;
                color: #2c3e50;
                border: 1px solid #b8c2cc;
                border-radius: 4px;
                padding: 4px 12px;
                font-weight: 600;
                min-width: 96px;
            }}
            QPushButton#collisionProtectionToggle:hover {{
                background-color: #dde6ee;
            }}
            QPushButton#collisionProtectionToggle:checked {{
                background-color: {COLORS['success']};
                color: white;
                border: 1px solid {COLORS['success']};
            }}
        """)
        self.collision_enable_cb.clicked.connect(self._on_collision_apply)
        collision_layout.addWidget(self.collision_enable_cb)

        self.collision_source_combo = QComboBox()
        for key, _name in COLLISION_SOURCE_ITEMS:
            self.collision_source_combo.addItem(tr(key))
        self.collision_source_combo.setCurrentIndex(0)
        self.collision_source_combo.setFixedWidth(115)
        collision_layout.addWidget(self.collision_source_combo)

        self.collision_strategy_combo = QComboBox()
        for key, _name in COLLISION_STRATEGY_ITEMS:
            self.collision_strategy_combo.addItem(tr(key))
        self.collision_strategy_combo.setFixedWidth(105)
        collision_layout.addWidget(self.collision_strategy_combo)

        self.collision_label_err = QLabel(tr("collision_err_deg"))
        collision_layout.addWidget(self.collision_label_err)
        self.collision_error_spin = QDoubleSpinBox()
        self.collision_error_spin.setRange(1.0, 60.0)
        self.collision_error_spin.setDecimals(1)
        self.collision_error_spin.setSingleStep(1.0)
        self.collision_error_spin.setValue(COLLISION_GUI_DEFAULT_POSITION_ERROR_DEG)
        self.collision_error_spin.setFixedWidth(70)
        collision_layout.addWidget(self.collision_error_spin)

        self.collision_label_cur = QLabel(tr("collision_cur_ma"))
        collision_layout.addWidget(self.collision_label_cur)
        self.collision_current_spin = QDoubleSpinBox()
        self.collision_current_spin.setRange(100.0, 3000.0)
        self.collision_current_spin.setDecimals(0)
        self.collision_current_spin.setSingleStep(50.0)
        self.collision_current_spin.setValue(COLLISION_GUI_DEFAULT_CURRENT_MA)
        self.collision_current_spin.setFixedWidth(75)
        collision_layout.addWidget(self.collision_current_spin)

        self.collision_label_debounce = QLabel(tr("collision_debounce"))
        collision_layout.addWidget(self.collision_label_debounce)
        self.collision_debounce_spin = QSpinBox()
        self.collision_debounce_spin.setRange(0, 1000)
        self.collision_debounce_spin.setValue(100)
        self.collision_debounce_spin.setSuffix(" ms")
        self.collision_debounce_spin.setFixedWidth(85)
        collision_layout.addWidget(self.collision_debounce_spin)

        self.collision_label_cache = QLabel(tr("collision_cache"))
        collision_layout.addWidget(self.collision_label_cache)
        self.collision_cache_spin = QSpinBox()
        self.collision_cache_spin.setRange(0, 500)
        self.collision_cache_spin.setValue(COLLISION_GUI_CACHE_MS)
        self.collision_cache_spin.setSuffix(" ms")
        self.collision_cache_spin.setFixedWidth(80)
        collision_layout.addWidget(self.collision_cache_spin)

        self.collision_label_auto_clear = QLabel(tr("collision_auto_clear"))
        collision_layout.addWidget(self.collision_label_auto_clear)
        self.collision_auto_clear_spin = QSpinBox()
        self.collision_auto_clear_spin.setRange(0, 5000)
        self.collision_auto_clear_spin.setValue(COLLISION_GUI_AUTO_CLEAR_MS)
        self.collision_auto_clear_spin.setSuffix(" ms")
        self.collision_auto_clear_spin.setFixedWidth(85)
        collision_layout.addWidget(self.collision_auto_clear_spin)

        self.collision_apply_btn = QPushButton(tr("btn_apply"))
        self.collision_apply_btn.clicked.connect(self._on_collision_apply)
        collision_layout.addWidget(self.collision_apply_btn)

        self.collision_reset_btn = QPushButton(tr("btn_reset_collision"))
        self.collision_reset_btn.clicked.connect(self._on_collision_reset)
        collision_layout.addWidget(self.collision_reset_btn)

        self.collision_status_label = QLabel(f"{tr('collision_status_prefix')}: --")
        self.collision_status_label.setStyleSheet("color: #4a5568; font-size: 11px;")
        collision_layout.addWidget(self.collision_status_label)
        collision_layout.addStretch()
        layout.addLayout(collision_layout)
        self._update_collision_widgets_enabled()

        # Trajectory Params Toolbar (Hidden by default)
        self.traj_bar = QWidget()
        traj_layout = QHBoxLayout()
        traj_layout.setContentsMargins(0, 0, 0, 0)

        traj_layout.addWidget(QLabel("T(ms):"))
        self.spin_T = QSpinBox()
        self.spin_T.setRange(10, 10000)
        self.spin_T.setValue(500)
        self.spin_T.setFixedWidth(75)
        traj_layout.addWidget(self.spin_T)

        self.lbl_speed_or = QLabel(tr("or_speed") + "(rpm):")
        traj_layout.addWidget(self.lbl_speed_or)
        self.spin_speed = QDoubleSpinBox()
        self.spin_speed.setRange(0.0, 110.0)
        self.spin_speed.setValue(0.0)
        self.spin_speed.setToolTip(tr("speed_priority_tooltip"))
        self.spin_speed.setFixedWidth(80)
        traj_layout.addWidget(self.spin_speed)

        traj_layout.addWidget(QLabel("dt(ms):"))
        self.spin_dt = QSpinBox()
        self.spin_dt.setRange(1, 100)
        self.spin_dt.setValue(10)
        self.spin_dt.setFixedWidth(70)
        traj_layout.addWidget(self.spin_dt)

        traj_layout.addWidget(QLabel("Kp:"))
        self.spin_kp = QDoubleSpinBox()
        self.spin_kp.setRange(0, 10.0)
        self.spin_kp.setSingleStep(0.1)
        self.spin_kp.setValue(SERVO_DRAG_DEFAULT_KP)
        self.spin_kp.setFixedWidth(75)
        traj_layout.addWidget(self.spin_kp)

        traj_layout.addWidget(QLabel("Kd:"))
        self.spin_kd = QDoubleSpinBox()
        self.spin_kd.setRange(0, 5.0)
        self.spin_kd.setSingleStep(0.01)
        self.spin_kd.setValue(SERVO_DRAG_DEFAULT_KD)
        self.spin_kd.setFixedWidth(75)
        traj_layout.addWidget(self.spin_kd)

        self.run_all_btn = QPushButton("▶ Run All")
        self.run_all_btn.setStyleSheet("font-size: 13px; font-weight: bold; padding: 4px 14px; background-color: #27ae60; color: white;")
        self.run_all_btn.clicked.connect(self._on_run_all)
        traj_layout.addWidget(self.run_all_btn)
        traj_layout.addStretch()

        self.traj_bar.setLayout(traj_layout)
        layout.addWidget(self.traj_bar)

        # Stacked widget: page 0 = motor sliders, page 1 = MIT
        self.stack = QStackedWidget()
        layout.addWidget(self.stack, 1)

        # --- Page 0: Motor sliders (Position/Velocity/Current) ---
        self._build_motor_page()

        # --- Page 1: MIT control ---
        self._build_mit_page()

        # Set default mode to Position after all UI elements are built.
        self.mode_combo.setCurrentIndex(MODE_POSITION)

    def _build_motor_page(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        container = QWidget()
        grid = QGridLayout()
        grid.setSpacing(8)
        container.setLayout(grid)

        self.finger_groups = {}
        finger_names = get_revo3_finger_names()
        finger_motors = get_revo3_finger_motors()
        for i, name in enumerate(finger_names):
            motor_ids = finger_motors[name]
            group = FingerGroup(name, motor_ids, self._on_motor_value_changed, self._on_finger_action)
            group.run_finger_callback = self._on_run_finger_trajectory
            self.finger_groups[name] = group
            for mid, slider in group.motor_sliders.items():
                slider.run_callback = self._on_run_motor_trajectory
            row = 0 if i < 3 else 1
            col = i if i < 3 else i - 3
            grid.addWidget(group, row, col)

        # Device info panel in the empty slot (row 1, col 2)
        self.info_panel = DeviceInfoPanel()
        grid.addWidget(self.info_panel, 1, 2)

        for c in range(3):
            grid.setColumnStretch(c, 1)
        for r in range(2):
            grid.setRowStretch(r, 1)

        scroll.setWidget(container)
        self.stack.addWidget(scroll)  # index 0

    def _build_mit_page(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        container = QWidget()
        vbox = QVBoxLayout()
        vbox.setSpacing(8)
        container.setLayout(vbox)

        # MIT Global Top Bar
        mit_bar = QHBoxLayout()
        mit_bar.setContentsMargins(0, 0, 0, 0)

        mit_bar.addWidget(QLabel("Global Kp:"))
        self.mit_global_kp = QDoubleSpinBox()
        self.mit_global_kp.setRange(*MIT_KP_RANGE[:2])
        self.mit_global_kp.setSingleStep(MIT_KP_RANGE[2])
        self.mit_global_kp.setValue(1.0)
        self.mit_global_kp.setFixedWidth(65)
        mit_bar.addWidget(self.mit_global_kp)

        mit_bar.addWidget(QLabel("Global Kd:"))
        self.mit_global_kd = QDoubleSpinBox()
        self.mit_global_kd.setRange(*MIT_KD_RANGE[:2])
        self.mit_global_kd.setSingleStep(MIT_KD_RANGE[2])
        self.mit_global_kd.setValue(0.1)
        self.mit_global_kd.setFixedWidth(65)
        mit_bar.addWidget(self.mit_global_kd)

        apply_btn = QPushButton("Apply Kp/Kd to All")
        apply_btn.clicked.connect(self._on_mit_apply_all_gains)
        mit_bar.addWidget(apply_btn)
        mit_bar.addStretch()

        vbox.addLayout(mit_bar)

        grid = QGridLayout()
        grid.setSpacing(8)
        vbox.addLayout(grid)

        self.mit_groups = {}
        finger_names = get_revo3_finger_names()
        finger_motors = get_revo3_finger_motors()
        for i, name in enumerate(finger_names):
            motor_ids = finger_motors[name]
            group = MitFingerGroup(name, motor_ids, self._on_mit_value_changed)
            self.mit_groups[name] = group
            row = 0 if i < 3 else 1
            col = i if i < 3 else i - 3
            grid.addWidget(group, row, col)

        # MIT info panel in the empty slot (row 1, col 2)
        self.mit_info_panel = DeviceInfoPanel()
        grid.addWidget(self.mit_info_panel, 1, 2)

        for c in range(3):
            grid.setColumnStretch(c, 1)
        for r in range(2):
            grid.setRowStretch(r, 1)

        scroll.setWidget(container)
        self.stack.addWidget(scroll)  # index 1

    @staticmethod
    def _wrap_layout(layout):
        """Wrap a QLayout in a QWidget for use with QFormLayout"""
        w = QWidget()
        w.setLayout(layout)
        return w

    # ========================================================================
    # Settings callbacks
    # ========================================================================

    def _on_set_power_on_auto_calibration(self):
        if not self.device:
            return
        enabled = self.auto_calib_cb.isChecked()
        run_async(
            lambda: self.device.set_power_on_auto_calibration(self.slave_id, enabled)
        )
        print(f"[Settings] Auto calibration: {'enabled' if enabled else 'disabled'}")

    def _on_manual_calibration(self):
        if not self.device:
            return
        run_async(lambda: self.device.manual_calibration(self.slave_id))
        print("[Settings] Manual calibration triggered")

    def _on_clear_motor_faults(self):
        if not self.device:
            return
        run_async(lambda: self.device.clear_motor_faults(self.slave_id))
        print("[Settings] Motor errors cleared")

    def _on_reset_finger_defaults(self):
        if not self.device:
            return
        run_async(lambda: self.device.reset_finger_defaults(self.slave_id))
        print("[Settings] Finger parameters reset to defaults")

    def _on_touch_screen_changed(self):
        if not self.device:
            return
        enabled = self.touch_screen_cb.isChecked()
        run_async(lambda: self.device.set_touch_screen(self.slave_id, enabled))
        print(f"[Settings] Touch screen: {'enabled' if enabled else 'disabled'}")

    def _on_buzzer_changed(self):
        if not self.device:
            return
        enabled = self.buzzer_cb.isChecked()
        run_async(lambda: getattr(self.device, "set_buzzer", lambda e: None)(enabled))
        print(f"[Settings] Buzzer: {'enabled' if enabled else 'disabled'}")

    def _on_vibration_changed(self):
        if not self.device:
            return
        enabled = self.vibration_cb.isChecked()
        run_async(lambda: getattr(self.device, "set_vibration", lambda e: None)(enabled))
        print(f"[Settings] Vibration: {'enabled' if enabled else 'disabled'}")

    def _on_teaching_mode_changed(self):
        if not self.device:
            return
        enabled = self.teaching_mode_cb.isChecked()
        run_async(lambda: self.device.set_teaching_mode(self.slave_id, enabled))
        print(f"[Settings] Teaching mode: {'enabled' if enabled else 'disabled'}")

    def _on_software_e_stop_changed(self):
        if not self.device:
            return
        enabled = self.software_e_stop_cb.isChecked()
        run_async(lambda: self.device.set_software_e_stop(self.slave_id, enabled))
        print(f"[Settings] Software e-stop: {'enabled' if enabled else 'disabled'}")

    def _on_use_broadcast_id_changed(self):
        if not self.device:
            return
        enabled = self.use_broadcast_id_cb.isChecked()
        run_async(lambda: self.device.set_use_broadcast_id(self.slave_id, enabled))
        print(f"[Settings] Use broadcast ID: {'enabled' if enabled else 'disabled'}")

    def _on_motor_fault_log_changed(self, checked):
        self.enable_motor_fault_debug = checked
        print(f"[Settings] Motor error debug log: {'enabled' if checked else 'disabled'}")

    def _collision_enum_value(self, enum_name, value_name):
        if sdk is None:
            return value_name
        enum = getattr(sdk, enum_name, None)
        if enum is None:
            return value_name
        return getattr(enum, value_name, value_name)

    def _build_collision_config(self):
        source_name = COLLISION_SOURCE_ITEMS[self.collision_source_combo.currentIndex()][1]
        strategy_name = COLLISION_STRATEGY_ITEMS[self.collision_strategy_combo.currentIndex()][1]
        return {
            "enable": self.collision_enable_cb.isChecked(),
            "source": source_name,
            "position_error_threshold_deg": self.collision_error_spin.value(),
            "current_threshold_ma": self.collision_current_spin.value(),
            "debounce_time_ms": self.collision_debounce_spin.value(),
            "max_cached_status_age_ms": self.collision_cache_spin.value(),
            "strategy": strategy_name,
            "auto_clear_time_ms": self.collision_auto_clear_spin.value(),
        }

    def _update_collision_widgets_enabled(self, applying=False):
        if not hasattr(self, "collision_enable_cb"):
            return
        enabled = self.collision_enable_cb.isChecked()
        for widget in (
            self.collision_source_combo,
            self.collision_strategy_combo,
            self.collision_label_err,
            self.collision_error_spin,
            self.collision_label_cur,
            self.collision_current_spin,
            self.collision_label_debounce,
            self.collision_debounce_spin,
            self.collision_label_cache,
            self.collision_cache_spin,
            self.collision_label_auto_clear,
            self.collision_auto_clear_spin,
        ):
            widget.setEnabled(enabled and not applying)
        self.collision_apply_btn.setEnabled(enabled and not applying)
        self.collision_reset_btn.setEnabled(enabled and not applying)

    def _on_collision_apply(self):
        self._update_collision_widgets_enabled(applying=True)
        device = self.device
        if not device or not hasattr(device, "set_collision_protection_config"):
            self._update_collision_widgets_enabled()
            self.collision_status_label.setText(f"{tr('collision_status_prefix')}: {tr('collision_status_unsupported')}")
            return
        config = self._build_collision_config()
        if config is None:
            self._update_collision_widgets_enabled()
            self.collision_status_label.setText(f"{tr('collision_status_prefix')}: {tr('collision_status_sdk_unsupported')}")
            return
        self.collision_enable_cb.setEnabled(False)
        run_async(lambda: self._apply_collision_config_async(device, self.slave_id, config))
        state = tr("collision_status_enabled") if self.collision_enable_cb.isChecked() else tr("collision_status_disabled")
        self.collision_status_label.setText(f"{tr('collision_status_prefix')}: {state}")
        self.collision_status_label.setStyleSheet(
            f"color: {COLORS['success'] if self.collision_enable_cb.isChecked() else '#4a5568'}; font-size: 11px; font-weight: 600;"
        )
        eng_state = "enabled" if self.collision_enable_cb.isChecked() else "disabled"
        eng_source = COLLISION_SOURCE_ITEMS[self.collision_source_combo.currentIndex()][1]
        eng_strategy = COLLISION_STRATEGY_ITEMS[self.collision_strategy_combo.currentIndex()][1]
        print(
            f"[Collision] {eng_state}, source={eng_source}, "
            f"strategy={eng_strategy}, "
            f"debounce={self.collision_debounce_spin.value()}ms, "
            f"cache={self.collision_cache_spin.value()}ms, "
            f"auto_clear={self.collision_auto_clear_spin.value()}ms"
        )

    async def _apply_collision_config_async(self, device, slave_id, config):
        try:
            await self._await_collision_sdk(
                "apply config",
                lambda: device.set_collision_protection_config(slave_id, config),
            )
        except Exception as e:
            logger.warning("[Collision] apply config failed: %s", e)
        finally:
            self.sig_collision_apply_finished.emit()

    def _finish_collision_apply(self):
        self.collision_enable_cb.setEnabled(True)
        if not self.collision_enable_cb.isChecked():
            self._servo_drag_blocked_until_release.clear()
            self._servo_drag_stall_counts.clear()
            self._servo_drag_first_stall_at.clear()
            self._servo_drag_first_stall_seq.clear()
            self._collision_active = [False] * REVO3_ULTRA_JOINT_COUNT
        self._update_collision_widgets_enabled()
        self._update_collision_status_label()
        self._update_finger_collision_state()
        self._update_motor_diagnostic_badges()
        self._update_collision_ui_timer()

    def _on_collision_reset(self):
        device = self.device
        if not device or not hasattr(device, "reset_collision_state"):
            return
        self.collision_reset_btn.setEnabled(False)
        self._collision_reset_succeeded = False
        run_async(lambda: self._reset_collision_state_async(device, self.slave_id))

    async def _reset_collision_state_async(self, device, slave_id):
        try:
            await self._await_collision_sdk(
                "reset state",
                lambda: device.reset_collision_state(slave_id),
            )
            self._collision_reset_succeeded = True
        except Exception as e:
            logger.warning("[Collision] reset state failed: %s", e)
        finally:
            self.sig_collision_reset_finished.emit()

    def _finish_collision_reset(self):
        if self._collision_reset_succeeded:
            self._collision_active = [False] * REVO3_ULTRA_JOINT_COUNT
            self._servo_drag_blocked_until_release.clear()
            self._servo_drag_stall_counts.clear()
            self._servo_drag_first_stall_at.clear()
            self._servo_drag_first_stall_seq.clear()
            self._update_collision_status_label()
            self._update_finger_collision_state()
            self._update_motor_diagnostic_badges()
            print("[Collision] State reset")
        self._update_collision_widgets_enabled()
        self._update_collision_ui_timer()

    def _update_collision_status_label(self):
        active_ids = {i for i, flag in enumerate(self._collision_active) if flag}
        active = [f"M{i:02d}" for i in sorted(active_ids)]
        if active:
            self.collision_status_label.setText(tr("collision_status_active") + ": " + ", ".join(active[:6]))
            self.collision_status_label.setStyleSheet("color: #e74c3c; font-weight: bold; font-size: 11px;")
        elif self._servo_drag_blocked_until_release:
            guarded = [f"M{i:02d}" for i in sorted(self._servo_drag_blocked_until_release)]
            self.collision_status_label.setText("Stall guard: " + ", ".join(guarded[:6]))
            self.collision_status_label.setStyleSheet("color: #b7791f; font-weight: bold; font-size: 11px;")
        else:
            state = tr("collision_status_enabled") if self.collision_enable_cb.isChecked() else tr("collision_status_disabled")
            color = COLORS['success'] if self.collision_enable_cb.isChecked() else "#4a5568"
            self.collision_status_label.setText(f"{tr('collision_status_prefix')}: {state}")
            self.collision_status_label.setStyleSheet(f"color: {color}; font-size: 11px; font-weight: 600;")

    def _should_fast_poll_collision_ui(self):
        return (
            bool(self._active_servo_drags)
            or any(self._collision_active)
            or bool(self._servo_drag_blocked_until_release)
        )

    def _update_collision_ui_timer(self):
        if not hasattr(self, "collision_ui_timer"):
            return
        if not self.device:
            self.collision_ui_timer.stop()
            return
        interval = COLLISION_UI_FAST_POLL_MS if self._should_fast_poll_collision_ui() else COLLISION_UI_IDLE_POLL_MS
        if self.collision_ui_timer.interval() != interval:
            self.collision_ui_timer.setInterval(interval)
        if not self.collision_ui_timer.isActive():
            self.collision_ui_timer.start()

    def _refresh_collision_ui_realtime(self):
        if not self.device:
            self.collision_ui_timer.stop()
            return
        self._poll_collision_state(force=self._should_fast_poll_collision_ui())

    def _update_finger_collision_state(self):
        active_joints = {idx for idx, active in enumerate(self._collision_active) if active}
        blocked_joints = set(self._servo_drag_blocked_until_release)
        dragging_joints = set(self._active_servo_drags)
        is_connected = self.device is not None
        self._log_finger_state_transition(active_joints, blocked_joints, dragging_joints, is_connected)
        for group in getattr(self, "finger_groups", {}).values():
            group.update_state(
                active_joints,
                blocked_joints,
                self._last_motor_online,
                self._last_motor_temps,
                self._last_motor_fault_codes,
                dragging_joints,
                is_connected,
            )
        for group in getattr(self, "mit_groups", {}).values():
            group.update_state(
                active_joints,
                blocked_joints,
                self._last_motor_online,
                self._last_motor_temps,
                self._last_motor_fault_codes,
                dragging_joints,
                is_connected,
            )

    def _update_motor_diagnostic_badges(self):
        if self._last_motor_online is None:
            return
        temps = self._last_motor_temps or []
        errors = self._last_motor_fault_codes or []
        blocked_joints = set(self._servo_drag_blocked_until_release) if hasattr(self, "_servo_drag_blocked_until_release") else set()
        for group in getattr(self, "finger_groups", {}).values():
            for mid, slider in group.motor_sliders.items():
                is_online = (self._last_motor_online & (1 << mid)) != 0
                temp_val = temps[mid] if mid < len(temps) else 0.0
                err_val = errors[mid] if mid < len(errors) else 0
                collision_active = mid < len(self._collision_active) and self._collision_active[mid]
                stall_guard_active = mid in blocked_joints
                slider.update_diagnostics(temp_val, is_online, err_val, collision_active, stall_guard_active)
        for group in getattr(self, "mit_groups", {}).values():
            for mid, row in group.motor_rows.items():
                is_online = (self._last_motor_online & (1 << mid)) != 0
                temp_val = temps[mid] if mid < len(temps) else 0.0
                err_val = errors[mid] if mid < len(errors) else 0
                collision_active = mid < len(self._collision_active) and self._collision_active[mid]
                stall_guard_active = mid in blocked_joints
                row.update_diagnostics(temp_val, is_online, err_val, collision_active, stall_guard_active)

    def _log_motor_fault_sample_debug(self, errors, status_sequence, is_new_sample):
        if not self.enable_motor_fault_debug:
            return
        faulted = tuple(
            (idx, errors[idx], tuple(decode_motor_fault_code(errors[idx])))
            for idx in range(min(len(errors or []), REVO3_ULTRA_JOINT_COUNT))
            if decode_motor_fault_code(errors[idx])
        )
        now = time.monotonic()
        signature = faulted
        should_log = faulted and now - self._last_motor_fault_debug_log_time >= MOTOR_ERROR_DEBUG_LOG_INTERVAL_S
        if not faulted:
            if self._last_motor_fault_debug_signature:
                print("[MotorErrorDebug] cleared")
            self._last_motor_fault_debug_signature = None
            self._last_motor_fault_debug_log_time = now
            return
        if not should_log:
            return
        self._last_motor_fault_debug_signature = signature
        self._last_motor_fault_debug_log_time = now
        sample_age_ms = int((now - self._last_motor_status_sample_time) * 1000)
        freq = getattr(self.shared_data, "motor_frequency", None) if self.shared_data else None
        raw = ", ".join(
            f"M{idx:02d}=0x{raw_val:04X}({'+'.join(names)})"
            for idx, raw_val, names in faulted
        )
        freshness = "fresh" if is_new_sample else "reused"
        print(
            f"[MotorErrorDebug] {freshness} sample, age={sample_age_ms}ms, "
            f"collector={freq if freq is not None else 'n/a'}Hz, "
            f"seq={status_sequence}, faults={raw}"
        )

    def _current_finger_state_signature(self, active_joints, blocked_joints, dragging_joints, is_connected):
        if not is_connected:
            return None
        stall_joints = set()
        error_joints = set()
        offline_joints = set()
        errors = self._last_motor_fault_codes or []
        for mid in range(REVO3_ULTRA_JOINT_COUNT):
            err_val = errors[mid] if mid < len(errors) else 0
            err_names = decode_motor_fault_code(err_val)
            if "Stall" in err_names:
                stall_joints.add(mid)
            if [name for name in err_names if name != "Stall"]:
                error_joints.add(mid)
            if self._last_motor_online is not None and (self._last_motor_online & (1 << mid)) == 0:
                offline_joints.add(mid)
        return (
            tuple(sorted(active_joints)),
            tuple(sorted(blocked_joints)),
            tuple(sorted(stall_joints)),
            tuple(sorted(error_joints)),
            tuple(sorted(offline_joints)),
            tuple(sorted(dragging_joints)),
        )

    def _log_finger_state_transition(self, active_joints, blocked_joints, dragging_joints, is_connected):
        if not self.enable_motor_fault_debug:
            return
        signature = self._current_finger_state_signature(active_joints, blocked_joints, dragging_joints, is_connected)
        if signature == self._last_finger_state_signature:
            return
        self._last_finger_state_signature = signature
        if signature is None:
            return
        active, blocked, stall, errors, offline, dragging = (set(items) for items in signature)
        reasons = []
        if active:
            reasons.append(f"collision_active={_format_motor_labels(active)}")
        if blocked:
            reasons.append(f"stall_guard={_format_motor_labels(blocked)}")
        if stall:
            reasons.append(f"stall_bit={_format_motor_labels(stall)}")
        if errors:
            reasons.append(f"errors={_format_motor_labels(errors)}")
        if offline:
            reasons.append(f"offline={_format_motor_labels(offline)}")
        if not reasons:
            if self._last_finger_state_log_signature is not None:
                logger.info(
                    "[FingerState] OK "
                    f"(collision_toggle={self.collision_enable_cb.isChecked()}, "
                    f"dragging={_format_motor_labels(dragging) if dragging else 'none'})"
                )
            self._last_finger_state_log_signature = None
            self._last_finger_state_log_time = time.monotonic()
            return

        now = time.monotonic()
        has_collision = bool(active)
        should_log = (
            has_collision
            or signature != self._last_finger_state_log_signature
            and now - self._last_finger_state_log_time >= FINGER_STATE_LOG_INTERVAL_S
        )
        if not should_log:
            return

        self._last_finger_state_log_signature = signature
        self._last_finger_state_log_time = now
        logger.info(
            "[FingerState] State: "
            + "; ".join(reasons)
            + f"; collision_toggle={self.collision_enable_cb.isChecked()}; "
            + f"dragging={_format_motor_labels(dragging) if dragging else 'none'}"
        )

    def _update_active_drag_stall_guard(self, advance=False, status_sequence=None):
        if not hasattr(self, "collision_enable_cb") or not self.collision_enable_cb.isChecked():
            self._servo_drag_stall_counts.clear()
            self._servo_drag_first_stall_at.clear()
            self._servo_drag_first_stall_seq.clear()
            return
        if not self._active_servo_drags and not self._servo_drag_starting:
            self._servo_drag_stall_counts.clear()
            self._servo_drag_first_stall_at.clear()
            self._servo_drag_first_stall_seq.clear()
            return
        errors = self._last_motor_fault_codes or []
        dragging = set(self._active_servo_drags).union(self._servo_drag_starting)
        for motor_id in list(self._servo_drag_stall_counts):
            if motor_id not in dragging:
                self._servo_drag_stall_counts.pop(motor_id, None)
                self._servo_drag_first_stall_at.pop(motor_id, None)
                self._servo_drag_first_stall_seq.pop(motor_id, None)
        for motor_id in sorted(dragging):
            stalled = motor_id < len(errors) and (errors[motor_id] & (1 << 8)) != 0
            if not stalled:
                self._servo_drag_stall_counts.pop(motor_id, None)
                self._servo_drag_first_stall_at.pop(motor_id, None)
                self._servo_drag_first_stall_seq.pop(motor_id, None)
                continue
            if advance:
                now = time.monotonic()
                if motor_id not in self._servo_drag_first_stall_at:
                    self._servo_drag_first_stall_at[motor_id] = now
                    self._servo_drag_first_stall_seq[motor_id] = status_sequence
                    drag_started_at = self._servo_drag_started_at.get(motor_id)
                    drag_elapsed_ms = int((now - drag_started_at) * 1000) if drag_started_at else -1
                    logger.info(
                        "[Collision] GUI first firmware Stall sample "
                        f"M{motor_id:02d}, drag_elapsed={drag_elapsed_ms}ms, "
                        f"seq={status_sequence}, raw=0x{errors[motor_id]:04X}"
                    )
                self._servo_drag_stall_counts[motor_id] = self._servo_drag_stall_counts.get(motor_id, 0) + 1
            count = self._servo_drag_stall_counts.get(motor_id, 0)
            if count < GUI_STALL_BLOCK_CONSECUTIVE_SAMPLES:
                continue
            if motor_id not in self._servo_drag_blocked_until_release:
                now = time.monotonic()
                drag_started_at = self._servo_drag_started_at.get(motor_id)
                first_stall_at = self._servo_drag_first_stall_at.get(motor_id)
                drag_elapsed_ms = int((now - drag_started_at) * 1000) if drag_started_at else -1
                stall_elapsed_ms = int((now - first_stall_at) * 1000) if first_stall_at else -1
                logger.info(
                    f"[Collision] GUI blocking drag M{motor_id:02d} after "
                    f"{count} consecutive firmware Stall samples, "
                    f"drag_elapsed={drag_elapsed_ms}ms, stall_elapsed={stall_elapsed_ms}ms, "
                    f"first_seq={self._servo_drag_first_stall_seq.get(motor_id)}, "
                    f"seq={status_sequence}"
                )
            self._block_servo_drag_until_release(motor_id)
            self._cancel_servo_drag_locally(motor_id, cancel_sdk_stream=False, restore_control_priority=False)

    def _apply_collision_active(self, active):
        self._collision_active = active
        active_set = {idx for idx, flag in enumerate(active) if flag}
        affected_drags = self._active_servo_drags.intersection(active_set)
        for motor_id in list(affected_drags):
            print(f"[Collision] GUI stopping local drag state for M{motor_id:02d} because collision is active")
            self._block_servo_drag_until_release(motor_id)
            self._cancel_servo_drag_locally(motor_id)
        self._update_collision_status_label()
        self._update_finger_collision_state()
        self._update_motor_diagnostic_badges()
        self._update_collision_ui_timer()

    def _poll_collision_state(self, force=False):
        """Poll shared collision state asynchronously or synchronously without blocking GUI thread."""
        device = self.device
        if not device:
            return
        func = getattr(device, "collision_active", None) or getattr(device, "get_all_collision_active", None)
        if not callable(func):
            return
        try:
            if asyncio.iscoroutinefunction(func):
                if getattr(self, "_collision_poll_in_flight", False):
                    return
                self._collision_poll_in_flight = True

                async def _fetch():
                    try:
                        raw = await func()
                        active = [bool(v) for v in raw]
                        self.sig_collision_active_fetched.emit(active)
                    except Exception as ex:
                        print(f"[Collision] Poll active state failed: {ex}")
                    finally:
                        self._collision_poll_in_flight = False

                run_async(_fetch)
            else:
                active_raw = func()
                if inspect.isawaitable(active_raw):
                    if getattr(self, "_collision_poll_in_flight", False):
                        return
                    self._collision_poll_in_flight = True

                    async def _fetch_awaitable():
                        try:
                            raw = await active_raw
                            active = [bool(v) for v in raw]
                            self.sig_collision_active_fetched.emit(active)
                        except Exception as ex:
                            print(f"[Collision] Poll active state failed: {ex}")
                        finally:
                            self._collision_poll_in_flight = False

                    run_async(_fetch_awaitable)
                else:
                    active = [bool(v) for v in active_raw]
                    self.sig_collision_active_fetched.emit(active)
        except Exception as e:
            print(f"[Collision] Poll active state failed: {e}")

    async def _await_collision_sdk(self, label, call_fn):
        result = call_fn()
        if inspect.isawaitable(result):
            return await result
        return result

    def _on_read_diagnostics(self):
        async def fetch_diag():
            device = self.device
            if not device:
                return
            try:
                hw = await device.get_hardware_revision(self.slave_id)
                online = await device.get_motor_online_mask(self.slave_id)
                temps = await device.get_all_motor_module_temperatures(self.slave_id)
                errors = await device.get_all_joint_fault_codes(self.slave_id)
                self.sig_diag_fetched.emit(True, hw, online, temps, errors)

                async def _get(func_name, fallback):
                    func = getattr(device, func_name, None)
                    if not callable(func):
                        return fallback
                    try:
                        return await func(self.slave_id)
                    except Exception:
                        return fallback

                # Also track toggles periodically
                ac = await _get(
                    "get_power_on_auto_calibration",
                    self.auto_calib_cb.isChecked(),
                )
                ts = await _get("revo3_get_touch_screen", self.touch_screen_cb.isChecked())
                bz = await _get("revo3_get_buzzer_switch", self.buzzer_cb.isChecked())
                vib = await _get("revo3_get_vibration_switch", self.vibration_cb.isChecked())
                tm = await _get("revo3_get_teaching_mode", self.teaching_mode_cb.isChecked())
                es = await _get("revo3_get_software_e_stop", self.software_e_stop_cb.isChecked())
                ub = await _get("revo3_get_use_broadcast_id", self.use_broadcast_id_cb.isChecked())
                self.sig_toggles_fetched.emit(ac, ts, bz, vib, tm, es, ub)
            except Exception as e:
                if self.shared_data and not self.shared_data.is_running:
                    return
                print(f"[Diag] Error fetching diagnostics: {e}")
                self.sig_diag_fetched.emit(False, str(e), 0, [], [])

        run_async(fetch_diag)

    def _update_diag_ui(self, success, hw, online, temps, errors):
        if True:
            if success:
                total = 21
                online_count = bin(online).count('1')
                if online_count == 0:
                    self.diag_consecutive_failures += 1
                    self._last_motor_online = online
                    self._last_motor_temps = []
                    self._last_motor_fault_codes = []
                    self._servo_drag_stall_counts.clear()
                    self._servo_drag_first_stall_at.clear()
                    self._servo_drag_first_stall_seq.clear()
                    self._update_finger_collision_state()
                    self._update_motor_diagnostic_badges()
                    msg = f"FW: N/A | HW: {hw} | ⚠ 0/{total} Online"
                    self.lbl_diag_result.setStyleSheet("color: red; font-weight: bold;")
                    if self.diag_consecutive_failures >= 2:
                        logger.warning("[MotorControl] All motors offline. Connection might be lost.")
                        self.diag_timer.stop()
                        if self.shared_data:
                            self.shared_data.connection_lost.emit()
                    self.lbl_diag_result.setText(msg)
                    for panel in [self.info_panel, self.mit_info_panel]:
                        panel.update_info(hw=hw, online=online, temps=[], errors=[])
                    return

                self.diag_consecutive_failures = 0
                self._last_motor_online = online
                self._last_motor_temps = temps or []
                self._last_motor_fault_codes = errors or []
                self._update_active_drag_stall_guard(advance=True)

                # Build offline motor ID list
                offline_ids = [f"M{i:02d}" for i in range(total) if not (online & (1 << i))]
                if offline_ids:
                    online_str = f"⚠ {online_count}/{total} Online  Offline: {', '.join(offline_ids)}"
                else:
                    online_str = f"✅ {online_count}/{total} Online"

                # Find max temperature and which motor
                if temps:
                    max_temp = max(temps[:total])
                    max_mid = temps[:total].index(max_temp)
                    if max_temp >= 60:
                        temp_str = f"🌡 Max: {int(max_temp)}°C (M{max_mid:02d}) ⚠ Overheat!"
                    elif max_temp >= 45:
                        temp_str = f"🌡 Max: {int(max_temp)}°C (M{max_mid:02d}) ⚡Warm"
                    else:
                        temp_str = f"🌡 Max: {int(max_temp)}°C (M{max_mid:02d})"
                else:
                    temp_str = "🌡 N/A"

                # Fault-code summary. Operating-state bits are read from a separate field.
                if errors:
                    err_motors = [(i, e) for i, e in enumerate(errors[:total]) if e != 0]
                    if err_motors:
                        err_parts = []
                        for i, e in err_motors[:4]:
                            err_names = decode_motor_fault_code(e)
                            err_parts.append(f"M{i:02d}={'+'.join(err_names)}")

                        if len(err_motors) > 4:
                            err_parts.append(f"+{len(err_motors)-4} more")
                        err_str = f"❌ ERR: {', '.join(err_parts)}"
                    else:
                        err_str = "✅ No Errors"
                else:
                    err_str = ""

                fw = getattr(self._device_info, 'firmware_version', 'N/A') if hasattr(self, '_device_info') and self._device_info else 'N/A'

                # Build compact toolbar status (brief indicator)
                issues = []
                if offline_ids:
                    issues.append(f"{len(offline_ids)} offline")
                if errors and err_motors:
                    issues.append(f"{len(err_motors)} err")
                if temps and max(temps[:total]) >= 60:
                    issues.append("overheat")

                if issues:
                    msg = f"FW: {fw} | HW: {hw} | ⚠ {', '.join(issues)}  |  {temp_str}"
                    self.lbl_diag_result.setStyleSheet("color: #e74c3c; font-weight: bold;")
                else:
                    msg = f"FW: {fw} | HW: {hw} | ✅ {online_count}/{total} Online  |  {temp_str}"
                    self.lbl_diag_result.setStyleSheet(f"color: {COLORS['primary']};")

                # Update individual motor UI badges
                self._update_motor_diagnostic_badges()

                self._update_finger_collision_state()
                self._update_collision_ui_timer()

            else:
                msg = hw  # error message is in hw
                self.lbl_diag_result.setStyleSheet("color: red; font-weight: bold;")
                self.diag_consecutive_failures += 1
                if self.diag_consecutive_failures >= 3:
                    logger.warning("[MotorControl] Diagnostic refresh failed 3 times. Connection might be lost.")
                    self.diag_timer.stop()
                    if self.shared_data:
                        self.shared_data.connection_lost.emit()

            self.lbl_diag_result.setText(msg)

            # Update info panels on all pages
            for panel in [self.info_panel, self.mit_info_panel]:
                panel.update_info(hw=hw, online=online, temps=temps, errors=errors)

    def update_texts(self):
        self.mode_label.setText(tr("mode") + ":")
        self.mode_combo.setItemText(0, tr("mode_position"))
        self.mode_combo.setItemText(1, tr("mode_current"))
        self.mode_combo.setItemText(2, tr("mode_impedance"))
        self.mode_combo.setItemText(3, tr("mode_damping"))
        self.mode_combo.setItemText(4, tr("mode_mit"))
        self.mode_combo.setItemText(5, tr("mode_trajectory"))
        self.open_all_btn.setText(tr("btn_open_all"))
        self.close_all_btn.setText(tr("btn_close_all"))
        self.zero_all_btn.setText(tr("btn_zero_all"))
        self.auto_calib_cb.setText(tr("v3_auto_calibration"))
        self.manual_calib_btn.setText(tr("v3_manual_calibration"))
        self.clear_faults_btn.setText(tr("v3_clear_faults"))
        self.reset_finger_btn.setText(tr("v3_reset_finger_defaults"))
        self.touch_screen_cb.setText(tr("v3_touch_screen"))
        self.buzzer_cb.setText(tr("buzzer"))
        self.vibration_cb.setText(tr("vibration"))
        self.teaching_mode_cb.setText(tr("v3_teaching_mode"))
        self.software_e_stop_cb.setText(tr("v3_software_e_stop"))
        self.use_broadcast_id_cb.setText(tr("v3_use_broadcast_id"))
        self.err_log_cb.setText(tr("v3_motor_fault_log"))
        self.btn_read_diag.setText(tr("v3_diag_read"))

        if hasattr(self, 'lbl_speed_or'):
            self.lbl_speed_or.setText(tr("or_speed") + "(rpm):")
        if hasattr(self, 'spin_speed'):
            self.spin_speed.setToolTip(tr("speed_priority_tooltip"))

        # Update finger group buttons
        if hasattr(self, 'finger_groups'):
            for group in self.finger_groups.values():
                group.update_texts()

        # Update info panels
        for panel in [self.info_panel, self.mit_info_panel]:
            if hasattr(panel, 'update_texts'):
                panel.update_texts()

        # Update collision protection texts
        if hasattr(self, 'collision_enable_cb'):
            self.collision_enable_cb.setText(tr("collision_protection"))
            self.collision_label_err.setText(tr("collision_err_deg"))
            self.collision_label_cur.setText(tr("collision_cur_ma"))
            self.collision_label_debounce.setText(tr("collision_debounce"))
            self.collision_label_cache.setText(tr("collision_cache"))
            self.collision_label_auto_clear.setText(tr("collision_auto_clear"))
            self.collision_apply_btn.setText(tr("btn_apply"))
            self.collision_reset_btn.setText(tr("btn_reset_collision"))

            for i, (key, _) in enumerate(COLLISION_SOURCE_ITEMS):
                self.collision_source_combo.setItemText(i, tr(key))
            for i, (key, _) in enumerate(COLLISION_STRATEGY_ITEMS):
                self.collision_strategy_combo.setItemText(i, tr(key))

            self._update_collision_status_label()

    # ========================================================================
    # Mode switching
    # ========================================================================

    def _on_mode_changed(self, index):
        if index != MODE_POSITION:
            self._stop_all_servo_drags()
        self.current_mode = index

        if hasattr(self, 'traj_bar'):
            if index == MODE_TRAJECTORY:
                self.traj_bar.show()
            else:
                self.traj_bar.hide()

        if index <= MODE_DAMPING or index == MODE_TRAJECTORY:
            # Position / Current / Impedance / Damping / Trajectory -> motor slider page
            self.stack.setCurrentIndex(0)
            min_val, max_val, step, _ = MODE_RANGES[index]
            is_traj = (index == MODE_TRAJECTORY)
            for group in self.finger_groups.values():
                group.set_mode_range(min_val, max_val, step, index)
                group.run_finger_btn.setVisible(is_traj)
                group.open_btn.setVisible(not is_traj)
                group.close_btn.setVisible(not is_traj)
                for slider in group.motor_sliders.values():
                    slider.live_update = not is_traj
                    slider.run_btn.setVisible(is_traj)

            # Show open/close/fraction buttons only in position or trajectory mode
            is_pos_or_traj = index in (MODE_POSITION, MODE_TRAJECTORY)
            self.open_all_btn.setVisible(is_pos_or_traj)
            self.close_all_btn.setVisible(is_pos_or_traj)
            self.btn_half.setVisible(is_pos_or_traj)
            self.btn_third.setVisible(is_pos_or_traj)
            self.btn_quarter.setVisible(is_pos_or_traj)
            self.btn_fifth.setVisible(is_pos_or_traj)

        elif index == MODE_MIT:
            self.stack.setCurrentIndex(1)
            self.open_all_btn.setVisible(False)
            self.close_all_btn.setVisible(False)
            self.btn_half.setVisible(False)
            self.btn_third.setVisible(False)
            self.btn_quarter.setVisible(False)
            self.btn_fifth.setVisible(False)

    # ========================================================================
    # Motor value callbacks
    # ========================================================================

    def _on_motor_value_changed(self, motor_id, value):
        device = self.device
        if not device:
            return
        if self.current_mode == MODE_POSITION:
            if motor_id in self._active_servo_drags:
                self._update_servo_drag_target(motor_id, value)
            else:
                run_async(lambda: self._send_motor_command(motor_id, value))
            return
        run_async(lambda: self._send_motor_command(motor_id, value))

    def _get_servo_drag_params(self):
        return {
            "kp": getattr(self, "spin_kp", None).value() if hasattr(self, "spin_kp") else SERVO_DRAG_DEFAULT_KP,
            "kd": getattr(self, "spin_kd", None).value() if hasattr(self, "spin_kd") else SERVO_DRAG_DEFAULT_KD,
            "vel_cap": (
                getattr(self, "spin_speed", None).value()
                if hasattr(self, "spin_speed") and self.spin_speed.value() > 0.0
                else SERVO_DRAG_DEFAULT_VEL_CAP_RPM
            ),
            "interval_ms": SERVO_DRAG_INTERVAL_MS,
            "filter_mode": SERVO_DRAG_FILTER_MODE,
            "omega": SERVO_DRAG_OMEGA,
            "idle_timeout_ms": SERVO_DRAG_IDLE_TIMEOUT_MS,
        }

    def _next_servo_drag_token(self):
        self._servo_drag_next_token += 1
        return self._servo_drag_next_token

    def _is_servo_drag_token_current(self, motor_id, token):
        return self._servo_drag_tokens.get(motor_id) == token

    def _clear_servo_drag_timing(self, motor_id):
        self._servo_drag_started_at.pop(motor_id, None)
        self._servo_drag_stall_counts.pop(motor_id, None)
        self._servo_drag_first_stall_at.pop(motor_id, None)
        self._servo_drag_first_stall_seq.pop(motor_id, None)

    async def _await_servo_drag_sdk(self, label, call_fn):
        result = call_fn()
        if inspect.isawaitable(result):
            return await result
        return result

    def _run_servo_drag_async(self, motor_id, coro_fn):
        return run_control_async(lambda: self._run_servo_drag_locked(motor_id, coro_fn))

    async def _run_servo_drag_locked(self, motor_id, coro_fn):
        lock = self._servo_drag_locks.get(motor_id)
        if lock is None:
            lock = asyncio.Lock()
            self._servo_drag_locks[motor_id] = lock
        async with lock:
            return await coro_fn()

    def _start_servo_drag(self, motor_id, value):
        if self.current_mode != MODE_POSITION or not self.device:
            return
        if motor_id in self._servo_drag_blocked_until_release:
            return
        if motor_id < len(self._collision_active) and self._collision_active[motor_id]:
            return
        token = self._next_servo_drag_token()
        self._servo_drag_tokens[motor_id] = token
        was_idle = not self._active_servo_drags
        self._active_servo_drags.add(motor_id)
        if was_idle:
            self._begin_servo_drag_control_priority()
        self._update_finger_collision_state()
        self._update_collision_ui_timer()
        self._servo_drag_starting.add(motor_id)
        self._servo_drag_latest_targets[motor_id] = value
        self._servo_drag_started_at[motor_id] = time.monotonic()
        self._servo_drag_stall_counts.pop(motor_id, None)
        self._servo_drag_first_stall_at.pop(motor_id, None)
        self._servo_drag_first_stall_seq.pop(motor_id, None)
        p = self._get_servo_drag_params()
        device = self.device
        slave_id = self.slave_id
        self._run_servo_drag_async(
            motor_id,
            lambda: self._start_servo_drag_task(device, slave_id, motor_id, value, p, token),
        )

    async def _start_servo_drag_task(self, device, slave_id, motor_id, value, params, token):
        try:
            await self._await_servo_drag_sdk(
                f"start M{motor_id:02d}",
                lambda: device.start_servo_drag(
                    slave_id,
                    motor_id,
                    value,
                    params["kp"],
                    params["kd"],
                    params["vel_cap"],
                    params["interval_ms"],
                    params["idle_timeout_ms"],
                    params["filter_mode"],
                    params["omega"],
                ),
            )
        except asyncio.TimeoutError:
            print(f"[ServoDrag] start M{motor_id:02d} timed out; clearing local drag state")
            self.sig_servo_drag_inactive.emit(motor_id)
            return
        except Exception as e:
            if not self._is_servo_drag_token_current(motor_id, token):
                raise
            if "collision protection is active" in str(e):
                self._block_servo_drag_until_release(motor_id)
            was_last_drag = len(self._active_servo_drags) == 1 and motor_id in self._active_servo_drags
            self._active_servo_drags.discard(motor_id)
            self._servo_drag_starting.discard(motor_id)
            self._servo_drag_latest_targets.pop(motor_id, None)
            self._clear_servo_drag_timing(motor_id)
            self._servo_drag_tokens.pop(motor_id, None)
            self._servo_drag_pending_stop.pop(motor_id, None)
            if was_last_drag:
                self._end_servo_drag_control_priority()
            self.sig_collision_active_fetched.emit(list(self._collision_active))
            raise

        if not self._is_servo_drag_token_current(motor_id, token):
            try:
                await self._call_cancel_servo_drag(device, slave_id, motor_id)
            except asyncio.TimeoutError:
                print(f"[ServoDrag] stale cancel M{motor_id:02d} timed out")
            return

        latest = self._servo_drag_latest_targets.get(motor_id, value)
        self._servo_drag_starting.discard(motor_id)
        pending_stop = self._servo_drag_pending_stop.pop(motor_id, None)
        if pending_stop is not None:
            self._active_servo_drags.discard(motor_id)
            try:
                await self._await_servo_drag_sdk(
                    f"stop pending M{motor_id:02d}",
                    lambda: device.stop_servo_drag(slave_id, motor_id, pending_stop),
                )
            except asyncio.TimeoutError:
                print(f"[ServoDrag] pending stop M{motor_id:02d} timed out; clearing local drag state")
            if self._is_servo_drag_token_current(motor_id, token):
                self._servo_drag_latest_targets.pop(motor_id, None)
                self._clear_servo_drag_timing(motor_id)
                self._servo_drag_tokens.pop(motor_id, None)
                if not self._active_servo_drags:
                    self._end_servo_drag_control_priority()
            self.sig_collision_active_fetched.emit(list(self._collision_active))
            return
        if motor_id not in self._active_servo_drags:
            try:
                await self._await_servo_drag_sdk(
                    f"stop inactive M{motor_id:02d}",
                    lambda: device.stop_servo_drag(slave_id, motor_id, latest),
                )
            except asyncio.TimeoutError:
                print(f"[ServoDrag] inactive stop M{motor_id:02d} timed out; clearing local drag state")
            if self._is_servo_drag_token_current(motor_id, token):
                self._servo_drag_latest_targets.pop(motor_id, None)
                self._clear_servo_drag_timing(motor_id)
                self._servo_drag_tokens.pop(motor_id, None)
                self._servo_drag_pending_stop.pop(motor_id, None)
            return
        if latest != value:
            # Sync call; no await needed, writes directly to the shared cache.
            if not self._try_update_servo_drag(device, slave_id, motor_id, latest):
                return
        # No timer needed; SDK worker handles timing.

    def _try_update_servo_drag(self, device, slave_id, motor_id, value):
        try:
            device.update_servo_drag(slave_id, motor_id, value)
            return True
        except Exception as e:
            msg = str(e)
            if "servo_drag is not active" in msg or "not active" in msg:
                print(f"[ServoDrag] update M{motor_id:02d} ignored because SDK stream is inactive")
            else:
                print(f"[ServoDrag] update M{motor_id:02d} failed: {e}")
            self.sig_servo_drag_inactive.emit(motor_id)
            return False

    def _update_servo_drag_target(self, motor_id, value):
        """Direct sync write to the SDK shared cache."""
        if self.current_mode != MODE_POSITION or not self.device:
            return
        if motor_id in self._servo_drag_blocked_until_release:
            return
        if motor_id < len(self._collision_active) and self._collision_active[motor_id]:
            self._handle_servo_drag_inactive(motor_id)
            return
        if motor_id not in self._active_servo_drags:
            return
        self._servo_drag_latest_targets[motor_id] = value
        if motor_id in self._servo_drag_starting:
            return
        self._try_update_servo_drag(self.device, self.slave_id, motor_id, value)

    def _stop_servo_drag(self, motor_id, value):
        if self.current_mode != MODE_POSITION or not self.device:
            return
        if motor_id not in self._active_servo_drags:
            return
        final_value = value
        was_last_drag = len(self._active_servo_drags) == 1
        self._servo_drag_latest_targets[motor_id] = final_value
        self._servo_drag_pending_stop[motor_id] = final_value
        self._active_servo_drags.discard(motor_id)
        self._update_finger_collision_state()
        self._update_collision_ui_timer()
        token = self._servo_drag_tokens.get(motor_id)
        if was_last_drag:
            self._end_servo_drag_control_priority()
        if motor_id in self._servo_drag_starting:
            return
        device = self.device
        slave_id = self.slave_id
        self._run_servo_drag_async(
            motor_id,
            lambda: self._stop_servo_drag_task(device, slave_id, motor_id, final_value, token),
        )

    def _get_servo_drag_stop_target(self, motor_id):
        target = self._servo_drag_latest_targets.get(motor_id)
        if target is not None:
            return target
        for group in getattr(self, "finger_groups", {}).values():
            slider = group.motor_sliders.get(motor_id)
            if slider is not None:
                return slider.spin.value()
        return 0.0

    def _cancel_servo_drag_locally(self, motor_id, cancel_sdk_stream=False, restore_control_priority=True):
        if motor_id not in self._active_servo_drags and motor_id not in self._servo_drag_starting:
            return
        final_value = self._get_servo_drag_stop_target(motor_id)
        token = self._servo_drag_tokens.get(motor_id)
        was_last_drag = len(self._active_servo_drags) == 1 and motor_id in self._active_servo_drags
        self._active_servo_drags.discard(motor_id)
        self._servo_drag_starting.discard(motor_id)
        self._servo_drag_latest_targets.pop(motor_id, None)
        self._clear_servo_drag_timing(motor_id)
        self._servo_drag_tokens.pop(motor_id, None)
        self._servo_drag_pending_stop.pop(motor_id, None)
        if was_last_drag and restore_control_priority:
            self._end_servo_drag_control_priority()
        self._update_finger_collision_state()
        self._update_collision_ui_timer()
        if cancel_sdk_stream and self.device and token is not None:
            device = self.device
            slave_id = self.slave_id
            self._run_servo_drag_async(
                motor_id,
                lambda: self._cancel_servo_drag_task(device, slave_id, motor_id, token),
            )

    def _block_servo_drag_until_release(self, motor_id):
        self._servo_drag_blocked_until_release.add(motor_id)

    def _release_servo_drag_block(self, motor_id):
        self._servo_drag_blocked_until_release.discard(motor_id)

    def _handle_servo_drag_inactive(self, motor_id):
        if motor_id not in self._active_servo_drags and motor_id not in self._servo_drag_starting:
            self._poll_collision_state(force=True)
            return
        self._block_servo_drag_until_release(motor_id)
        self._cancel_servo_drag_locally(motor_id)
        self._poll_collision_state(force=True)

    def _handle_servo_drag_stopped(self, motor_id, token):
        if not self._is_servo_drag_token_current(motor_id, token):
            return
        self._servo_drag_starting.discard(motor_id)
        self._servo_drag_latest_targets.pop(motor_id, None)
        self._clear_servo_drag_timing(motor_id)
        self._servo_drag_tokens.pop(motor_id, None)
        self._servo_drag_pending_stop.pop(motor_id, None)
        self._update_finger_collision_state()
        self._update_collision_ui_timer()
        self._poll_collision_state(force=True)

    async def _stop_servo_drag_task(self, device, slave_id, motor_id, value, token):
        current_token = self._servo_drag_tokens.get(motor_id)
        if current_token is not None and current_token != token:
            return
        try:
            await self._await_servo_drag_sdk(
                f"stop M{motor_id:02d}",
                lambda: device.stop_servo_drag(slave_id, motor_id, value),
            )
        except asyncio.TimeoutError:
            print(f"[ServoDrag] stop M{motor_id:02d} timed out; clearing local drag state")
        self.sig_servo_drag_stopped.emit(motor_id, token)

    async def _cancel_servo_drag_task(self, device, slave_id, motor_id, token):
        try:
            await self._call_cancel_servo_drag(device, slave_id, motor_id)
        except asyncio.TimeoutError:
            print(f"[ServoDrag] cancel M{motor_id:02d} timed out; local drag state already cleared")
        except Exception as e:
            logger.warning("[ServoDrag] cancel M%02d failed after local state cleared: %s", motor_id, e)

    async def _call_cancel_servo_drag(self, device, slave_id, motor_id):
        cancel_fn = getattr(device, "cancel_servo_drag", None) or getattr(device, "cancel_drag", None)
        if not callable(cancel_fn):
            logger.info(
                "[ServoDrag] cancel M%02d requested, but SDK has no cancel_servo_drag",
                motor_id,
            )
            return
        await self._await_servo_drag_sdk(
            f"cancel M{motor_id:02d}",
            lambda: cancel_fn(slave_id, motor_id),
        )

    def _stop_all_servo_drags(self):
        for motor_id in list(self._active_servo_drags):
            target = 0.0
            for group in self.finger_groups.values():
                if motor_id in group.motor_sliders:
                    target = group.motor_sliders[motor_id].spin.value()
                    break
            self._stop_servo_drag(motor_id, target)
        self._active_servo_drags.clear()
        self._servo_drag_starting.clear()
        self._servo_drag_pending_stop.clear()
        self._servo_drag_blocked_until_release.clear()
        self._servo_drag_stall_counts.clear()
        self._servo_drag_started_at.clear()
        self._servo_drag_first_stall_at.clear()
        self._servo_drag_first_stall_seq.clear()
        self._update_finger_collision_state()
        self._update_collision_ui_timer()

    def _begin_servo_drag_control_priority(self):
        motor_freq = None
        if threading.current_thread() is not threading.main_thread():
            self.sig_control_priority.emit(True, motor_freq or 0)
            return
        if self.shared_data and hasattr(self.shared_data, "begin_control_priority"):
            if motor_freq is not None:
                self.shared_data.begin_control_priority(motor_freq=motor_freq)
            else:
                self.shared_data.begin_control_priority()

    def _end_servo_drag_control_priority(self):
        if threading.current_thread() is not threading.main_thread():
            self.sig_control_priority.emit(False, 0)
            return
        if self.shared_data and hasattr(self.shared_data, "end_control_priority"):
            self.shared_data.end_control_priority()

    def _set_servo_drag_control_priority(self, enabled, motor_freq=0):
        if enabled:
            if self.shared_data and hasattr(self.shared_data, "begin_control_priority"):
                if motor_freq > 0:
                    self.shared_data.begin_control_priority(motor_freq=motor_freq)
                else:
                    self.shared_data.begin_control_priority()
        else:
            if self.shared_data and hasattr(self.shared_data, "end_control_priority"):
                self.shared_data.end_control_priority()

    async def _send_motor_command(self, motor_id, value):
        try:
            device = self.device
            sid = self.slave_id
            if self.current_mode == MODE_POSITION:
                await device.set_joint_position(sid, motor_id, value)
            elif self.current_mode == MODE_CURRENT:
                await device.set_joint_current(sid, motor_id, value)
            elif self.current_mode == MODE_IMPEDANCE:
                # ControlMode.Impedance=4, param = coefficient × 100
                await device.single_joint_control(sid, motor_id, 4, int(value * 100))
            elif self.current_mode == MODE_DAMPING:
                # ControlMode.Damping=5, param = coefficient × 100
                await device.single_joint_control(sid, motor_id, 5, int(value * 100))
        except Exception as e:
            print(f"[Motor] Send command failed (motor {motor_id}): {e}")

    def _on_mit_value_changed(self, motor_id, params):
        device = self.device
        if not device:
            return
        run_async(lambda: self._send_mit_command(motor_id, params))

    async def _send_mit_command(self, motor_id, params):
        try:
            device = self.device
            sid = self.slave_id
            await device.set_joint_mit(
                sid, motor_id,
                params['position'], params['velocity'], params['current'],
                params['kp'], params['kd']
            )
        except Exception as e:
            print(f"[Motor] MIT command failed (motor {motor_id}): {e}")

    def _on_mit_apply_all_gains(self):
        kp = self.mit_global_kp.value()
        kd = self.mit_global_kd.value()
        for group in self.mit_groups.values():
            for row in group.motor_rows.values():
                row.set_gains_silent(kp, kd)

    # ========================================================================
    # Status updates from SharedDataManager (non-blocking buffer reads)
    # ========================================================================

    def _update_status_from_shared(self):
        """Update motor status from shared data manager (non-blocking read)"""
        if not self.shared_data:
            return

        try:
            if hasattr(self, "fps_badge") and self.fps_badge is not None:
                motor_fps = self.shared_data.get_motor_fps() if self.shared_data else 0.0
                if motor_fps > 0:
                    fps_text = f"FPS: {motor_fps:.1f}"
                else:
                    fps_text = "FPS: --"
                if self.fps_badge.text() != fps_text:
                    self.fps_badge.setText(fps_text)

            status = self.shared_data.get_latest_revo3_motor()
            if not status:
                return
            if self._last_motor_online == 0:
                return
            status_sequence = (
                self.shared_data.get_latest_revo3_motor_sequence()
                if hasattr(self.shared_data, "get_latest_revo3_motor_sequence")
                else 0
            )
            is_new_sample = status_sequence != self._last_motor_status_sequence
            if is_new_sample:
                self._last_motor_status_sequence = status_sequence
                self._last_motor_status_sample_time = time.monotonic()

            # Choose values based on mode
            if self.current_mode == MODE_POSITION:
                values = status.positions_deg
            elif self.current_mode == MODE_CURRENT:
                values = status.currents_ma
            elif self.current_mode == MODE_MIT:
                values = status.positions_deg  # Show position as primary status for MIT
            elif self.current_mode == MODE_TRAJECTORY:
                values = status.positions_deg
            else:
                values = []

            # Update motor slider groups (Position/Velocity/Current)
            if self.current_mode <= MODE_CURRENT:
                for name, group in self.finger_groups.items():
                    for mid in get_revo3_finger_motors().get(name, []):
                        if mid < len(values):
                            group.update_motor_status(mid, values[mid])

            # Update MIT groups
            elif self.current_mode == MODE_MIT:
                for name, group in self.mit_groups.items():
                    for mid in get_revo3_finger_motors().get(name, []):
                        if mid < len(values):
                            group.update_motor_status(mid, values[mid])

            self._poll_collision_state()

        except Exception as e:
            print(f"[Motor] Update status failed: {e}")

    # ========================================================================
    # Device management
    # ========================================================================

    def set_device(self, device, slave_id, device_info=None, shared_data=None):
        """Set device for Revo3 motor control. Uses SharedDataManager for status polling."""
        self.shared_data = shared_data
        self._device = device
        self._slave_id = slave_id
        self._device_info = device_info
        self.diag_consecutive_failures = 0
        if device and shared_data:
            self.update_timer.start()
            self._update_collision_ui_timer()
            # Populate FW/SN from device_info into info panels
            if device_info:
                fw = getattr(device_info, 'firmware_version', '') or ''
                sn = getattr(device_info, 'serial_number', '') or ''
                model = getattr(device_info, 'model', None)
                sku = getattr(device_info, 'hand_side', None)
                touch_layout = touch_layout_display_name(device)
                for panel in [self.info_panel, self.mit_info_panel]:
                    panel.update_info(
                        fw=fw,
                        sn=sn,
                        model=model,
                        sku=sku,
                        touch_layout=touch_layout,
                    )
            # Initial diagnostics read + start periodic refresh
            QTimer.singleShot(500, self._on_read_diagnostics)
            self.diag_timer.start()

            # Sync hardware toggles via 2.0 DeviceConfig API
            async def fetch_toggles():
                if not self.device:
                    return
                try:
                    config = await self.device.get_config_snapshot()
                    ac = config.power_on_auto_calibration_enabled
                    ts = getattr(config, 'touch_screen_enabled', getattr(config, 'touch_screen', self.touch_screen_cb.isChecked()))
                    bz = getattr(config, 'buzzer_enabled', getattr(config, 'buzzer', self.buzzer_cb.isChecked()))
                    vib = getattr(config, 'vibration_enabled', getattr(config, 'vibration', self.vibration_cb.isChecked()))
                    tm = getattr(config, 'teaching_mode_enabled', getattr(config, 'teaching_mode', self.teaching_mode_cb.isChecked()))
                    es = getattr(config, 'software_stop_enabled', getattr(config, 'software_estop', self.software_e_stop_cb.isChecked()))
                    ub = getattr(config, 'use_broadcast_id', self.use_broadcast_id_cb.isChecked())
                    self.sig_toggles_fetched.emit(ac, ts, bz, vib, tm, es, ub)
                except Exception as e:
                    print(f"[Settings] Failed to sync toggles: {e}")

            run_async(fetch_toggles)
        else:
            self.update_timer.stop()
            self.diag_timer.stop()
            self.collision_ui_timer.stop()

    def clear_device(self):
        self._stop_all_servo_drags()
        self.update_timer.stop()
        self.diag_timer.stop()
        self.collision_ui_timer.stop()
        if hasattr(self, "fps_badge") and self.fps_badge is not None:
            fps_text = "FPS: --"
            if self.fps_badge.text() != fps_text:
                self.fps_badge.setText(fps_text)
        self.diag_consecutive_failures = 0
        self._collision_active = [False] * REVO3_ULTRA_JOINT_COUNT
        self._servo_drag_stall_counts.clear()
        self._servo_drag_started_at.clear()
        self._servo_drag_first_stall_at.clear()
        self._servo_drag_first_stall_seq.clear()
        self._last_motor_online = None
        self._last_motor_temps = []
        self._last_motor_fault_codes = []
        self._last_finger_state_signature = None
        self._last_finger_state_log_signature = None
        self._last_finger_state_log_time = 0.0
        self._last_motor_status_sequence = 0
        self._last_motor_status_sample_time = 0.0
        self._last_motor_fault_debug_signature = None
        self._last_motor_fault_debug_log_time = 0.0
        self._update_collision_status_label()
        self._update_finger_collision_state()
        self.shared_data = None
        self._device = None
        # Clear all info panels
        for panel in [self.info_panel, self.mit_info_panel]:
            panel.clear_info()

    def _update_toggles_ui(self, ac, ts, bz, vib, tm, es, ub):
        self.auto_calib_cb.blockSignals(True)
        self.touch_screen_cb.blockSignals(True)
        self.buzzer_cb.blockSignals(True)
        self.vibration_cb.blockSignals(True)
        self.teaching_mode_cb.blockSignals(True)
        self.software_e_stop_cb.blockSignals(True)
        self.use_broadcast_id_cb.blockSignals(True)

        self.auto_calib_cb.setChecked(ac)
        self.touch_screen_cb.setChecked(ts)
        self.buzzer_cb.setChecked(bz)
        self.vibration_cb.setChecked(vib)
        self.teaching_mode_cb.setChecked(tm)
        self.software_e_stop_cb.setChecked(es)
        self.use_broadcast_id_cb.setChecked(ub)

        self.auto_calib_cb.blockSignals(False)
        self.touch_screen_cb.blockSignals(False)
        self.buzzer_cb.blockSignals(False)
        self.vibration_cb.blockSignals(False)
        self.teaching_mode_cb.blockSignals(False)
        self.software_e_stop_cb.blockSignals(False)
        self.use_broadcast_id_cb.blockSignals(False)

    # ========================================================================
    # Global actions
    # ========================================================================

    def _on_finger_action(self, finger_name, action):
        """Handle per-finger Open/Close button click."""
        if self.current_mode != MODE_POSITION or not self.device:
            return
        group = self.finger_groups.get(finger_name)
        if not group:
            return
        # Read current positions as baseline, then modify only this finger
        targets = [0.0] * get_revo3_motor_count()
        for name, g in self.finger_groups.items():
            for mid, slider in g.motor_sliders.items():
                targets[mid] = slider.spin.value()
        # Override this finger's targets
        for mid, slider in group.motor_sliders.items():
            if action == "open":
                target = get_motor_open_position(mid)
            else:
                target = get_motor_close_position(mid)
            targets[mid] = target
            slider.set_value_silent(target)
        run_async(lambda: self.device.set_all_motor_positions(self.slave_id, targets))

    def _move_all_to_ratio(self, ratio):
        """Move all motors to a specific ratio of their max position (0.0=open, 1.0=close)"""
        if not self.device or self.current_mode not in (MODE_POSITION, MODE_TRAJECTORY):
            return

        targets = [0.0] * get_revo3_motor_count()
        for name, group in self.finger_groups.items():
            for mid, slider in group.motor_sliders.items():
                open_pos = get_motor_open_position(mid)
                close_pos = get_motor_close_position(mid)
                target = open_pos + (close_pos - open_pos) * ratio
                targets[mid] = target
                slider.set_value_silent(target)

        if self.current_mode == MODE_POSITION:
            run_async(lambda: self.device.set_all_motor_positions(self.slave_id, targets))
        elif self.current_mode == MODE_TRAJECTORY:
            p = self._get_traj_params()
            if p['speed'] > 0:
                run_async(lambda: self.device.move_hand_with_speed_and_gains(
                    self.slave_id, targets, p['speed'], p['dt'], p['kp'], p['kd']
                ))
            else:
                run_async(lambda: self.device.move_hand_with_gains(
                    self.slave_id, targets, p['T'], p['dt'], p['kp'], p['kd']
                ))

    def _open_all(self):
        """Open hand: flexion joints → 0°, abduction/rotation → neutral (0°)"""
        print("[MotorControlPanel] 'Open All' (全部张开) clicked")
        self._move_all_to_ratio(0.0)

    def _close_all(self):
        """Close hand: flexion joints → max, abduction/rotation → neutral (0°)"""
        print("[MotorControlPanel] 'Close All' (全部闭合) clicked")
        self._move_all_to_ratio(1.0)

    def _default_gesture(self):
        """Invoke hardware default gesture via reset_default_gesture"""
        print("[MotorControlPanel] 'Default Gesture' clicked")
        if not self.device:
            return
        run_async(lambda: self.device.reset_finger_defaults(self.slave_id))

    def _zero_all(self):
        """All controls -> 0"""
        print("[MotorControlPanel] 'Zero All' clicked: Resetting all joints to 0")
        if not self.device:
            return

        if self.current_mode in (MODE_POSITION, MODE_CURRENT, MODE_IMPEDANCE, MODE_DAMPING, MODE_TRAJECTORY):
            targets = [0.0] * get_revo3_motor_count()
            for group in self.finger_groups.values():
                for slider in group.motor_sliders.values():
                    slider.set_value_silent(0.0)

            if self.current_mode == MODE_POSITION:
                run_async(lambda: self.device.set_all_motor_positions(self.slave_id, targets))
            elif self.current_mode == MODE_CURRENT:
                run_async(lambda: self.device.set_all_motor_currents(self.slave_id, targets))
            elif self.current_mode in (MODE_IMPEDANCE, MODE_DAMPING):
                mode_val = 4 if self.current_mode == MODE_IMPEDANCE else 5
                params = [0] * 21  # 21 joints, all zero
                run_async(lambda: self.device.multi_joint_control(self.slave_id, mode_val, params))
            elif self.current_mode == MODE_TRAJECTORY:
                p = self._get_traj_params()
                if p['speed'] > 0:
                    run_async(lambda: self.device.move_hand_with_speed_and_gains(
                        self.slave_id, targets, p['speed'], p['dt'], p['kp'], p['kd']))
                else:
                    run_async(lambda: self.device.move_hand_with_gains(
                        self.slave_id, targets, p['T'], p['dt'], p['kp'], p['kd']))

        elif self.current_mode == MODE_MIT:
            for group in self.mit_groups.values():
                group.zero_all()
            # Send batch zeroes
            targets = [0.0] * get_revo3_motor_count()
            run_async(lambda: self.device.set_all_mit_params(
                self.slave_id, targets, targets, targets, targets, targets))

    # ========================================================================
    # Trajectory Execution
    # ========================================================================

    def _get_traj_params(self):
        """Helper to get global trajectory params"""
        return {
            'T': self.spin_T.value() / 1000.0,
            'speed': self.spin_speed.value(),
            'dt': self.spin_dt.value() / 1000.0,
            'kp': self.spin_kp.value(),
            'kd': self.spin_kd.value()
        }

    def _on_run_motor_trajectory(self, motor_id, target):
        if not self.device: return
        p = self._get_traj_params()
        if p['speed'] > 0:
            run_async(lambda: self.device.move_joint_with_speed_and_gains(
                self.slave_id, motor_id, target, p['speed'], p['dt'], p['kp'], p['kd']
            ))
        else:
            run_async(lambda: self.device.move_joint_with_gains(
                self.slave_id, motor_id, target, p['T'], p['dt'], p['kp'], p['kd']
            ))

    def _on_run_finger_trajectory(self, finger_name, targets_dict):
        if not self.device: return
        p = self._get_traj_params()

        # Build global targets list
        targets = [0.0] * get_revo3_motor_count()
        # Read current shared data positions to avoid moving other fingers to 0
        status = self.shared_data.get_latest_revo3_motor() if self.shared_data else None
        if status:
            for i in range(get_revo3_motor_count()):
                targets[i] = status.positions_deg[i]

        # Override with finger targets
        for mid, val in targets_dict.items():
            targets[mid] = val

        if p['speed'] > 0:
            run_async(lambda: self.device.move_hand_with_speed_and_gains(
                self.slave_id, targets, p['speed'], p['dt'], p['kp'], p['kd']
            ))
        else:
            run_async(lambda: self.device.move_hand_with_gains(
                self.slave_id, targets, p['T'], p['dt'], p['kp'], p['kd']
            ))

    def _on_run_all(self):
        if not self.device or self.current_mode != MODE_TRAJECTORY:
            return
        p = self._get_traj_params()
        targets = [0.0] * get_revo3_motor_count()
        for group in self.finger_groups.values():
            for mid, slider in group.motor_sliders.items():
                targets[mid] = slider.spin.value()

        if p['speed'] > 0:
            run_async(lambda: self.device.move_hand_with_speed_and_gains(
                self.slave_id, targets, p['speed'], p['dt'], p['kp'], p['kd']
            ))
        else:
            run_async(lambda: self.device.move_hand_with_gains(
                self.slave_id, targets, p['T'], p['dt'], p['kp'], p['kd']
            ))
