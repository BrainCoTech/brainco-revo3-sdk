"""Revo3-only system configuration panel with legacy-style sub-tabs."""

import asyncio
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional, TYPE_CHECKING

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from .i18n import tr

sys.path.insert(0, str(Path(__file__).parent.parent))
from common_imports import sdk, run_async

if TYPE_CHECKING:
    from .shared_data import SharedDataManager


class SystemConfigPanel(QWidget):
    slave_id_changed = Signal(int)
    request_reconnect = Signal(object)

    def __init__(self):
        super().__init__()
        self.shared_data: Optional["SharedDataManager"] = None
        self.protocol = None
        self._loading_settings = False
        self._setup_ui()
        self.update_texts()

    @property
    def device(self):
        return self.shared_data.device if self.shared_data else None

    @property
    def slave_id(self):
        return self.shared_data.slave_id if self.shared_data else 1

    @property
    def device_info(self):
        return self.shared_data.device_info if self.shared_data else None

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        self.tabs = QTabWidget()
        self.tabs.setUsesScrollButtons(True)
        self.tabs.setElideMode(Qt.ElideNone)
        layout.addWidget(self.tabs, 1)

        self._setup_basic_tab()
        self._setup_runtime_tab()
        self._setup_comm_tab()
        self._setup_revo3_status_tab()

        self.log_group = QGroupBox()
        log_layout = QVBoxLayout(self.log_group)
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumHeight(130)
        log_layout.addWidget(self.log_text)
        layout.addWidget(self.log_group)

    def _setup_basic_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(12)

        self.info_group = QGroupBox()
        info_layout = QFormLayout(self.info_group)
        self.sn_title = QLabel()
        self.sn_label = QLabel("--")
        info_layout.addRow(self.sn_title, self.sn_label)
        self.fw_title = QLabel()
        self.fw_label = QLabel("--")
        info_layout.addRow(self.fw_title, self.fw_label)
        self.hw_title = QLabel()
        self.hw_label = QLabel("--")
        info_layout.addRow(self.hw_title, self.hw_label)
        self.hw_version_title = QLabel("Hardware Version:")
        self.hw_version_label = QLabel("--")
        info_layout.addRow(self.hw_version_title, self.hw_version_label)
        self.sku_title = QLabel("SKU:")
        self.sku_label = QLabel("--")
        info_layout.addRow(self.sku_title, self.sku_label)
        self.protocol_title = QLabel("Protocol:")
        self.protocol_label = QLabel("--")
        info_layout.addRow(self.protocol_title, self.protocol_label)
        layout.addWidget(self.info_group)

        self.slave_id_group = QGroupBox()
        slave_layout = QHBoxLayout(self.slave_id_group)
        self.new_slave_id_label = QLabel()
        slave_layout.addWidget(self.new_slave_id_label)
        self.new_slave_id_spin = QSpinBox()
        self.new_slave_id_spin.setRange(1, 255)
        self.new_slave_id_spin.setValue(1)
        slave_layout.addWidget(self.new_slave_id_spin)
        self.set_slave_id_btn = QPushButton()
        self.set_slave_id_btn.clicked.connect(self._set_slave_id)
        slave_layout.addWidget(self.set_slave_id_btn)
        slave_layout.addStretch()
        layout.addWidget(self.slave_id_group)

        self.system_group = QGroupBox()
        system_layout = QHBoxLayout(self.system_group)
        self.reboot_btn = QPushButton()
        self.reboot_btn.clicked.connect(self._reboot)
        system_layout.addWidget(self.reboot_btn)
        self.factory_reset_btn = QPushButton()
        self.factory_reset_btn.clicked.connect(self._factory_reset)
        system_layout.addWidget(self.factory_reset_btn)
        system_layout.addStretch()
        layout.addWidget(self.system_group)

        layout.addStretch()
        self.tabs.addTab(widget, "")

    def _setup_runtime_tab(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(12)

        self.calib_group = QGroupBox()
        calib_layout = QVBoxLayout(self.calib_group)
        row = QHBoxLayout()
        self.auto_calib_check = QCheckBox()
        self.auto_calib_check.stateChanged.connect(self._on_auto_calib_changed)
        row.addWidget(self.auto_calib_check)
        row.addStretch()
        calib_layout.addLayout(row)
        row = QHBoxLayout()
        self.manual_calib_btn = QPushButton()
        self.manual_calib_btn.clicked.connect(self._manual_calibrate)
        row.addWidget(self.manual_calib_btn)
        row.addStretch()
        calib_layout.addLayout(row)
        layout.addWidget(self.calib_group)

        self.runtime_group = QGroupBox("Runtime Flags")
        runtime_layout = QGridLayout(self.runtime_group)
        self.touch_screen_check = QCheckBox()
        self.touch_screen_check.stateChanged.connect(self._on_touch_screen_changed)
        self.teaching_mode_check = QCheckBox()
        self.teaching_mode_check.stateChanged.connect(self._on_teaching_mode_changed)
        self.software_estop_check = QCheckBox("Software E-Stop")
        self.software_estop_check.stateChanged.connect(self._on_software_estop_changed)
        self.broadcast_id_check = QCheckBox("Use Broadcast ID")
        self.broadcast_id_check.stateChanged.connect(self._on_broadcast_id_changed)
        runtime_layout.addWidget(self.touch_screen_check, 0, 0)
        runtime_layout.addWidget(self.teaching_mode_check, 0, 1)
        runtime_layout.addWidget(self.software_estop_check, 1, 0)
        runtime_layout.addWidget(self.broadcast_id_check, 1, 1)
        runtime_layout.setColumnStretch(2, 1)
        layout.addWidget(self.runtime_group)

        self.protection_group = QGroupBox("Protection")
        protection_layout = QHBoxLayout(self.protection_group)
        protection_layout.addWidget(QLabel("Global Protect Current (mA):"))
        self.global_current_spin = QSpinBox()
        self.global_current_spin.setRange(0, 10000)
        self.global_current_spin.setValue(1500)
        protection_layout.addWidget(self.global_current_spin)
        self.apply_global_current_btn = QPushButton()
        self.apply_global_current_btn.clicked.connect(self._apply_global_current)
        protection_layout.addWidget(self.apply_global_current_btn)
        protection_layout.addStretch()
        layout.addWidget(self.protection_group)

        refresh = QHBoxLayout()
        self.refresh_runtime_btn = QPushButton()
        self.refresh_runtime_btn.clicked.connect(self._load_runtime_settings)
        refresh.addWidget(self.refresh_runtime_btn)
        refresh.addStretch()
        layout.addLayout(refresh)

        layout.addStretch()
        scroll.setWidget(widget)
        self.tabs.addTab(scroll, "")

    def _setup_comm_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(12)

        self.current_baud_group = QGroupBox("Current Connection")
        self.current_layout = QFormLayout(self.current_baud_group)
        self.current_protocol_label = QLabel("--")
        self.current_layout.addRow("Protocol:", self.current_protocol_label)
        self.current_modbus_label = QLabel("--")
        self.current_layout.addRow("Modbus Baudrate:", self.current_modbus_label)
        self.current_can_arb_label = QLabel("--")
        self.current_layout.addRow("CAN Arbitration:", self.current_can_arb_label)
        self.current_can_data_label = QLabel("--")
        self.current_layout.addRow("CANFD Data:", self.current_can_data_label)
        layout.addWidget(self.current_baud_group)

        self.modbus_group = QGroupBox("Modbus/RS485 Baudrate")
        modbus_layout = QHBoxLayout(self.modbus_group)
        modbus_layout.addWidget(QLabel("Baudrate:"))
        self.modbus_baud_combo = QComboBox()
        self.modbus_baud_combo.addItems(["1 Mbps", "2 Mbps", "3 Mbps", "5 Mbps"])
        modbus_layout.addWidget(self.modbus_baud_combo)
        self.modbus_baud_btn = QPushButton("Set")
        self.modbus_baud_btn.clicked.connect(self._set_modbus_baudrate)
        modbus_layout.addWidget(self.modbus_baud_btn)
        modbus_layout.addStretch()
        layout.addWidget(self.modbus_group)

        self.canfd_group = QGroupBox("CANFD Data Baudrate")
        canfd_layout = QHBoxLayout(self.canfd_group)
        canfd_layout.addWidget(QLabel("Data Rate:"))
        self.canfd_baud_combo = QComboBox()
        self.canfd_baud_combo.addItems(["1 Mbps", "2 Mbps", "4 Mbps", "5 Mbps"])
        canfd_layout.addWidget(self.canfd_baud_combo)
        self.canfd_baud_btn = QPushButton("Set")
        self.canfd_baud_btn.clicked.connect(self._set_canfd_baudrate)
        canfd_layout.addWidget(self.canfd_baud_btn)
        canfd_layout.addStretch()
        layout.addWidget(self.canfd_group)

        refresh = QHBoxLayout()
        self.refresh_comm_btn = QPushButton()
        self.refresh_comm_btn.clicked.connect(self._load_comm_settings)
        refresh.addWidget(self.refresh_comm_btn)
        refresh.addStretch()
        layout.addLayout(refresh)
        layout.addStretch()
        self.tabs.addTab(widget, "")

    def _setup_revo3_status_tab(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(12)

        self.revo3_sys_group = QGroupBox()
        sys_layout = QGridLayout(self.revo3_sys_group)
        self.sys_state_label = QLabel("--")
        self.sys_error_label = QLabel("--")
        self.sys_current_label = QLabel("--")
        self.sys_voltage_label = QLabel("--")
        self.sys_power_label = QLabel("--")
        self.sys_temp_label = QLabel("--")
        self.lbl_sys_state_title = QLabel()
        self.lbl_error_code_title = QLabel()
        self.lbl_current_title = QLabel()
        self.lbl_voltage_title = QLabel()
        self.lbl_power_title = QLabel()
        self.lbl_temp_title = QLabel()
        sys_layout.addWidget(self.lbl_sys_state_title, 0, 0)
        sys_layout.addWidget(self.sys_state_label, 0, 1)
        sys_layout.addWidget(self.lbl_error_code_title, 0, 2)
        sys_layout.addWidget(self.sys_error_label, 0, 3)
        sys_layout.addWidget(self.lbl_current_title, 1, 0)
        sys_layout.addWidget(self.sys_current_label, 1, 1)
        sys_layout.addWidget(self.lbl_voltage_title, 1, 2)
        sys_layout.addWidget(self.sys_voltage_label, 1, 3)
        sys_layout.addWidget(self.lbl_power_title, 2, 0)
        sys_layout.addWidget(self.sys_power_label, 2, 1)
        sys_layout.addWidget(self.lbl_temp_title, 2, 2)
        sys_layout.addWidget(self.sys_temp_label, 2, 3)
        sys_layout.setColumnStretch(4, 1)
        layout.addWidget(self.revo3_sys_group)

        self.revo3_motor_group = QGroupBox()
        motor_layout = QVBoxLayout(self.revo3_motor_group)
        grid = QGridLayout()
        grid.setSpacing(8)
        self.lbl_motor_id = QLabel()
        self.lbl_motor_sn = QLabel()
        self.lbl_motor_fw = QLabel()
        self.lbl_motor_temp = QLabel("Temp")
        self.lbl_motor_error = QLabel("Error")
        grid.addWidget(self.lbl_motor_id, 0, 0)
        grid.addWidget(self.lbl_motor_sn, 0, 1)
        grid.addWidget(self.lbl_motor_fw, 0, 2)
        grid.addWidget(self.lbl_motor_temp, 0, 3)
        grid.addWidget(self.lbl_motor_error, 0, 4)
        self.motor_row_labels = []
        self.motor_sn_labels = []
        self.motor_fw_labels = []
        self.motor_temp_labels = []
        self.motor_error_labels = []
        for i in range(21):
            row = i + 1
            row_label = QLabel(f"Motor {i}")
            self.motor_row_labels.append(row_label)
            grid.addWidget(row_label, row, 0)
            sn_label = QLabel("--")
            self.motor_sn_labels.append(sn_label)
            grid.addWidget(sn_label, row, 1)
            fw_label = QLabel("--")
            self.motor_fw_labels.append(fw_label)
            grid.addWidget(fw_label, row, 2)
            temp_label = QLabel("--")
            self.motor_temp_labels.append(temp_label)
            grid.addWidget(temp_label, row, 3)
            error_label = QLabel("--")
            self.motor_error_labels.append(error_label)
            grid.addWidget(error_label, row, 4)
        grid.setColumnStretch(5, 1)
        motor_layout.addLayout(grid)
        layout.addWidget(self.revo3_motor_group)

        refresh = QHBoxLayout()
        self.refresh_revo3_btn = QPushButton()
        self.refresh_revo3_btn.clicked.connect(self._load_revo3_status)
        refresh.addWidget(self.refresh_revo3_btn)
        refresh.addStretch()
        layout.addLayout(refresh)

        layout.addStretch()
        scroll.setWidget(widget)
        self.tabs.addTab(scroll, "")

    def set_device(self, device, slave_id, device_info, protocol=None, shared_data=None):
        self.shared_data = shared_data
        self.protocol = protocol
        self.protocol_label.setText(protocol or "--")
        self.current_protocol_label.setText(protocol or "--")
        self.new_slave_id_spin.setValue(slave_id)

        if device_info:
            self.sn_label.setText(getattr(device_info, "serial_number", "--"))
            self.fw_label.setText(getattr(device_info, "firmware_version", "--"))
            self.hw_version_label.setText(getattr(device_info, "hardware_version", "--") or "--")
            self.hw_label.setText(self._enum_name(getattr(device_info, "hardware_type", "--")))
            self.sku_label.setText(self._enum_name(getattr(device_info, "sku_type", "--")))

        self._load_runtime_settings()
        self._load_comm_settings()
        self._load_revo3_status()

    def clear_device(self):
        self.shared_data = None
        for label in [
            self.sn_label,
            self.fw_label,
            self.hw_label,
            self.hw_version_label,
            self.sku_label,
            self.protocol_label,
            self.current_protocol_label,
            self.current_modbus_label,
            self.current_can_arb_label,
            self.current_can_data_label,
            self.sys_state_label,
            self.sys_error_label,
            self.sys_current_label,
            self.sys_voltage_label,
            self.sys_power_label,
            self.sys_temp_label,
        ]:
            label.setText("--")
        for labels in [
            self.motor_sn_labels,
            self.motor_fw_labels,
            self.motor_temp_labels,
            self.motor_error_labels,
        ]:
            for label in labels:
                label.setText("--")

    def update_texts(self):
        self.info_group.setTitle(tr("device_info"))
        self.sn_title.setText(tr("serial_number") + ":")
        self.fw_title.setText(tr("firmware_version") + ":")
        self.hw_title.setText(tr("hardware_type") + ":")
        self.slave_id_group.setTitle(tr("slave_id_settings"))
        self.new_slave_id_label.setText(tr("new_slave_id") + ":")
        self.set_slave_id_btn.setText(tr("btn_set"))
        self.system_group.setTitle(tr("system_control"))
        self.reboot_btn.setText(tr("btn_reboot"))
        self.factory_reset_btn.setText(tr("btn_factory_reset"))
        self.calib_group.setTitle(tr("position_calibration"))
        self.auto_calib_check.setText(tr("auto_calibration"))
        self.manual_calib_btn.setText(tr("manual_calibration"))
        self.touch_screen_check.setText(tr("v3_touch_screen"))
        self.teaching_mode_check.setText(tr("v3_teaching_mode"))
        self.runtime_group.setTitle(tr("runtime_flags"))
        self.protection_group.setTitle(tr("protection"))
        self.apply_global_current_btn.setText(tr("apply"))
        self.refresh_runtime_btn.setText(tr("refresh_settings"))
        self.refresh_comm_btn.setText(tr("refresh_settings"))
        self.refresh_revo3_btn.setText(tr("refresh_status_info"))
        self.log_group.setTitle(tr("operation_log"))
        self.revo3_sys_group.setTitle(tr("revo3_status"))
        self.revo3_motor_group.setTitle(tr("motor_info"))
        self.lbl_sys_state_title.setText(tr("system_state") + ":")
        self.lbl_error_code_title.setText(tr("error_code") + ":")
        self.lbl_current_title.setText(tr("current_ma") + ":")
        self.lbl_voltage_title.setText(tr("voltage_v") + ":")
        self.lbl_power_title.setText(tr("power_w") + ":")
        self.lbl_temp_title.setText(tr("temperature_c") + ":")
        self.lbl_motor_id.setText(tr("motor_id"))
        self.lbl_motor_sn.setText(tr("v3_sn"))
        self.lbl_motor_fw.setText(tr("v3_fw"))
        for i, label in enumerate(self.motor_row_labels):
            label.setText(f"Motor {i}")
        self.tabs.setTabText(0, "📋 " + tr("device_info"))
        self.tabs.setTabText(1, "⚙ " + tr("revo3_runtime"))
        self.tabs.setTabText(2, "📡 " + tr("communication"))
        self.tabs.setTabText(3, "📊 " + tr("revo3_status"))

    def _load_runtime_settings(self):
        if not self.device:
            return
        self._loading_settings = True
        try:
            self.auto_calib_check.setChecked(bool(self._call_bool("revo3_get_auto_calibration", False)))
            self.touch_screen_check.setChecked(bool(self._call_bool("revo3_get_touch_screen", False)))
            self.teaching_mode_check.setChecked(bool(self._call_bool("revo3_get_teaching_mode", False)))
            self.software_estop_check.setChecked(bool(self._call_bool("revo3_get_software_e_stop", False)))
            self.broadcast_id_check.setChecked(bool(self._call_bool("revo3_get_use_broadcast_id", False)))
            if hasattr(self.device, "revo3_get_global_protect_current"):
                current = run_async(lambda: self.device.revo3_get_global_protect_current(self.slave_id))
                if current is not None:
                    self.global_current_spin.setValue(int(float(current)))
            self._log("Runtime settings loaded")
        except Exception as e:
            self._log(f"Failed to load runtime settings: {e}")
        finally:
            self._loading_settings = False

    def _load_comm_settings(self):
        if not self.device:
            return
        run_async(self._async_load_comm_settings)

    async def _async_load_comm_settings(self):
        protocol = self.protocol or ""
        self.current_protocol_label.setText(protocol or "--")
        self.current_modbus_label.setText("N/A")
        self.current_can_arb_label.setText("N/A")
        self.current_can_data_label.setText("N/A")

        is_modbus = "Modbus" in protocol or "Mock" in protocol
        is_canfd = "CANFD" in protocol

        if hasattr(self, "current_layout"):
            label_modbus = self.current_layout.labelForField(self.current_modbus_label)
            if label_modbus:
                label_modbus.setVisible(is_modbus)
            self.current_modbus_label.setVisible(is_modbus)

            label_can_arb = self.current_layout.labelForField(self.current_can_arb_label)
            if label_can_arb:
                label_can_arb.setVisible(is_canfd)
            self.current_can_arb_label.setVisible(is_canfd)

            label_can_data = self.current_layout.labelForField(self.current_can_data_label)
            if label_can_data:
                label_can_data.setVisible(is_canfd)
            self.current_can_data_label.setVisible(is_canfd)

        self.modbus_group.setEnabled(is_modbus)
        self.canfd_group.setEnabled(is_canfd)
        try:
            if "Modbus" in protocol or "Mock" in protocol:
                if hasattr(self.device, "revo3_get_rs485_baudrate"):
                    baud = await self.device.revo3_get_rs485_baudrate(self.slave_id)
                    self.current_modbus_label.setText(self._enum_name(baud))

                    # Update ComboBox default selection
                    baud_val = getattr(baud, "value", None)
                    if baud_val is None:
                        baud_map = {
                            "Baud1Mbps": 0,
                            "Baud2Mbps": 1,
                            "Baud3Mbps": 2,
                            "Baud5Mbps": 3
                        }
                    else:
                        baud_map = {
                            1: 0,
                            2: 1,
                            3: 2,
                            5: 3
                        }
                    idx = baud_map.get(baud_val if baud_val is not None else self._enum_name(baud))
                    if idx is not None:
                        self.modbus_baud_combo.setCurrentIndex(idx)

            elif "CANFD" in protocol:
                if hasattr(self.device, "revo3_get_canfd_baudrate"):
                    baud = await self.device.revo3_get_canfd_baudrate(self.slave_id)
                    self.current_can_data_label.setText(self._enum_name(baud))
                    
                    # Update ComboBox default selection
                    baud_val = getattr(baud, "value", None)
                    if baud_val is None:
                        baud_map = {
                            "Baud1Mbps": 0,
                            "Baud2Mbps": 1,
                            "Baud4Mbps": 2,
                            "Baud5Mbps": 3
                        }
                    else:
                        baud_map = {
                            1: 0,
                            2: 1,
                            4: 2,
                            5: 3
                        }
                    idx = baud_map.get(baud_val if baud_val is not None else self._enum_name(baud))
                    if idx is not None:
                        self.canfd_baud_combo.setCurrentIndex(idx)

        except Exception as e:
            self._log(f"Failed to load communication settings: {e}")
        self._log("Communication settings refreshed")

    def _load_revo3_status(self):
        if not self.device:
            return
        run_async(self._async_load_revo3_status)

    async def _async_load_revo3_status(self):
        device = self.device
        if not device:
            return
        try:
            status = await device.revo3_get_system_status(self.slave_id)
            self.sys_state_label.setText(str(getattr(status, "system_state", "--")))
            self.sys_error_label.setText(str(getattr(status, "error_code", "--")))
            self.sys_current_label.setText(str(getattr(status, "current_ma", "--")))
            self.sys_voltage_label.setText(str(getattr(status, "voltage_v", "--")))
            self.sys_power_label.setText(str(getattr(status, "power_w", "--")))
            self.sys_temp_label.setText(str(getattr(status, "temperature_c", "--")))
        except Exception as e:
            self._log(f"Failed to load system status: {e}")

        for method_name, labels in [
            ("revo3_get_all_motor_sns", self.motor_sn_labels),
            ("revo3_get_motor_fw_versions", self.motor_fw_labels),
            ("revo3_get_all_motor_temperatures", self.motor_temp_labels),
            ("revo3_get_all_motor_errors", self.motor_error_labels),
        ]:
            try:
                values = await getattr(device, method_name)(self.slave_id)
                for i, value in enumerate(list(values)[:21]):
                    labels[i].setText(str(value))
            except Exception as e:
                self._log(f"{method_name} failed: {e}")
        self._log("Status refreshed")

    def _set_slave_id(self):
        new_id = self.new_slave_id_spin.value()
        self.slave_id_changed.emit(new_id)
        self._log(f"Slave ID updated in GUI context: {new_id}")

    def _reboot(self):
        if not self.device:
            return
        
        reply = QMessageBox.question(
            self,
            tr("confirm"),
            tr("confirm_reboot"),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply == QMessageBox.No:
            return

        if self.shared_data:
            self.shared_data.stop()

        try:
            if hasattr(self.device, "revo3_reboot"):
                run_async(lambda: self.device.revo3_reboot(self.slave_id), raise_exception=True)
            self._log("Reboot requested")
        except Exception as e:
            err_msg = str(e).lower()
            if any(x in err_msg for x in ["timeout", "closed", "connection", "broken pipe", "invalid crc", "io error"]):
                # Hand will reboot and disconnect immediately. Catching timeouts or port closed exceptions is expected.
                self._log(f"Reboot command sent, connection closed (expected): {e}")
            else:
                self._log(f"Failed to reboot: {e}")
                QMessageBox.critical(
                    self,
                    tr("btn_reboot"),
                    f"Reboot command failed:\n{e}"
                )
                if self.shared_data:
                    self.shared_data.start()
                return

        QMessageBox.information(
            self,
            tr("btn_reboot"),
            tr("reboot_info_msg")
        )
        self.request_reconnect.emit(None)

    def _factory_reset(self):
        if not self.device:
            return
        reply = QMessageBox.question(
            self,
            tr("confirm"),
            tr("confirm_factory_reset"),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            if hasattr(self.device, "revo3_reset_finger_defaults"):
                run_async(lambda: self.device.revo3_reset_finger_defaults(self.slave_id))
            self._log("Factory defaults requested")

    def _manual_calibrate(self):
        if not self.device:
            return
        if hasattr(self.device, "revo3_manual_calibration"):
            run_async(lambda: self.device.revo3_manual_calibration(self.slave_id))
        self._log("Manual calibration requested")

    def _on_auto_calib_changed(self, state):
        self._set_flag("revo3_set_auto_calibration", state == Qt.Checked.value, "Auto calibration")

    def _on_touch_screen_changed(self, state):
        self._set_flag("revo3_set_touch_screen", state == Qt.Checked.value, "Touch screen")

    def _on_teaching_mode_changed(self, state):
        self._set_flag("revo3_set_teaching_mode", state == Qt.Checked.value, "Teaching mode")

    def _on_software_estop_changed(self, state):
        self._set_flag("revo3_set_software_e_stop", state == Qt.Checked.value, "Software E-Stop")

    def _on_broadcast_id_changed(self, state):
        self._set_flag("revo3_set_use_broadcast_id", state == Qt.Checked.value, "Use broadcast ID")

    def _set_flag(self, method_name: str, enabled: bool, label: str):
        if self._loading_settings or not self.device or not hasattr(self.device, method_name):
            return
        try:
            run_async(lambda: getattr(self.device, method_name)(self.slave_id, enabled))
            self._log(f"{label}: {enabled}")
        except Exception as e:
            self._log(f"Failed to set {label}: {e}")

    def _apply_global_current(self):
        if not self.device or not hasattr(self.device, "revo3_set_global_protect_current"):
            return
        value = self.global_current_spin.value()
        try:
            run_async(lambda: self.device.revo3_set_global_protect_current(self.slave_id, value))
            self._log(f"Global protect current set to {value} mA")
        except Exception as e:
            self._log(f"Failed to set global protect current: {e}")

    def _set_modbus_baudrate(self):
        if not self.device or not hasattr(self.device, "revo3_set_rs485_baudrate"):
            return
        idx = self.modbus_baud_combo.currentIndex()
        # Options: ["1 Mbps", "2 Mbps", "3 Mbps", "5 Mbps"]
        baud_map = {
            0: sdk.Baudrate.Baud1Mbps,
            1: sdk.Baudrate.Baud2Mbps,
            2: sdk.Baudrate.Baud3Mbps,
            3: sdk.Baudrate.Baud5Mbps,
        }
        baud_enum = baud_map.get(idx)
        if baud_enum is None:
            return

        current_baud = self._read_current_modbus_baudrate()
        if current_baud == baud_enum:
            self._log(f"RS485 baudrate already {self._enum_name(baud_enum)}; no change needed")
            self.current_modbus_label.setText(self._enum_name(baud_enum))
            return

        reply = QMessageBox.question(
            self,
            "Confirm Baudrate Change",
            f"Are you sure you want to change the RS485 baudrate to {self._enum_name(baud_enum)}?\n\n"
            "Warning: This will interrupt the current connection. The system will automatically reconnect using the new baudrate.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply == QMessageBox.No:
            return

        if self.shared_data:
            self.shared_data.stop()

        try:
            run_async(lambda: self.device.revo3_set_rs485_baudrate(self.slave_id, baud_enum), raise_exception=True)
            self._log(f"RS485 baudrate set to {self._enum_name(baud_enum)}")
        except Exception as e:
            # Under Modbus RTU, switching the baudrate immediately cuts off the connection,
            # which naturally produces a timeout, CRC, or write failure. We treat this as expected.
            self._log(f"Baudrate command sent; connection closed as expected during rate switch: {e}")

        # Wait for the hardware port rate switch to stabilize
        import time
        time.sleep(0.5)

        # Actively disconnect and reset panel states before showing the blocking dialog.
        # This releases the serial port and avoids residual timer ticks from polluting
        # the port with junk frames while the QMessageBox blocks the main UI thread.
        if self.shared_data:
            self.shared_data.connection_lost.emit()

        QMessageBox.information(
            self,
            "Baudrate Change Sent",
            "Baudrate change command has been sent. The system will now automatically scan and reconnect to verify the connection at the new baudrate."
        )
        self._load_comm_settings()
        self.request_reconnect.emit(baud_enum)

    def _read_current_modbus_baudrate(self):
        if not self.device or not hasattr(self.device, "revo3_get_rs485_baudrate"):
            return None
        try:
            return run_async(lambda: self.device.revo3_get_rs485_baudrate(self.slave_id), raise_exception=True)
        except Exception as e:
            self._log(f"Could not read current RS485 baudrate before setting: {e}")
            return None

    def _set_canfd_baudrate(self):
        if not self.device or not hasattr(self.device, "revo3_set_canfd_baudrate"):
            return
        idx = self.canfd_baud_combo.currentIndex()
        # Options: ["1 Mbps", "2 Mbps", "4 Mbps", "5 Mbps"]
        baud_map = {
            0: sdk.BaudrateCAN.Baud1Mbps,
            1: sdk.BaudrateCAN.Baud2Mbps,
            2: sdk.BaudrateCAN.Baud4Mbps,
            3: sdk.BaudrateCAN.Baud5Mbps,
        }
        baud_enum = baud_map.get(idx)
        if baud_enum is None:
            return

        reply = QMessageBox.question(
            self,
            "Confirm CANFD Baudrate Change",
            f"Are you sure you want to change the CANFD data baudrate to {self._enum_name(baud_enum)}?\n\n"
            "Warning: This will interrupt the current connection. The system will automatically reconnect using the new baudrate.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply == QMessageBox.No:
            return

        if self.shared_data:
            self.shared_data.stop()

        try:
            run_async(lambda: self.device.revo3_set_canfd_baudrate(self.slave_id, baud_enum), raise_exception=True)
            self._log(f"CANFD baudrate set to {self._enum_name(baud_enum)}")
        except Exception as e:
            err_msg = str(e).lower()
            if any(x in err_msg for x in ["timeout", "closed", "connection", "broken pipe", "invalid crc", "io error"]):
                self._log(f"CANFD baudrate command sent, timed out or closed (expected): {e}")
            else:
                self._log(f"Failed to set CANFD baudrate: {e}")
                QMessageBox.critical(
                    self,
                    "Baudrate Change Failed",
                    f"Failed to change CANFD data baudrate:\n{e}"
                )
                if self.shared_data:
                    self.shared_data.start()
                return

        # Wait a short period for the hardware port rate switch to stabilize
        import time
        time.sleep(0.5)

        QMessageBox.information(
            self,
            "Baudrate Change Sent",
            "Baudrate change command has been sent. The system will now automatically scan and reconnect to verify the connection at the new data baudrate."
        )
        self._load_comm_settings()
        self.request_reconnect.emit(None)

    def _call_bool(self, method_name: str, default: bool):
        if not hasattr(self.device, method_name):
            return default
        return run_async(lambda: getattr(self.device, method_name)(self.slave_id))

    def _enum_name(self, value):
        if hasattr(value, "name"):
            return value.name
        text = str(value)
        return text.split(".")[-1]

    def _log(self, message):
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.append(f"[{timestamp}] {message}")
