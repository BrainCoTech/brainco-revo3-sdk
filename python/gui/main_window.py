"""Revo3-only main window using the current GUI structure."""

import sys
import time
import warnings
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QActionGroup, QColor, QPainter
from PySide6.QtWidgets import (
    QDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStatusBar,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from .connection_panel import ConnectionPanel, run_in_new_loop
from .data_collector_panel import DataCollectorPanel
from .dfu_panel import DfuPanel
from .i18n import get_i18n, tr
from .motor_config_panel_revo3 import Revo3MotorConfigPanel
from .motor_control_panel_revo3 import Revo3MotorControlPanel
from .shared_data import SharedDataManager
from .shared_data import DEFAULT_MOTOR_FREQ, TOUCH_VIEW_FREQ
from .system_config_panel import SystemConfigPanel
from .teaching_panel import TeachingPanel
from .touch_panel_revo3 import Revo3TouchSubPanel
from .styles import is_dark_mode, get_tab_stylesheet


sys.path.insert(0, str(Path(__file__).parent.parent))
from common_imports import baudrate_to_int, get_model_name, logger, revo3_uses_motor_api, sdk


def _touch_layout(device):
    return getattr(
        getattr(getattr(device, "hand", None), "touch", None),
        "layout",
        None,
    )


def _touch_module_count(layout) -> int:
    if layout is None:
        return 0
    try:
        return len(layout.modules)
    except Exception:
        return 0


class DfuOverlay(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        self.hide()

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 180))
        painter.setPen(QColor(255, 193, 7))
        font = painter.font()
        font.setPointSize(24)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(self.rect(), Qt.AlignCenter, tr("dfu_overlay_warning"))

    def show_overlay(self, parent_widget):
        self.setParent(parent_widget)
        self.setGeometry(parent_widget.rect())
        self.raise_()
        self.show()

    def hide_overlay(self):
        self.hide()


