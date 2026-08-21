"""VisionTouch Independent Window

Displays VisionTouch sensor data in a separate window.
Can be launched from main window's Tools menu.

Features:
- 6D Force/Torque visualization
- Depth map heatmap
- Raw image display (Warped, Diff, Marker)
"""

import sys
import time
import threading
from pathlib import Path
from typing import Optional

import numpy as np
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTabWidget, QLabel, QPushButton, QStatusBar,
    QGroupBox, QGridLayout, QComboBox, QFileDialog, QProgressBar
)
from PySide6.QtCore import Qt, Signal, QObject, QTimer
from PySide6.QtGui import QImage, QPixmap

# Add parent directory to path for SDK import
sys.path.insert(0, str(Path(__file__).parent.parent))

# Try to import real SDK, fall back to mock
MOCK_MODE = False
try:
    from pyvitaisdk import VTSensor, VTSDeviceFinder, VTSDataType, VTSError, VTSensorType
    HAS_VITAI_SDK = True
    print("✅ Using optional vts_* runtime")
except ImportError:
    HAS_VITAI_SDK = False
    try:
        try:
            from .vision_touch_mock import (
                VTSensor, VTSDeviceFinder, VTSDataType, VTSError, VTSensorType
            )
        except ImportError:
            from gui.vision_touch_mock import (
                VTSensor, VTSDeviceFinder, VTSDataType, VTSError, VTSensorType
            )
        MOCK_MODE = True
        print("⚠ Optional vts_* runtime not found, using Mock Device")
        print("See python/gui/README.md for runtime setup")
    except ImportError:
        print("❌ Error: Neither real nor mock VisionTouch available")
        VTSensor = None
        VTSDeviceFinder = None
try:
    from .touch_common import logger, COLORS
    from .i18n import tr
except ImportError:
    from gui.touch_common import logger, COLORS
    from gui.i18n import tr


def extract_force6d_mean(force6d_vector: np.ndarray) -> np.ndarray:
    """Normalize VisionTouch force data to [Fx, Fy, Fz, Mx, My, Mz]."""
    arr = np.asarray(force6d_vector)
    if arr.ndim == 1:
        if arr.shape[0] >= 6:
            return arr[:6].astype(np.float32)
        out = np.zeros(6, dtype=np.float32)
        out[:arr.shape[0]] = arr.astype(np.float32)
        return out

    if arr.shape[-1] >= 6:
        return arr[..., :6].reshape(-1, 6).mean(axis=0).astype(np.float32)

    flat = arr.reshape(-1)
    out = np.zeros(6, dtype=np.float32)
    take = min(6, flat.shape[0])
    out[:take] = flat[:take].astype(np.float32)
    return out


class VisionTouchSignals(QObject):
    """Signals for thread-safe GUI updates"""
    sensors_found = Signal(object)  # selected SN list
    init_progress = Signal(int, int, str)  # (index, total, sn)
    sensor_initialized = Signal(str, object)  # (sn, VTSensor)
    sensor_ready = Signal(str)  # sn
    init_error = Signal(str, str)  # (sn/context, message)
    init_finished = Signal(object, object)  # (vision_devices dict, selected SN list)
    sensor_data_ready = Signal(str, object)  # (sn, data dict)
    stats_ready = Signal(int, int, float)  # (device_count, collected_count, round_seconds)
    force_data_ready = Signal(np.ndarray)  # 6D force vector
    depth_data_ready = Signal(np.ndarray)  # Depth map
    image_data_ready = Signal(dict)  # Images dict
    slip_data_ready = Signal(object, object)  # (slip_state, image)
    xyz_data_ready = Signal(np.ndarray)  # XYZ vector
    marker_data_ready = Signal(np.ndarray, np.ndarray, np.ndarray, object)  # (origin, current, offset, image)
    status_message = Signal(str)  # Status message
    error_occurred = Signal(str)  # Error message


