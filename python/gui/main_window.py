"""Modern Revo3-only main window matching the legacy GUI structure."""

import sys
import time
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
from .shared_data import DEFAULT_MOTOR_FREQ
from .system_config_panel import SystemConfigPanel
from .teaching_panel import TeachingPanel
from .timing_test_panel import TimingTestPanel
from .touch_panel_revo3 import Revo3TouchSubPanel
from .touch_common import run_async

sys.path.insert(0, str(Path(__file__).parent.parent))
from common_imports import get_hw_type_name, has_touch, sdk, uses_revo3_motor_api, logger, baudrate_to_int


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
    def __init__(self, revo3_modbus=False, mock_type=None):
        super().__init__()
        self.i18n = get_i18n()
        self.i18n.language_changed.connect(self._on_language_changed)
        self.device = None
        self.slave_id = 1
        self.protocol = None
        self.revo3_modbus = revo3_modbus
        self.mock_type = mock_type
        self.shared_data = SharedDataManager()
        self.vision_touch_window = None
        self._setup_ui()
        self._setup_menu()
        self._setup_statusbar()
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

        self.connection_panel = ConnectionPanel(revo3_modbus=self.revo3_modbus, mock_type=self.mock_type)
        self.connection_panel.connected.connect(self._on_connected)
        self.connection_panel.about_to_disconnect.connect(self._on_about_to_disconnect)
        self.connection_panel.disconnected.connect(self._on_disconnected)
        main_layout.addWidget(self.connection_panel)

        self.tabs = QTabWidget()
        self.tabs.setUsesScrollButtons(True)
        self.tabs.setElideMode(Qt.ElideNone)
        self.tabs.setDocumentMode(False)
        self.tabs.setStyleSheet("""
            QTabBar::tab {
                font-size: 13px;
                font-weight: bold;
                padding: 10px 18px;
                margin-right: 2px;
                border: 1px solid #cfd4d9;
                border-bottom: none;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                background-color: #e9ecef;
                color: #495057;
            }
            QTabBar::tab:selected {
                background-color: #ffffff;
                border: 2px solid #5D9CEC;
                border-bottom: 2px solid #ffffff;
                color: #5D9CEC;
            }
            QTabBar::tab:hover:!selected {
                background-color: #f8f9fa;
            }
            QTabWidget::pane {
                border: 2px solid #5D9CEC;
                border-radius: 6px;
                border-top-left-radius: 0px;
                border-top-right-radius: 6px;
                top: -2px;
                background-color: #ffffff;
            }
        """)
        self.tabs.currentChanged.connect(self._on_tab_changed)
        main_layout.addWidget(self.tabs, 1)

        self.motor_panel_revo3 = Revo3MotorControlPanel()
        self.tabs.addTab(self.motor_panel_revo3, "🎮 " + tr("motor_control_v3"))

        self.config_panel_revo3 = Revo3MotorConfigPanel()
        self.tabs.addTab(self.config_panel_revo3, "⚙ " + tr("v3_motor_config"))

        self.touch_panel = Revo3TouchPanel()
        self.tabs.addTab(self.touch_panel, "👆 " + tr("touch_sensor"))

        self.timing_panel = TimingTestPanel()
        self.tabs.addTab(self.timing_panel, "\u23f1 " + tr("timing_test"))

        self.teaching_panel = TeachingPanel()
        self.tabs.addTab(self.teaching_panel, "🎓 " + tr("teaching_mode"))

        self.dfu_panel = DfuPanel()
        self.dfu_panel.dfu_started.connect(self._on_dfu_started)
        self.dfu_panel.dfu_finished.connect(self._on_dfu_finished)
        self.tabs.addTab(self.dfu_panel, "🔄 " + tr("dfu_upgrade"))

        self.config_panel = SystemConfigPanel()
        if hasattr(self.config_panel, "request_reconnect"):
            self.config_panel.request_reconnect.connect(self._on_request_reconnect)
        self.tabs.addTab(self.config_panel, "\u2699 " + tr("system_config"))

        self.collector_panel = DataCollectorPanel()
        self.dfu_overlay = DfuOverlay()

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
        self.vision_touch_action = QAction("📷 VisionTouch Sensor...", self)
        self.vision_touch_action.triggered.connect(self._show_vision_touch)
        self.tools_menu.addAction(self.vision_touch_action)

        self.help_menu = menubar.addMenu("Help")
        self.about_action = QAction("About", self)
        self.about_action.triggered.connect(self._show_about)
        self.help_menu.addAction(self.about_action)

    def _setup_statusbar(self):
        self.statusbar = QStatusBar()
        self.setStatusBar(self.statusbar)

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
                self.shared_data.update_frequencies(0, 20)
            else:
                self.shared_data.update_frequencies(DEFAULT_MOTOR_FREQ, 0)

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

    def _on_language_changed(self, _lang):
        self._update_texts()
        for panel in [
            self.connection_panel,
            self.motor_panel_revo3,
            self.config_panel_revo3,
            self.touch_panel,
            self.collector_panel,
            self.timing_panel,
            self.teaching_panel,
            self.dfu_panel,
            self.config_panel,
        ]:
            if hasattr(panel, "update_texts"):
                panel.update_texts()
        names = [
            (self.motor_panel_revo3, "🎮 " + tr("motor_control_v3")),
            (self.config_panel_revo3, "⚙ " + tr("v3_motor_config")),
            (self.touch_panel, "👆 " + tr("touch_sensor")),
            (self.timing_panel, "\u23f1 " + tr("timing_test")),
            (self.teaching_panel, "🎓 " + tr("teaching_mode")),
            (self.dfu_panel, "🔄 " + tr("dfu_upgrade")),
            (self.config_panel, "\u2699 " + tr("system_config")),
        ]
        for panel, name in names:
            idx = self.tabs.indexOf(panel)
            if idx >= 0:
                self.tabs.setTabText(idx, name)

    def _on_about_to_disconnect(self):
        self.shared_data.stop()

    def _on_connected(self, device, slave_id, device_info, protocol_key, protocol):
        self.device = device
        self.slave_id = slave_id
        self.protocol = protocol
        hw_type = getattr(device_info, "hardware_type", None) if device_info else None
        if hw_type and not uses_revo3_motor_api(hw_type):
            QMessageBox.warning(self, "BC Revo3 SDK", "Connected hardware is not Revo3.")
            self.connection_panel._on_disconnect()
            return

        self.tabs.setEnabled(True)
        touch_tab_index = self.tabs.indexOf(self.touch_panel)
        if touch_tab_index >= 0:
            self.tabs.setTabVisible(touch_tab_index, has_touch(hw_type))

        self.shared_data.set_device(device, slave_id, device_info)
        self.shared_data.connection_lost.connect(self._on_connection_lost)

        if has_touch(hw_type):
            logger.info("Touch-enabled device detected. Automatically enabling touch sensor modules...")
            try:
                # Enable all 11 touch modules (0x7FF mask)
                run_async(lambda: device.revo3_set_all_touch_modules_enabled(slave_id, 0x7FF))
            except Exception as e:
                logger.error(f"Failed to enable touch sensors: {e}")

        self.shared_data.start()

        self.motor_panel_revo3.set_device(device, slave_id, device_info, self.shared_data)
        self.config_panel_revo3.set_device(device, slave_id, device_info, protocol, self.shared_data)
        self.teaching_panel.set_device(device, slave_id, device_info, self.shared_data)
        self.touch_panel.set_device(device, slave_id, device_info, self.shared_data)
        self.collector_panel.set_device(device, slave_id, device_info, self.shared_data)
        self.timing_panel.set_device(device, slave_id, device_info, self.shared_data)
        self.dfu_panel.set_device(device, slave_id, device_info, self.shared_data)
        self.config_panel.set_device(device, slave_id, device_info, protocol, self.shared_data)

        if hasattr(self.config_panel, "slave_id_changed"):
            self.config_panel.slave_id_changed.connect(self._on_slave_id_changed)

        self._update_device_info_statusbar()
        sn = getattr(device_info, "serial_number", "") if device_info else ""
        self.statusbar.showMessage(f"Connected: {sn}")
        self.tabs.setCurrentIndex(self.tabs.indexOf(self.motor_panel_revo3))

    def _update_device_info_statusbar(self):
        if self.device is None:
            self.device_info_label.setText("")
            return
        device_info = self.shared_data.device_info
        hw_type = getattr(device_info, "hardware_type", None) if device_info else None
        hw_str = get_hw_type_name(hw_type) if hw_type else ""
        fw_ver = getattr(device_info, "firmware_version", "") if device_info else ""

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

        self.device_info_label.setText(" | ".join(p for p in [hw_str, f"ID: {self.slave_id}", f"{protocol}{baud_str}", f"FW: {fw_ver}"] if p))

    def _on_disconnected(self):
        try:
            self.shared_data.connection_lost.disconnect(self._on_connection_lost)
        except RuntimeError:
            pass
        try:
            self.config_panel.slave_id_changed.disconnect(self._on_slave_id_changed)
        except Exception:
            pass
        self.shared_data.stop()
        self.shared_data.clear_device()
        self.device = None
        self.slave_id = 1
        self.protocol = None
        for panel in [
            self.motor_panel_revo3,
            self.config_panel_revo3,
            self.teaching_panel,
            self.touch_panel,
            self.collector_panel,
            self.timing_panel,
            self.dfu_panel,
            self.config_panel,
        ]:
            if hasattr(panel, "clear_device"):
                panel.clear_device()
        self.device_info_label.setText("")
        self.statusbar.showMessage(tr("status_disconnected"))

    def _on_connection_lost(self):
        self.statusbar.showMessage(tr("status_connection_lost"))
        self.connection_panel._on_disconnect()

    def _on_request_reconnect(self, modbus_baudrate=None):
        if modbus_baudrate is not None:
            self.connection_panel.last_modbus_baudrate = modbus_baudrate
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

    def _show_vision_touch(self):
        if self.vision_touch_window is None:
            try:
                from .vision_touch_window import VisionTouchWindow

                self.vision_touch_window = VisionTouchWindow(self)
            except ImportError as e:
                QMessageBox.warning(
                    self,
                    "VisionTouch Not Available",
                    f"VisionTouch features require pyvitaisdk.\n\nInstall with: pip install pyvitaisdk\n\nError: {e}",
                )
                return
        self.vision_touch_window.show()
        self.vision_touch_window.raise_()
        self.vision_touch_window.activateWindow()

    def _show_about(self):
        sdk_version = "Unknown"
        if sdk is not None:
            sdk_version = getattr(sdk, "__version__", "1.1.1")
        about_text = f"""
<h2>BC Revo3 SDK GUI</h2>
<p>Modern control interface for BrainCo Revo3 dexterous hands.</p>
<p><b>SDK Version:</b> v{sdk_version}</p>
<h3>Supported Protocols</h3>
<ul><li>Modbus/RS485</li><li>CANFD</li><li>EtherCAT (Linux)</li></ul>
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
                protocol = self.connection_panel.protocol_key
                if getattr(ctx, "is_mock", False):
                    run_in_new_loop(lambda: ctx.close())
                elif protocol == "modbus" and hasattr(sdk, "modbus_close"):
                    run_in_new_loop(lambda: sdk.modbus_close(ctx))
                elif hasattr(sdk, "close_device_handler"):
                    run_in_new_loop(lambda: sdk.close_device_handler(ctx))
                elif hasattr(ctx, "close"):
                    run_in_new_loop(lambda: ctx.close())
            except Exception as e:
                print(f"Error closing device on exit: {e}")
            self.connection_panel.ctx = None
        self.device = None
        event.accept()


class Revo3TouchPanel(Revo3TouchSubPanel):
    def set_device(self, device, slave_id, device_info=None, shared_data=None):
        super().set_device(device, slave_id, device_info, shared_data)
        self.device_info = device_info
        self.shared_data = shared_data
        if shared_data:
            shared_data.touch_updated.connect(self.update_data)

    def clear_device(self):
        super().clear_device()
        if getattr(self, "shared_data", None):
            try:
                self.shared_data.touch_updated.disconnect(self.update_data)
            except RuntimeError:
                pass
        self.device_info = None
        self.shared_data = None