class MainWindow(QMainWindow):
    def __init__(
        self,
        revo3_modbus=False,
        mock_type=None,
        canfd=None,
    ):
        super().__init__()
        self.i18n = get_i18n()
        self.i18n.language_changed.connect(self._on_language_changed)
        self.device = None
        self.slave_id = 126
        self.protocol = None
        self.revo3_modbus = revo3_modbus
        self.mock_type = mock_type
        self.canfd_arg = canfd
        self._handling_connection_lost = False
        self.shared_data = SharedDataManager()
        self._last_fps_tuple = (0.0, 0.0, 0.0)
        self._setup_ui()
        self._setup_menu()
        self._setup_statusbar()
        self.shared_data.touch_latency_timer_hint.connect(
            self._on_touch_latency_timer_hint
        )
        self._update_texts()
        sdk_version = "Unknown"
        if sdk is not None:
            sdk_version = getattr(sdk, "__version__", "1.1.1")
        self.setWindowTitle(f"BC Revo3 SDK (v{sdk_version})")
        self.setMinimumSize(1000, 700)
        self.showMaximized()

    def _setup_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(16)

        self.connection_panel = ConnectionPanel(
            revo3_modbus=self.revo3_modbus,
            mock_type=self.mock_type,
            canfd=self.canfd_arg,
        )
        self.connection_panel.connected.connect(self._on_connected)
        self.connection_panel.about_to_disconnect.connect(self._on_about_to_disconnect)
        self.connection_panel.disconnected.connect(self._on_disconnected)
        main_layout.addWidget(self.connection_panel)

        self.tabs = QTabWidget()
        self.tabs.setUsesScrollButtons(True)
        self.tabs.setElideMode(Qt.ElideNone)
        self.tabs.setDocumentMode(False)
        self.tabs.setStyleSheet(get_tab_stylesheet(is_dark_mode()))
        self.tabs.currentChanged.connect(self._on_tab_changed)
        main_layout.addWidget(self.tabs, 1)

        self.motor_panel_revo3 = Revo3MotorControlPanel()
        self.tabs.addTab(self.motor_panel_revo3, "🎮 " + tr("motor_control_v3"))

        self.config_panel_revo3 = Revo3MotorConfigPanel()
        self.tabs.addTab(self.config_panel_revo3, "⚙ " + tr("v3_motor_config"))

        self.touch_panel = Revo3TouchPanel()
        self.tabs.addTab(self.touch_panel, "👆 " + tr("touch_sensor"))
        self.tabs.setTabVisible(self.tabs.indexOf(self.touch_panel), False)

        self.teaching_panel = TeachingPanel()
        self.tabs.addTab(self.teaching_panel, "🎓 " + tr("teaching_mode"))

        self.dfu_panel = DfuPanel()
        self.dfu_panel.dfu_started.connect(self._on_dfu_started)
        self.dfu_panel.dfu_finished.connect(self._on_dfu_finished)
        self.tabs.addTab(self.dfu_panel, "🔄 " + tr("dfu_upgrade"))

        self.config_panel = SystemConfigPanel()
        if hasattr(self.config_panel, "request_reconnect"):
            self.config_panel.request_reconnect.connect(self._on_request_reconnect)
        self.touch_panel.touch_layout_updated.connect(
            self.config_panel.update_touch_layout
        )
        self.tabs.addTab(self.config_panel, "\u2699 " + tr("system_config"))

        self.collector_panel = DataCollectorPanel()
        self.dfu_overlay = DfuOverlay()
        self.tabs.setEnabled(False)

    def _setup_menu(self):
        menubar = self.menuBar()
        self.file_menu = menubar.addMenu("File")
        self.exit_action = QAction("Exit", self)
        self.exit_action.setShortcut("Ctrl+Q")
        self.exit_action.triggered.connect(self.close)
        self.file_menu.addAction(self.exit_action)

        self.view_menu = menubar.addMenu("View")
        self.lang_menu = self.view_menu.addMenu("Language")
        lang_group = QActionGroup(self)
        lang_group.setExclusive(True)
        self.lang_en_action = QAction("English", self)
        self.lang_en_action.setCheckable(True)
        self.lang_en_action.setChecked(True)
        self.lang_en_action.triggered.connect(lambda: self.i18n.set_language("en"))
        lang_group.addAction(self.lang_en_action)
        self.lang_menu.addAction(self.lang_en_action)
        self.lang_zh_action = QAction("中文", self)
        self.lang_zh_action.setCheckable(True)
        self.lang_zh_action.triggered.connect(lambda: self.i18n.set_language("zh"))
        lang_group.addAction(self.lang_zh_action)
        self.lang_menu.addAction(self.lang_zh_action)

        self.tools_menu = menubar.addMenu("Tools")
        self.data_collector_action = QAction("📊 Data Collection...", self)
        self.data_collector_action.triggered.connect(self._show_data_collector)
        self.tools_menu.addAction(self.data_collector_action)

        self.help_menu = menubar.addMenu("Help")
        self.about_action = QAction("About", self)
        self.about_action.triggered.connect(self._show_about)
        self.help_menu.addAction(self.about_action)

    def _setup_statusbar(self):
        self.statusbar = QStatusBar()
        self.setStatusBar(self.statusbar)

        self.fps_label = QLabel("")
        self.fps_label.setStyleSheet(
            "font-family: 'SF Mono', 'Segoe UI Mono', 'Roboto Mono', Menlo, Consolas, monospace; "
            "font-size: 11px; font-weight: 600; padding: 2px 8px; color: #10b981;"
        )
        self.statusbar.addPermanentWidget(self.fps_label)

        self.device_info_label = QLabel("")
        self.statusbar.addPermanentWidget(self.device_info_label)
        self.lang_btn = QPushButton("🌐 EN")
        self.lang_btn.setFixedWidth(60)
        self.lang_btn.clicked.connect(self._toggle_language)
        self.statusbar.addPermanentWidget(self.lang_btn)

    def _on_tab_changed(self, index):
        current_widget = self.tabs.widget(index)
        if self.shared_data and self.shared_data.data_collector:
            if current_widget == self.touch_panel:
                self.shared_data.update_frequencies(0, TOUCH_VIEW_FREQ)
            else:
                self.shared_data.update_frequencies(DEFAULT_MOTOR_FREQ, 0)
        if hasattr(self, "fps_label"):
            self._update_fps_display()

    def _toggle_language(self):
        if self.i18n.current_language == "en":
            self.i18n.set_language("zh")
            self.lang_btn.setText("🌐 中")
        else:
            self.i18n.set_language("en")
            self.lang_btn.setText("🌐 EN")

    def _update_texts(self):
        if self.device is None:
            self.statusbar.showMessage(tr("ready"))
        self._update_fps_display()

    def _on_language_changed(self, _lang):
        self._update_texts()
        for i in range(self.tabs.count()):
            panel = self.tabs.widget(i)
            if hasattr(panel, "update_texts"):
                panel.update_texts()
        for panel in [self.connection_panel, self.collector_panel]:
            if hasattr(panel, "update_texts"):
                panel.update_texts()
        names = [
            (self.motor_panel_revo3, "🎮 " + tr("motor_control_v3")),
            (self.config_panel_revo3, "⚙ " + tr("v3_motor_config")),
            (self.touch_panel, "👆 " + tr("touch_sensor")),
            (self.teaching_panel, "🎓 " + tr("teaching_mode")),
            (self.dfu_panel, "🔄 " + tr("dfu_upgrade")),
            (self.config_panel, "\u2699 " + tr("system_config")),
        ]
        for panel, name in names:
            if panel is None:
                continue
            idx = self.tabs.indexOf(panel)
            if idx >= 0:
                self.tabs.setTabText(idx, name)

    def _on_about_to_disconnect(self):
        self.shared_data.stop()

    def _on_connected(self, device, slave_id, device_info, protocol_key, protocol):
        self._handling_connection_lost = False
        self.device = device
        self.slave_id = slave_id
        self.protocol = protocol
        model = getattr(device_info, "model", None) if device_info else None
        if model and not revo3_uses_motor_api(model):
            QMessageBox.warning(self, "BC Revo3 SDK", "Connected hardware is not Revo3.")
            self.connection_panel._on_disconnect()
            return

        self.tabs.setEnabled(True)
        touch_layout = _touch_layout(device)
        supports_touch = (
            bool(getattr(device, "supports_touch", False))
            or _touch_module_count(touch_layout) > 0
        )
        touch_tab_index = self.tabs.indexOf(self.touch_panel)
        if touch_tab_index >= 0:
            self.tabs.setTabVisible(touch_tab_index, supports_touch)

        self.shared_data.set_device(device, slave_id, device_info)
        self.shared_data.connection_lost.connect(self._on_connection_lost)
        self.shared_data.fps_updated.connect(self._on_fps_updated)

        port_name = self.connection_panel.last_reconnect_port or "unknown"
        self.shared_data.configure_serial_latency_hint(protocol_key, port_name)
        baud_str = ""
        if protocol_key == "modbus":
            last_baud = self.connection_panel.last_modbus_baudrate
            if last_baud is not None:
                baud_val = baudrate_to_int(last_baud)
                baud_str = f" @ {baud_val / 1000000:.1f}M bps"
        logger.info(f"Connected to Revo3 device: ID={slave_id}, Protocol={protocol}{baud_str}, Port={port_name}")

        self.shared_data.start()

        self.motor_panel_revo3.set_device(device, slave_id, device_info, self.shared_data)
        self.config_panel_revo3.set_device(device, slave_id, device_info, protocol, self.shared_data)
        self.teaching_panel.set_device(device, slave_id, device_info, self.shared_data)
        if touch_tab_index >= 0 and self.tabs.isTabVisible(touch_tab_index):
            self.touch_panel.set_device(device, slave_id, device_info, self.shared_data)
        else:
            self.touch_panel.clear_device()
        self.collector_panel.set_device(device, slave_id, device_info, self.shared_data)
        self.dfu_panel.set_device(device, slave_id, device_info, self.shared_data)
        self.config_panel.set_device(device, slave_id, device_info, protocol, self.shared_data)
        if hasattr(self.config_panel, "set_connection_info"):
            self.config_panel.set_connection_info(self.connection_panel.get_connection_info())

        if hasattr(self.config_panel, "slave_id_changed"):
            self.config_panel.slave_id_changed.connect(self._on_slave_id_changed)

        self._update_device_info_statusbar()
        self._update_fps_display()
        sn = getattr(device_info, "serial_number", "") if device_info else ""
        self.statusbar.showMessage(f"Connected: {sn}")
        self.tabs.setCurrentIndex(self.tabs.indexOf(self.motor_panel_revo3))

    def _on_fps_updated(self, motor_fps: float, touch_fps: float, ui_fps: float):
        self._last_fps_tuple = (motor_fps, touch_fps, ui_fps)
        self._update_fps_display()

    def _on_touch_latency_timer_hint(
        self, actual_frequency: float, target_frequency: float, port_name: str
    ):
        message = tr("touch_latency_timer_hint").format(
            actual=actual_frequency,
            target=target_frequency,
            port=port_name,
        )
        self.statusbar.showMessage(message, 20000)

    def _update_fps_display(self):
        if self.device is None:
            self.fps_label.setText("")
            return
        motor_fps, touch_fps, ui_fps = self._last_fps_tuple
        touch_tab_index = self.tabs.indexOf(self.touch_panel)
        supports_touch = touch_tab_index >= 0 and self.tabs.isTabVisible(touch_tab_index)

        motor_name = tr("fps_motor_prefix")
        touch_name = tr("fps_touch_prefix")
        ui_name = tr("fps_ui_prefix")

        parts = []
        current_widget = self.tabs.currentWidget()
        motor_fps_widgets = (
            self.motor_panel_revo3,
            self.config_panel_revo3,
            self.teaching_panel,
        )
        if current_widget in motor_fps_widgets:
            parts.append(f"{motor_name}: {motor_fps:.1f} FPS")
        elif current_widget == self.touch_panel and supports_touch:
            parts.append(f"{touch_name}: {touch_fps:.1f} FPS")
        if ui_fps > 0:
            parts.append(f"{ui_name}: {ui_fps:.1f} FPS")

        if not parts:
            self.fps_label.setText("")
            return

        self.fps_label.setText(" | ".join(parts))

    def _update_device_info_statusbar(self):
        if self.device is None:
            self.device_info_label.setText("")
            return
        device_info = self.shared_data.device_info
        protocol_key = self.connection_panel.protocol_key
        protocol = self.connection_panel.protocol
        baud_str = ""
        if protocol_key == "modbus":
            last_baud = self.connection_panel.last_modbus_baudrate
            if last_baud is not None:
                baud_val = baudrate_to_int(last_baud)
                if baud_val > 0:
                    if baud_val >= 1000000:
                        baud_str = f" ({baud_val // 1000000}M)"
                    else:
                        baud_str = f" ({baud_val // 100}K)"
        elif protocol_key == "canfd":
            baud_str = " (1M/5M)"

        self.device_info_label.setText(
            " | ".join(p for p in [f"ID: {self.slave_id}", f"{protocol}{baud_str}"] if p)
        )

    def _on_disconnected(self):
        self._handling_connection_lost = False
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            try:
                self.shared_data.connection_lost.disconnect(self._on_connection_lost)
            except Exception:
                pass
            try:
                self.shared_data.fps_updated.disconnect(self._on_fps_updated)
            except Exception:
                pass
            try:
                self.config_panel.slave_id_changed.disconnect(self._on_slave_id_changed)
            except Exception:
                pass
        self.shared_data.stop()
        self.shared_data.clear_device()
        self._last_fps_tuple = (0.0, 0.0, 0.0)
        self.fps_label.setText("")
        self.device = None
        self.slave_id = 126
        self.protocol = None
        for panel in [
            self.motor_panel_revo3,
            self.config_panel_revo3,
            self.teaching_panel,
            self.touch_panel,
            self.collector_panel,
            self.dfu_panel,
            self.config_panel,
        ]:
            if hasattr(panel, "clear_device"):
                panel.clear_device()
        self.device_info_label.setText("")
        self.statusbar.showMessage(tr("status_disconnected"))
        touch_tab_index = self.tabs.indexOf(self.touch_panel)
        if touch_tab_index >= 0:
            self.tabs.setTabVisible(touch_tab_index, False)
        self.tabs.setEnabled(False)

    def _on_connection_lost(self):
        if self._handling_connection_lost:
            return
        self._handling_connection_lost = True
        self.statusbar.showMessage(tr("status_connection_lost") + " - 正在尝试自动重连...")
        self.connection_panel._on_disconnect()

        from PySide6.QtCore import QTimer
        QTimer.singleShot(1500, self.connection_panel.reconnect_last_device)

    def _on_request_reconnect(self, modbus_baudrate=None):
        if modbus_baudrate is not None:
            self.connection_panel.last_modbus_baudrate = modbus_baudrate
            baud_val = baudrate_to_int(modbus_baudrate)
            logger.info(f"Baudrate changed to {baud_val}. Reconnecting...")
        else:
            logger.info("Reconnection requested...")
        self.statusbar.showMessage("Baudrate changed. Automatically scanning and reconnecting in 2 seconds...")
        self.connection_panel._on_disconnect()
        from PySide6.QtCore import QTimer
        QTimer.singleShot(2000, self.connection_panel.reconnect_last_device)

    def _on_slave_id_changed(self, new_id):
        self.slave_id = new_id
        self.shared_data.update_slave_id(new_id)
        self.connection_panel.slave_id = new_id
        self.statusbar.showMessage(f"Slave ID changed to {new_id}")

    def _on_dfu_started(self):
        self.shared_data.stop()
        for panel in [
            self.motor_panel_revo3,
            self.config_panel_revo3,
            self.teaching_panel,
            self.touch_panel,
            self.collector_panel,
        ]:
            if hasattr(panel, "clear_device"):
                panel.clear_device()
        dfu_index = self.tabs.indexOf(self.dfu_panel)
        self.tabs.setCurrentIndex(dfu_index)
        for i in range(self.tabs.count()):
            if i != dfu_index:
                self.tabs.setTabEnabled(i, False)
        self.connection_panel.disconnect_btn.setEnabled(False)
        self.connection_panel.auto_detect_btn.setEnabled(False)
        self.statusbar.showMessage(tr("dfu_status_warning"))

    def _on_dfu_finished(self, success):
        for i in range(self.tabs.count()):
            self.tabs.setTabEnabled(i, True)
        self.connection_panel.disconnect_btn.setEnabled(True)
        self.connection_panel.auto_detect_btn.setEnabled(True)
        if success:
            self.statusbar.showMessage(tr("dfu_wait_reconnect"))
            # Auto-reconnect after 6 seconds to allow firmware to boot up completely
            from PySide6.QtCore import QTimer
            QTimer.singleShot(6000, self.connection_panel.reconnect_last_device)
        else:
            self.statusbar.showMessage(tr("dfu_failed"))

    def _show_data_collector(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("📊 Data Collection")
        dialog.resize(800, 600)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.collector_panel)
        dialog.exec()
        self.collector_panel.setParent(None)

    def _show_about(self):
        sdk_version = "Unknown"
        if sdk is not None:
            sdk_version = getattr(sdk, "__version__", "1.1.1")
        about_text = f"""
<h2>BC Revo3 SDK GUI</h2>
<p>Modern control interface for BrainCo Revo3 dexterous hands.</p>
<p><b>SDK Version:</b> v{sdk_version}</p>
<h3>Supported Protocols</h3>
<ul><li>Modbus/RS485</li><li>CANFD</li></ul>
<h3>Supported Devices</h3>
<ul><li>Revo3 Basic / Touch</li><li>Revo3 Pro / Touch</li><li>Revo3 Ultra / Touch / Vision Touch</li></ul>
<p style="color: #7f8c8d;">© 2015-2026 BrainCo Inc.</p>
        """
        msg = QMessageBox(self)
        msg.setWindowTitle("About BC Revo3 SDK")
        msg.setTextFormat(Qt.RichText)
        msg.setText(about_text)
        msg.setIcon(QMessageBox.Information)
        msg.exec()

    def closeEvent(self, event):
        if not self.connection_panel.shutdown_worker():
            self.connection_panel.status_label.setText("Stopping connection task...")
            event.ignore()
            return
        self.shared_data.stop()
        time.sleep(0.1)
        for panel in [
            self.motor_panel_revo3,
            self.config_panel_revo3,
            self.teaching_panel,
            self.touch_panel,
            self.collector_panel,
        ]:
            if hasattr(panel, "clear_device"):
                panel.clear_device()
        if self.connection_panel.ctx:
            try:
                ctx = self.connection_panel.ctx
                if hasattr(ctx, "close"):
                    run_in_new_loop(lambda: ctx.close())
            except Exception as e:
                print(f"Error closing device on exit: {e}")
            self.connection_panel.ctx = None
        self.device = None
        event.accept()


class Revo3TouchPanel(Revo3TouchSubPanel):
    def _on_fps_updated(self, _motor_fps, touch_fps, _ui_fps):
        self.update_fps(touch_fps)

    def set_device(self, device, slave_id, device_info=None, shared_data=None):
        super().set_device(device, slave_id, device_info, shared_data)
        self.device_info = device_info
        self.shared_data = shared_data
        if shared_data:
            shared_data.touch_updated.connect(self.enqueue_data)
            shared_data.fps_updated.connect(self._on_fps_updated)

    def clear_device(self):
        super().clear_device()
        if getattr(self, "shared_data", None):
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", RuntimeWarning)
                try:
                    self.shared_data.touch_updated.disconnect(self.enqueue_data)
                except Exception:
                    pass
                try:
                    self.shared_data.fps_updated.disconnect(self._on_fps_updated)
                except Exception:
                    pass
        self.device_info = None
        self.shared_data = None