class VisionTouchDataCollector:
    """Background thread for VisionTouch data collection"""
    
    def __init__(self, vision_devices, signals: VisionTouchSignals, collect_force: bool = False):
        self.vision_devices = vision_devices
        self.signals = signals
        self.collect_force = collect_force
        self.running = False
        self.thread = None
        
    def start(self):
        """Start data collection thread"""
        if self.running:
            return
        self.running = True
        self.thread = threading.Thread(target=self._collect_loop, daemon=True)
        self.thread.start()
        logger.info("VisionTouch data collection started")
        
    def stop(self):
        """Stop data collection thread"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=1.0)
        logger.info("VisionTouch data collection stopped")
        
    def _collect_loop(self):
        """Data collection loop for all connected VisionTouch sensors."""
        while self.running:
            loop_started = time.monotonic()
            collected_count = 0
            for sn, vision_device in list(self.vision_devices.items()):
                if not self.running:
                    break
                try:
                    data_types = [
                        VTSDataType.DEPTH_MAP,
                        VTSDataType.RAW_IMG,
                        VTSDataType.CALIBRATE_IMG,
                        VTSDataType.WARPED_IMG,
                        VTSDataType.DIFF_IMG,
                        VTSDataType.MARKER_IMG,
                        VTSDataType.SLIP_STATE,
                        VTSDataType.XYZ_VECTOR,
                        VTSDataType.MARKER_ORIGIN_VECTOR,
                        VTSDataType.MARKER_CURRENT_VECTOR,
                        VTSDataType.MARKER_OFFSET_VECTOR,
                    ]
                    if self.collect_force:
                        data_types.insert(0, VTSDataType.FORCE6D_VECTOR)
                    data = vision_device.collect_sensor_data(*data_types)
                    collected_count += 1
                    self.signals.sensor_data_ready.emit(sn, data)
                except VTSError as e:
                    self.signals.error_occurred.emit(f"{sn}: VTSError: {e}")
                    logger.error(f"VisionTouch collection error for {sn}: {e}")
                except Exception as e:
                    self.signals.error_occurred.emit(f"{sn}: Error: {e}")
                    logger.error(f"Unexpected VisionTouch collection error for {sn}: {e}")

            round_seconds = max(1e-6, time.monotonic() - loop_started)
            self.signals.stats_ready.emit(len(self.vision_devices), collected_count, round_seconds)
            time.sleep(0.050)


class Force6DWidget(QWidget):
    """6D Force/Torque display widget"""
    
    def __init__(self):
        super().__init__()
        self.current_values = np.zeros(6)
        self._setup_ui()
        
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(12)
        
        # Title
        title = QLabel("6D Force & Torque")
        title.setStyleSheet("font-size: 16px; font-weight: bold; color: #5D9CEC;")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        
        # Force group
        force_group = QGroupBox("Force (N)")
        force_layout = QGridLayout(force_group)
        force_layout.setSpacing(8)
        
        self.force_labels = {}
        force_names = ['Fx', 'Fy', 'Fz']
        force_colors = ['#e74c3c', '#27ae60', '#3498db']
        
        for i, (name, color) in enumerate(zip(force_names, force_colors)):
            name_lbl = QLabel(f"{name}:")
            name_lbl.setStyleSheet(f"font-weight: bold; color: {color}; font-size: 14px;")
            
            value_lbl = QLabel("0.00")
            value_lbl.setStyleSheet(
                "font-size: 18px; font-family: 'Courier New'; "
                "color: #2c3e50; background: #ecf0f1; padding: 4px 8px; border-radius: 4px;"
            )
            value_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            value_lbl.setMinimumWidth(100)
            
            force_layout.addWidget(name_lbl, i, 0)
            force_layout.addWidget(value_lbl, i, 1)
            self.force_labels[name] = value_lbl

        norm_name_lbl = QLabel("|F|:")
        norm_name_lbl.setStyleSheet("font-weight: bold; color: #5D9CEC; font-size: 14px;")
        norm_value_lbl = QLabel("0.00")
        norm_value_lbl.setStyleSheet(
            "font-size: 18px; font-family: 'Courier New'; "
            "color: #2c3e50; background: #ecf0f1; padding: 4px 8px; border-radius: 4px;"
        )
        norm_value_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        norm_value_lbl.setMinimumWidth(100)
        force_layout.addWidget(norm_name_lbl, len(force_names), 0)
        force_layout.addWidget(norm_value_lbl, len(force_names), 1)
        self.force_labels["|F|"] = norm_value_lbl
        
        layout.addWidget(force_group)
        
        # Torque group
        torque_group = QGroupBox("Torque (N·m)")
        torque_layout = QGridLayout(torque_group)
        torque_layout.setSpacing(8)
        
        torque_names = ['Mx', 'My', 'Mz']
        torque_colors = ['#e67e22', '#9b59b6', '#1abc9c']
        
        for i, (name, color) in enumerate(zip(torque_names, torque_colors)):
            name_lbl = QLabel(f"{name}:")
            name_lbl.setStyleSheet(f"font-weight: bold; color: {color}; font-size: 14px;")
            
            value_lbl = QLabel("0.000")
            value_lbl.setStyleSheet(
                "font-size: 18px; font-family: 'Courier New'; "
                "color: #2c3e50; background: #ecf0f1; padding: 4px 8px; border-radius: 4px;"
            )
            value_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            value_lbl.setMinimumWidth(100)
            
            torque_layout.addWidget(name_lbl, i, 0)
            torque_layout.addWidget(value_lbl, i, 1)
            self.force_labels[name] = value_lbl
        
        layout.addWidget(torque_group)
        
        # Add pyqtgraph visualization if available
        try:
            try:
                from .touch_chart_force6d import Force6DChart
            except ImportError:
                from gui.touch_chart_force6d import Force6DChart
            self.force_chart = Force6DChart(
                "VisionTouch",
                components=6,
                accent_color=(100, 255, 100),
            )
            layout.addWidget(self.force_chart, 1)
        except ImportError as e:
            logger.warning(f"pyqtgraph or its dependencies (e.g. PyOpenGL) not available: {e}. Using simple display.")
            self.force_chart = None
        
        layout.addStretch()
        
    def update_data(self, force6d: np.ndarray):
        """Update 6D force display
        
        Args:
            force6d: np.ndarray of shape (6,) - [Fx, Fy, Fz, Mx, My, Mz]
        """
        if not self.isVisible():
            return
        force6d = extract_force6d_mean(force6d)
        
        self.current_values = force6d
        
        # Update text labels
        names = ['Fx', 'Fy', 'Fz', 'Mx', 'My', 'Mz']
        for i, name in enumerate(names):
            if i < 3:  # Force
                self.force_labels[name].setText(f"{force6d[i]:+.2f}")
            else:  # Torque
                self.force_labels[name].setText(f"{force6d[i]:+.3f}")
        force_norm = float(np.linalg.norm(force6d[:3]))
        self.force_labels["|F|"].setText(f"{force_norm:.2f}")
        
        # Update chart if available
        if self.force_chart:
            self.force_chart.add_data_array(force6d)


class DepthMapWidget(QWidget):
    """Depth map heatmap display"""
    
    def __init__(self):
        super().__init__()
        self._setup_ui()
        
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        
        # Title
        title = QLabel("Depth Map")
        title.setStyleSheet("font-size: 16px; font-weight: bold; color: #5D9CEC;")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        
        # Image display
        self.image_label = QLabel("No depth data")
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setStyleSheet("background: #2c3e50; color: #ecf0f1; font-size: 14px;")
        self.image_label.setMinimumSize(400, 300)
        layout.addWidget(self.image_label, 1)
        
    def update_data(self, depth_map: np.ndarray):
        """Update depth map visualization
        
        Args:
            depth_map: np.ndarray of shape (H, W), dtype=float32
        """
        if not self.isVisible():
            return
        if depth_map is None or depth_map.size == 0:
            return
        
        # Normalize to 0-255
        depth_max = max(1.0, np.max(depth_map))
        depth_norm = (depth_map / depth_max * 255).astype(np.uint8)
        
        # Apply colormap (convert to RGB)
        import cv2
        depth_colored = cv2.applyColorMap(depth_norm, cv2.COLORMAP_JET)
        depth_rgb = cv2.cvtColor(depth_colored, cv2.COLOR_BGR2RGB)
        
        # Convert to QPixmap
        h, w, ch = depth_rgb.shape
        bytes_per_line = ch * w
        q_image = QImage(depth_rgb.data, w, h, bytes_per_line, QImage.Format_RGB888)
        pixmap = QPixmap.fromImage(q_image)
        
        # Scale to fit label
        scaled_pixmap = pixmap.scaled(
            self.image_label.size(),
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation
        )
        self.image_label.setPixmap(scaled_pixmap)


class ImageViewWidget(QWidget):
    """Raw image display (Warped, Diff, Marker)"""
    
    def __init__(self):
        super().__init__()
        self._setup_ui()
        
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        
        # Title
        title = QLabel("Sensor Images")
        title.setStyleSheet("font-size: 16px; font-weight: bold; color: #5D9CEC;")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        
        # Image tabs
        self.image_tabs = QTabWidget()
        
        # Raw image
        self.raw_label = QLabel("No image")
        self.raw_label.setAlignment(Qt.AlignCenter)
        self.raw_label.setStyleSheet("background: #2c3e50; color: #ecf0f1;")
        self.raw_label.setMinimumSize(400, 300)
        self.image_tabs.addTab(self.raw_label, "Raw")
        
        # Calibrate image
        self.calibrate_label = QLabel("No image")
        self.calibrate_label.setAlignment(Qt.AlignCenter)
        self.calibrate_label.setStyleSheet("background: #2c3e50; color: #ecf0f1;")
        self.calibrate_label.setMinimumSize(400, 300)
        self.image_tabs.addTab(self.calibrate_label, "Calibrate")
        
        # Warped image
        self.warped_label = QLabel("No image")
        self.warped_label.setAlignment(Qt.AlignCenter)
        self.warped_label.setStyleSheet("background: #2c3e50; color: #ecf0f1;")
        self.warped_label.setMinimumSize(400, 300)
        self.image_tabs.addTab(self.warped_label, "Warped")
        
        # Diff image
        self.diff_label = QLabel("No image")
        self.diff_label.setAlignment(Qt.AlignCenter)
        self.diff_label.setStyleSheet("background: #2c3e50; color: #ecf0f1;")
        self.diff_label.setMinimumSize(400, 300)
        self.image_tabs.addTab(self.diff_label, "Diff")
        
        # Marker image
        self.marker_label = QLabel("No image")
        self.marker_label.setAlignment(Qt.AlignCenter)
        self.marker_label.setStyleSheet("background: #2c3e50; color: #ecf0f1;")
        self.marker_label.setMinimumSize(400, 300)
        self.image_tabs.addTab(self.marker_label, "Marker")
        
        layout.addWidget(self.image_tabs, 1)
        
    def update_data(self, images: dict):
        """Update image displays
        
        Args:
            images: dict with keys 'warped', 'diff', 'marker'
        """
        import cv2
        
        for key, label in [
            ('raw', self.raw_label),
            ('calibrate', self.calibrate_label),
            ('warped', self.warped_label),
            ('diff', self.diff_label),
            ('marker', self.marker_label)
        ]:
            if key in images:
                img = images[key]
                if img is not None and img.size > 0:
                    # Convert BGR to RGB
                    img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
                    h, w, ch = img_rgb.shape
                    bytes_per_line = ch * w
                    q_image = QImage(img_rgb.data, w, h, bytes_per_line, QImage.Format_RGB888)
                    pixmap = QPixmap.fromImage(q_image)
                    
                    # Scale to fit
                    scaled_pixmap = pixmap.scaled(
                        label.size(),
                        Qt.KeepAspectRatio,
                        Qt.SmoothTransformation
                    )
                    label.setPixmap(scaled_pixmap)


class MultiSensorOverviewWidget(QWidget):
    """Compact force overview for all connected VisionTouch sensors."""

    def __init__(self):
        super().__init__()
        self.rows = {}
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        title = QLabel("VisionTouch Sensors")
        title.setStyleSheet("font-size: 16px; font-weight: bold; color: #5D9CEC;")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        self.grid_widget = QWidget()
        self.grid = QGridLayout(self.grid_widget)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(6)

        headers = ["SN", "|F| N", "Fx", "Fy", "Fz", "Status"]
        for col, text in enumerate(headers):
            label = QLabel(text)
            label.setStyleSheet("font-weight: bold; color: #5D9CEC;")
            self.grid.addWidget(label, 0, col)

        layout.addWidget(self.grid_widget)
        layout.addStretch()

    def set_sensors(self, sns):
        for row_widgets in self.rows.values():
            for widget in row_widgets.values():
                widget.setParent(None)
        self.rows.clear()

        for row, sn in enumerate(sns, start=1):
            widgets = {
                "sn": QLabel(sn),
                "norm": QLabel("--"),
                "fx": QLabel("--"),
                "fy": QLabel("--"),
                "fz": QLabel("--"),
                "status": QLabel("Waiting"),
            }
            for key, widget in widgets.items():
                widget.setMinimumWidth(80 if key != "sn" else 220)
                widget.setStyleSheet("font-family: 'Courier New';")
            for col, key in enumerate(["sn", "norm", "fx", "fy", "fz", "status"]):
                self.grid.addWidget(widgets[key], row, col)
            self.rows[sn] = widgets

    def update_force(self, sn, force6d):
        widgets = self.rows.get(sn)
        if not widgets:
            return
        force6d = extract_force6d_mean(force6d)
        widgets["norm"].setText(f"{float(np.linalg.norm(force6d[:3])):.2f}")
        widgets["fx"].setText(f"{force6d[0]:+.2f}")
        widgets["fy"].setText(f"{force6d[1]:+.2f}")
        widgets["fz"].setText(f"{force6d[2]:+.2f}")
        widgets["status"].setText("OK")
        widgets["status"].setStyleSheet("font-family: 'Courier New'; color: #27ae60;")

    def set_status(self, sn, message):
        widgets = self.rows.get(sn)
        if not widgets:
            return
        widgets["status"].setText(message[:60])
        widgets["status"].setStyleSheet("font-family: 'Courier New'; color: #27ae60;")

    def set_force_disabled(self, sn):
        widgets = self.rows.get(sn)
        if not widgets:
            return
        for key in ["norm", "fx", "fy", "fz"]:
            widgets[key].setText("--")
        widgets["status"].setText("OK (force off)")
        widgets["status"].setStyleSheet("font-family: 'Courier New'; color: #27ae60;")

    def set_error(self, sn, message):
        widgets = self.rows.get(sn)
        if not widgets:
            return
        widgets["status"].setText(message[:60])
        widgets["status"].setStyleSheet("font-family: 'Courier New'; color: #e74c3c;")


class VisionTouchPanel(QWidget):
    """VisionTouch Independent Panel
    
    Displays VisionTouch sensor data. Can be embedded in other windows.
    Can automatically connect to the first available VisionTouch device.
    """
    
    def __init__(self, parent=None, target_sn=None, auto_connect=True, force_model_dir=None, force_model_mode="none"):
        super().__init__(parent)
        self.target_sn = target_sn
        self.auto_connect = auto_connect
        self.force_model_dir = force_model_dir
        self.force_model_mode = force_model_mode
        self.force_enabled = force_model_mode != "none"
        
        self.vision_devices = {}
        self.selected_sn = None
        self.initializing = False
        self.closing = False
        self.init_thread = None
        self.collector: Optional[VisionTouchDataCollector] = None
        self.signals = VisionTouchSignals()
        
        self._setup_ui()
        self._connect_signals()
        
        # Auto-connect on startup
        if self.auto_connect:
            QTimer.singleShot(500, self._auto_connect)
        
    def _setup_ui(self):
        """Setup UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)
        
        # Control bar
        control_bar = QWidget()
        control_layout = QHBoxLayout(control_bar)
        control_layout.setContentsMargins(0, 0, 0, 0)
        
        self.connect_btn = QPushButton("🔌 Connect")
        self.connect_btn.clicked.connect(self._toggle_connection)
        control_layout.addWidget(self.connect_btn)
        
        self.calibrate_btn = QPushButton("📐 Calibrate")
        self.calibrate_btn.clicked.connect(self._calibrate)
        self.calibrate_btn.setEnabled(False)
        control_layout.addWidget(self.calibrate_btn)

        self.sensor_combo = QComboBox()
        self.sensor_combo.setMinimumWidth(240)
        self.sensor_combo.currentTextChanged.connect(self._on_selected_sensor_changed)
        control_layout.addWidget(self.sensor_combo)
        
        control_layout.addStretch()
        
        self.status_label = QLabel("Not connected")
        self.status_label.setStyleSheet(f"color: {COLORS['text_muted']};")
        control_layout.addWidget(self.status_label)
        
        layout.addWidget(control_bar)

        self.model_label = QLabel(
            self._force_model_status_text()
        )
        self.model_label.setStyleSheet(f"color: {COLORS['text_muted']};")
        layout.addWidget(self.model_label)

        model_bar = QWidget()
        model_layout = QHBoxLayout(model_bar)
        model_layout.setContentsMargins(0, 0, 0, 0)
        model_layout.setSpacing(8)

        model_layout.addWidget(QLabel("Force model mode:"))
        self.force_mode_combo = QComboBox()
        self.force_mode_combo.addItem("Disabled (fast)", "none")
        self.force_mode_combo.addItem("Auto load", "auto")
        self.force_mode_combo.addItem("Required", "required")
        mode_index = self.force_mode_combo.findData(self.force_model_mode)
        self.force_mode_combo.setCurrentIndex(max(0, mode_index))
        self.force_mode_combo.currentIndexChanged.connect(self._on_force_mode_changed)
        model_layout.addWidget(self.force_mode_combo)

        self.model_dir_btn = QPushButton("Choose model directory...")
        self.model_dir_btn.clicked.connect(self._choose_force_model_dir)
        model_layout.addWidget(self.model_dir_btn)

        self.clear_model_dir_btn = QPushButton("Clear")
        self.clear_model_dir_btn.clicked.connect(self._clear_force_model_dir)
        model_layout.addWidget(self.clear_model_dir_btn)

        model_layout.addStretch()
        layout.addWidget(model_bar)

        self.init_progress_bar = QProgressBar()
        self.init_progress_bar.setRange(0, 1)
        self.init_progress_bar.setValue(0)
        self.init_progress_bar.setFormat("Idle")
        layout.addWidget(self.init_progress_bar)
        
        # Main tabs
        self.tabs = QTabWidget()

        self.overview_widget = MultiSensorOverviewWidget()
        self.tabs.addTab(self.overview_widget, "📊 " + tr("vts_overview"))
        
        # Tab 1: 6D Force (Most important - force/torque data)
        self.force_widget = Force6DWidget()
        force_tab_name = "💪 6D Force" if self.force_enabled else "💪 6D Force (off)"
        self.tabs.addTab(self.force_widget, force_tab_name)
        
        # Tab 2: Depth Map (Pressure distribution visualization)
        self.depth_widget = DepthMapWidget()
        self.tabs.addTab(self.depth_widget, "🗺 " + tr("vts_depth_map"))
        
        # Tab 3: Slip Detection (Practical feature for grasping)
        try:
            from .vision_touch_widgets import SlipDetectionWidget
        except ImportError:
            from gui.vision_touch_widgets import SlipDetectionWidget
        self.slip_widget = SlipDetectionWidget()
        self.tabs.addTab(self.slip_widget, "⚠ " + tr("vts_slip_detection"))
        
        # Tab 4: Images (Raw sensor images for debugging)
        self.image_widget = ImageViewWidget()
        self.tabs.addTab(self.image_widget, "📷 " + tr("vts_images"))
        
        # Tab 5: 3D View (Advanced visualization)
        try:
            from .vision_touch_widgets import PointCloud3DWidget
        except ImportError:
            from gui.vision_touch_widgets import PointCloud3DWidget
        self.pointcloud_widget = PointCloud3DWidget()
        self.tabs.addTab(self.pointcloud_widget, "🎨 " + tr("vts_3d_view"))
        
        # Tab 6: Marker Tracking (Advanced analysis)
        try:
            from .vision_touch_widgets import MarkerTrackingWidget
        except ImportError:
            from gui.vision_touch_widgets import MarkerTrackingWidget
        self.marker_widget = MarkerTrackingWidget()
        self.tabs.addTab(self.marker_widget, "🎯 " + tr("vts_marker"))
        
        layout.addWidget(self.tabs, 1)
        
        # Status bar
        self.statusbar = QStatusBar()
        self.statusbar.showMessage("Ready")
        layout.addWidget(self.statusbar)
        
    def update_texts(self):
        """Update UI texts for multi-language support"""
        if self.tabs.indexOf(self.overview_widget) >= 0:
            self.tabs.setTabText(self.tabs.indexOf(self.overview_widget), "📊 " + tr("vts_overview"))
        if self.tabs.indexOf(self.force_widget) >= 0:
            self._update_force_tab_text()
        if self.tabs.indexOf(self.depth_widget) >= 0:
            self.tabs.setTabText(self.tabs.indexOf(self.depth_widget), "🗺 " + tr("vts_depth_map"))
        if self.tabs.indexOf(self.slip_widget) >= 0:
            self.tabs.setTabText(self.tabs.indexOf(self.slip_widget), "⚠ " + tr("vts_slip_detection"))
        if self.tabs.indexOf(self.image_widget) >= 0:
            self.tabs.setTabText(self.tabs.indexOf(self.image_widget), "📷 " + tr("vts_images"))
        if self.tabs.indexOf(self.pointcloud_widget) >= 0:
            self.tabs.setTabText(self.tabs.indexOf(self.pointcloud_widget), "🎨 " + tr("vts_3d_view"))
        if self.tabs.indexOf(self.marker_widget) >= 0:
            self.tabs.setTabText(self.tabs.indexOf(self.marker_widget), "🎯 " + tr("vts_marker"))
        
        self.model_label.setText(self._force_model_status_text())
        if self.vision_devices:
            status_icon = "🎭" if MOCK_MODE else "✅"
            total = len(self.vision_devices)
            self.status_label.setText(f"{status_icon} Connected: {total} sensors")
        else:
            self.status_label.setText("Searching for VisionTouch...")
            
        if self.connect_btn.text().startswith("🔌") or "Disconnect" in self.connect_btn.text() or "断开" in self.connect_btn.text():
            self.connect_btn.setText("🔌 " + tr("btn_disconnect"))
        else:
            self.connect_btn.setText("🔌 " + tr("btn_connect"))
            
        self.calibrate_btn.setText("🔄 " + tr("btn_calibrate"))

    def _connect_signals(self):
        """Connect signals to slots"""
        self.signals.sensors_found.connect(self._on_sensors_found)
        self.signals.init_progress.connect(self._on_init_progress)
        self.signals.sensor_initialized.connect(self._on_sensor_initialized)
        self.signals.sensor_ready.connect(self._on_sensor_ready)
        self.signals.init_error.connect(self._on_init_error)
        self.signals.init_finished.connect(self._on_init_finished)
        self.signals.sensor_data_ready.connect(self._on_sensor_data)
        self.signals.stats_ready.connect(self._on_stats)
        self.signals.status_message.connect(self._on_status_message)
        self.signals.error_occurred.connect(self._on_error)

    def connect_if_needed(self):
        """Connect to the VisionTouch sensor if the panel is idle."""
        if not self.vision_devices and self.connect_btn.isEnabled():
            self._auto_connect()
        
    def _toggle_connection(self):
        """Toggle connection state"""
        if self.vision_devices:
            # We are connected, disconnect first
            self._disconnect()
            self.connect_btn.setText("🔌 Connect / Switch")
            self.status_label.setText("Disconnected")
            self.statusbar.showMessage("Disconnected from sensor")
            self.calibrate_btn.setEnabled(False)
            self.sensor_combo.clear()
        else:
            self._auto_connect()
            
    def _auto_connect(self):
        """Auto-connect to first available VisionTouch device"""
        if VTSensor is None or VTSDeviceFinder is None:
            self._on_error("VisionTouch SDK not available")
            return

        if self.initializing:
            return

        self.closing = False
        self.initializing = True
        self.force_enabled = self.force_model_mode != "none"
        self._update_force_tab_text()
        self._set_model_controls_enabled(False)
        self.init_progress_bar.setRange(0, 1)
        self.init_progress_bar.setValue(0)
        self.init_progress_bar.setFormat("Searching...")
        self.connect_btn.setEnabled(False)
        self.calibrate_btn.setEnabled(False)
        self.status_label.setStyleSheet(f"color: {COLORS['text_muted']};")
        if MOCK_MODE:
            self.status_label.setText("Connecting (Mock Mode)...")
            self.statusbar.showMessage("🎭 Mock Mode: Simulating VisionTouch device...")
        else:
            self.status_label.setText("Searching for VisionTouch...")
            self.statusbar.showMessage("Searching for VisionTouch...")

        self.init_thread = threading.Thread(target=self._initialize_sensors_worker, daemon=True)
        self.init_thread.start()

    def _initialize_sensors_worker(self):
        """Initialize VisionTouch sensors without blocking the Qt event loop."""
        selected_sns = []
        try:
            finder = VTSDeviceFinder()
            sns = finder.get_sns()

            if not sns:
                self.signals.init_error.emit("VisionTouch", "No VisionTouch device found")
                self.signals.init_finished.emit({}, [])
                return

            if self.target_sn:
                if self.target_sn not in sns:
                    self.signals.init_error.emit(self.target_sn, "VisionTouch device not found")
                    self.signals.init_finished.emit({}, [])
                    return
                selected_sns = [self.target_sn]
            else:
                selected_sns = list(sns)

            mode_str = " (Mock)" if MOCK_MODE else ""
            self.signals.sensors_found.emit(selected_sns)

            for idx, sn in enumerate(selected_sns, start=1):
                self.signals.init_progress.emit(idx, len(selected_sns), sn)
                logger.info(f"Found VisionTouch device: {sn}{mode_str}")

                try:
                    config = finder.get_device_by_sn(sn)
                    force_model_path = (
                        self._resolve_force_model_path(sn, notify=False)
                        if self.force_enabled
                        else None
                    )
                    if force_model_path:
                        logger.info(f"Using VisionTouch force model: {force_model_path}")
                        vision_device = VTSensor(config=config, force_model_path=force_model_path)
                    else:
                        if self.force_model_mode == "required" and not MOCK_MODE:
                            self.signals.init_error.emit(
                                sn,
                                f"Force model not found: {self._force_model_path(sn)}",
                            )
                            continue
                        vision_device = VTSensor(config=config)

                    vision_device.calibrate()
                    self.signals.sensor_initialized.emit(sn, vision_device)
                    self.signals.sensor_ready.emit(sn)
                    logger.info(f"VisionTouch connected: {sn}{mode_str}")
                except Exception as e:
                    error_msg = f"Connection error for {sn}: {e}"
                    if hasattr(e, 'suggestion'):
                        error_msg += f"\nSuggestion: {e.suggestion}"
                    self.signals.init_error.emit(sn, str(e))
                    logger.error(error_msg)
        except Exception as e:
            self.signals.init_error.emit("VisionTouch", f"Connection error: {e}")
        self.signals.init_finished.emit({}, selected_sns)

    def _force_model_status_text(self):
        apply_note = ""
        if self.vision_devices:
            active_mode = "enabled" if self.force_enabled else "disabled"
            apply_note = f" | Active: {active_mode}. Changes apply after reconnect."
        if self.force_model_mode == "none":
            return f"Force model: disabled (fast init){apply_note}"
        if self.force_model_dir:
            return f"Force model: {self.force_model_dir} ({self.force_model_mode}){apply_note}"
        return f"Force model: not configured ({self.force_model_mode}){apply_note}"

    def _force_model_path(self, sn: str):
        if not self.force_model_dir:
            return None
        return Path(self.force_model_dir).expanduser() / sn / f"{sn}.onnx.enc"

    def _resolve_force_model_path(self, sn: str, notify: bool = True):
        """Return the per-SN force model path when a model directory is configured."""
        if not self.force_model_dir or MOCK_MODE:
            return None

        force_model_path = self._force_model_path(sn)
        if force_model_path.is_file():
            return str(force_model_path)

        if notify:
            self._on_error(
                "Force model not found for "
                f"{sn}: {force_model_path}. "
                "Force6D values may not match the VTS collection demo."
            )
        return None

    def _update_force_tab_text(self):
        if not hasattr(self, "tabs") or not hasattr(self, "force_widget"):
            return
        index = self.tabs.indexOf(self.force_widget)
        if index < 0:
            return
        force_tab_name = "💪 6D Force" if self.force_enabled else "💪 6D Force (off)"
        self.tabs.setTabText(index, force_tab_name)

    def _set_model_controls_enabled(self, enabled: bool):
        if hasattr(self, "force_mode_combo"):
            self.force_mode_combo.setEnabled(enabled)
        if hasattr(self, "model_dir_btn"):
            self.model_dir_btn.setEnabled(enabled)
        if hasattr(self, "clear_model_dir_btn"):
            self.clear_model_dir_btn.setEnabled(enabled)

    def _on_force_mode_changed(self, *_args):
        mode = self.force_mode_combo.currentData()
        if not mode:
            return
        self.force_model_mode = mode
        if not self.vision_devices and not self.initializing:
            self.force_enabled = mode != "none"
            self._update_force_tab_text()
        self.model_label.setText(self._force_model_status_text())

    def _choose_force_model_dir(self):
        start_dir = self.force_model_dir or str(Path.cwd())
        selected_dir = QFileDialog.getExistingDirectory(
            self,
            "Choose VisionTouch force model directory",
            start_dir,
        )
        if not selected_dir:
            return
        self.force_model_dir = selected_dir
        if self.force_model_mode == "none":
            auto_index = self.force_mode_combo.findData("auto")
            if auto_index >= 0:
                self.force_mode_combo.setCurrentIndex(auto_index)
        self.model_label.setText(self._force_model_status_text())

    def _clear_force_model_dir(self):
        self.force_model_dir = None
        self.model_label.setText(self._force_model_status_text())

    def _on_sensors_found(self, selected_sns):
        self.statusbar.showMessage(f"Initializing 0/{len(selected_sns)} VisionTouch sensors...")
        self.init_progress_bar.setRange(0, max(1, len(selected_sns)))
        self.init_progress_bar.setValue(0)
        self.init_progress_bar.setFormat(f"Initializing 0/{len(selected_sns)}")
        self.overview_widget.set_sensors(selected_sns)
        self.sensor_combo.clear()
        self.vision_devices = {}

    def _on_init_progress(self, index: int, total: int, sn: str):
        self.status_label.setText(f"Initializing {index}/{total}: {sn}")
        self.status_label.setStyleSheet(f"color: {COLORS['text_muted']};")
        self.init_progress_bar.setRange(0, max(1, total))
        self.init_progress_bar.setValue(max(0, index - 1))
        self.init_progress_bar.setFormat(f"Initializing {index}/{total}: {sn}")
        self.statusbar.showMessage(f"Initializing {index}/{total}: {sn}")

    def _on_sensor_initialized(self, sn: str, vision_device):
        if self.closing:
            try:
                vision_device.release()
            except Exception as e:
                logger.error(f"Error releasing VisionTouch device after close: {e}")
            return
        self.vision_devices[sn] = vision_device
        if self.selected_sn is None:
            self.selected_sn = sn
        if self.collector is None:
            self.collector = VisionTouchDataCollector(
                self.vision_devices,
                self.signals,
                collect_force=self.force_enabled,
            )
            self.collector.start()
        self.calibrate_btn.setEnabled(True)

    def _on_sensor_ready(self, sn: str):
        self.sensor_combo.addItem(sn)
        self.overview_widget.set_status(sn, "Ready")
        total = max(1, self.init_progress_bar.maximum())
        ready_count = len(self.vision_devices)
        self.init_progress_bar.setValue(min(ready_count, total))
        self.init_progress_bar.setFormat(f"Ready {ready_count}/{total}")

    def _on_init_error(self, sn: str, message: str):
        self.overview_widget.set_error(sn, message)
        self.statusbar.showMessage(f"{sn}: {message}")

    def _on_init_finished(self, vision_devices, selected_sns):
        self.initializing = False
        self.init_thread = None
        self.connect_btn.setEnabled(True)
        self._set_model_controls_enabled(True)
        if vision_devices:
            self.vision_devices.update(dict(vision_devices))

        if not self.vision_devices:
            self.calibrate_btn.setEnabled(False)
            self.init_progress_bar.setValue(0)
            self.init_progress_bar.setFormat("No sensors ready")
            self._on_error("No VisionTouch sensors initialized successfully")
            return

        self.selected_sn = self.sensor_combo.currentText() or self.selected_sn or next(iter(self.vision_devices.keys()))
        if self.collector is None:
            self.collector = VisionTouchDataCollector(
                self.vision_devices,
                self.signals,
                collect_force=self.force_enabled,
            )
            self.collector.start()

        status_icon = "🎭" if MOCK_MODE else "✅"
        total = len(selected_sns) if selected_sns else len(self.vision_devices)
        self.status_label.setText(f"{status_icon} Connected: {len(self.vision_devices)}/{total} sensors")
        self.status_label.setStyleSheet(f"color: {COLORS['text_muted']};")
        self.statusbar.showMessage(f"Connected to {len(self.vision_devices)}/{total} sensors")
        self.init_progress_bar.setRange(0, max(1, total))
        self.init_progress_bar.setValue(len(self.vision_devices))
        self.init_progress_bar.setFormat(f"Connected {len(self.vision_devices)}/{total}")
        self.model_label.setText(self._force_model_status_text())
        self.connect_btn.setText("🔌 Disconnect")
        self.calibrate_btn.setEnabled(True)

    def _on_selected_sensor_changed(self, sn: str):
        if sn:
            self.selected_sn = sn
            
    def _calibrate(self):
        """Recalibrate all connected sensors."""
        if not self.vision_devices:
            return
        
        try:
            self.statusbar.showMessage("Calibrating all VisionTouch sensors...")
            for sn, vision_device in self.vision_devices.items():
                self.status_label.setText(f"Calibrating: {sn}")
                vision_device.calibrate()
            self.status_label.setText(f"Connected: {len(self.vision_devices)} sensors")
            self.status_label.setStyleSheet(f"color: {COLORS['text_muted']};")
            self.statusbar.showMessage("Calibration complete")
            logger.info("VisionTouch sensors recalibrated")
        except Exception as e:
            self._on_error(f"Calibration error: {e}")

    def _on_sensor_data(self, sn: str, data):
        if VTSDataType.FORCE6D_VECTOR in data:
            self.overview_widget.update_force(sn, data[VTSDataType.FORCE6D_VECTOR])
        elif not self.force_enabled:
            self.overview_widget.set_force_disabled(sn)

        if sn != self.selected_sn:
            return

        if VTSDataType.FORCE6D_VECTOR in data:
            self.force_widget.update_data(data[VTSDataType.FORCE6D_VECTOR])

        if VTSDataType.DEPTH_MAP in data:
            self.depth_widget.update_data(data[VTSDataType.DEPTH_MAP])

        images = {}
        if VTSDataType.RAW_IMG in data:
            images['raw'] = data[VTSDataType.RAW_IMG]
        if VTSDataType.CALIBRATE_IMG in data:
            images['calibrate'] = data[VTSDataType.CALIBRATE_IMG]
        if VTSDataType.WARPED_IMG in data:
            images['warped'] = data[VTSDataType.WARPED_IMG]
        if VTSDataType.DIFF_IMG in data:
            images['diff'] = data[VTSDataType.DIFF_IMG]
        if VTSDataType.MARKER_IMG in data:
            images['marker'] = data[VTSDataType.MARKER_IMG]
        if images:
            self.image_widget.update_data(images)

        if VTSDataType.SLIP_STATE in data:
            self.slip_widget.update_data(
                data[VTSDataType.SLIP_STATE],
                data.get(VTSDataType.WARPED_IMG)
            )

        if VTSDataType.XYZ_VECTOR in data:
            self.pointcloud_widget.update_data(data[VTSDataType.XYZ_VECTOR])

        if VTSDataType.MARKER_OFFSET_VECTOR in data:
            self.marker_widget.update_data(
                data[VTSDataType.MARKER_ORIGIN_VECTOR],
                data[VTSDataType.MARKER_CURRENT_VECTOR],
                data[VTSDataType.MARKER_OFFSET_VECTOR],
                data.get(VTSDataType.WARPED_IMG)
            )

    def _on_stats(self, device_count: int, collected_count: int, round_seconds: float):
        fps = 1.0 / max(round_seconds, 1e-6)
        message = (
            f"Devices: {device_count} | Collected: {collected_count} | "
            f"Round: {round_seconds * 1000:.1f} ms | FPS: {fps:.1f}"
        )
        self.statusbar.showMessage(message)
            
    def _on_status_message(self, message: str):
        """Handle status message"""
        self.statusbar.showMessage(message)
        
    def _on_error(self, message: str):
        """Handle error messages"""
        self.status_label.setText(f"Error: {message}")
        self.status_label.setStyleSheet(f"color: {COLORS['danger']}; font-weight: bold;")
        if ": " in message:
            sn, detail = message.split(": ", 1)
            self.overview_widget.set_error(sn, detail)
        logger.error(message)

    def _disconnect(self):
        """Clean up background thread and device"""
        if self.collector:
            self.collector.stop()
            self.collector = None
        for vision_device in self.vision_devices.values():
            try:
                vision_device.release()
            except Exception as e:
                logger.error(f"Error releasing VisionTouch device: {e}")
        self.vision_devices.clear()
        self.selected_sn = None
        self._set_model_controls_enabled(True)
        self.force_enabled = self.force_model_mode != "none"
        self._update_force_tab_text()
        self.model_label.setText(self._force_model_status_text())
        if hasattr(self, "init_progress_bar"):
            self.init_progress_bar.setRange(0, 1)
            self.init_progress_bar.setValue(0)
            self.init_progress_bar.setFormat("Idle")

    def closeEvent(self, event):
        """Clean up background thread on close"""
        self.closing = True
        self._disconnect()
        event.accept()
        logger.info("VisionTouch window closed")

class VisionTouchWindow(QMainWindow):
    """Main window wrapper for VisionTouchPanel"""
    def __init__(self, parent=None, target_sn=None, force_model_dir=None, force_model_mode="none"):
        super().__init__(parent)
        self.setWindowTitle("VisionTouch Sensor")
        self.setMinimumSize(900, 700)
        self.panel = VisionTouchPanel(
            self,
            target_sn=target_sn,
            force_model_dir=force_model_dir,
            force_model_mode=force_model_mode,
        )
        self.setCentralWidget(self.panel)

    def closeEvent(self, event):
        self.panel.closeEvent(event)
        event.accept()


def main():
    """Run the VisionTouch window as a standalone GUI."""
    import argparse
    import signal

    from PySide6.QtWidgets import QApplication

    parser = argparse.ArgumentParser(description="Standalone VisionTouch sensor window")
    parser.add_argument("--sn", default=None, help="Target VisionTouch sensor SN")
    parser.add_argument(
        "--force-model-dir",
        default=None,
        help="Parent directory for force models: {dir}/{SN}/{SN}.onnx.enc",
    )
    parser.add_argument(
        "--force-model-mode",
        choices=["none", "auto", "required"],
        default="none",
        help="Force model loading mode. none=fast init without Force6D, auto=load models when present, required=fail sensors without models.",
    )
    args = parser.parse_args()

    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    app.setApplicationName("VisionTouch Sensor")
    app.setOrganizationName("BrainCo")

    signal.signal(signal.SIGINT, signal.SIG_DFL)

    window = VisionTouchWindow(
        target_sn=args.sn,
        force_model_dir=args.force_model_dir,
        force_model_mode=args.force_model_mode,
    )
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
