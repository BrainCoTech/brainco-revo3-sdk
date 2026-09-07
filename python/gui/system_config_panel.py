"""Revo3-only system configuration panel with task-oriented sub-tabs."""

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
from common_imports import sdk, run_async, logger

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
        self._touch_layout = None
        self._touch_firmware_versions = []
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

        self.log_group = QGroupBox()
        log_layout = QVBoxLayout(self.log_group)
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumHeight(130)
        log_layout.addWidget(self.log_text)
        layout.addWidget(self.log_group)

    def _setup_basic_tab(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
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
        self.touch_fw_title = QLabel("Touch Firmware:")
        self.touch_fw_label = QLabel("--")
        self.touch_fw_label.setWordWrap(True)
        self.touch_fw_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        info_layout.addRow(self.touch_fw_title, self.touch_fw_label)
        self.hw_title = QLabel()
        self.hw_label = QLabel("--")
        info_layout.addRow(self.hw_title, self.hw_label)
        self.hw_version_title = QLabel("Hardware Version:")
        self.hw_version_label = QLabel("--")
        info_layout.addRow(self.hw_version_title, self.hw_version_label)
        self.sku_title = QLabel("SKU:")
        self.sku_label = QLabel("--")
        info_layout.addRow(self.sku_title, self.sku_label)
        self.touch_layout_title = QLabel("Touch Layout:")
        self.touch_layout_label = QLabel("--")
        self.touch_layout_label.setWordWrap(True)
        self.touch_layout_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        info_layout.addRow(self.touch_layout_title, self.touch_layout_label)
        layout.addWidget(self.info_group)

        self._setup_overview_status(layout)

        layout.addStretch()
        scroll.setWidget(widget)
        self.tabs.addTab(scroll, "")

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
        self.auto_clear_faults_check = QCheckBox()
        self.auto_clear_faults_check.stateChanged.connect(
            self._on_auto_clear_faults_changed
        )
        runtime_layout.addWidget(self.touch_screen_check, 0, 0)
        runtime_layout.addWidget(self.teaching_mode_check, 0, 1)
        runtime_layout.addWidget(self.software_estop_check, 1, 0)
        runtime_layout.addWidget(self.broadcast_id_check, 1, 1)
        runtime_layout.addWidget(self.auto_clear_faults_check, 2, 0)
        runtime_layout.setColumnStretch(0, 1)
        runtime_layout.setColumnStretch(1, 1)
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

        self.system_group = QGroupBox()
        system_layout = QHBoxLayout(self.system_group)
        self.reboot_btn = QPushButton()
        self.reboot_btn.clicked.connect(self._reboot)
        system_layout.addWidget(self.reboot_btn)
        self.factory_reset_btn = QPushButton()
        self.factory_reset_btn.clicked.connect(self._factory_reset)
        self.factory_reset_btn.setStyleSheet("color: #c0392b;")
        system_layout.addWidget(self.factory_reset_btn)
        system_layout.addStretch()
        layout.addWidget(self.system_group)

        layout.addStretch()
        scroll.setWidget(widget)
        self.tabs.addTab(scroll, "")

    def _setup_comm_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(12)

        self.current_baud_group = QGroupBox("Current Connection")
        self.current_layout = QFormLayout(self.current_baud_group)
        self.protocol_label = QLabel("--")
        self.current_protocol_label = self.protocol_label
        self.current_layout.addRow("Protocol:", self.protocol_label)
        self.port_label = QLabel("--")
        self.current_layout.addRow("Port:", self.port_label)
        self.connected_slave_id_label = QLabel("--")
        self.current_layout.addRow("Slave ID:", self.connected_slave_id_label)
        self.current_modbus_label = QLabel("--")
        self.current_layout.addRow("Modbus Baudrate:", self.current_modbus_label)
        self.current_can_arb_label = QLabel("--")
        self.current_layout.addRow("CAN Arbitration Rate:", self.current_can_arb_label)
        self.current_can_data_label = QLabel("--")
        self.current_layout.addRow("CANFD Data Rate:", self.current_can_data_label)
        layout.addWidget(self.current_baud_group)

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

    def _setup_overview_status(self, layout):
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

        self.motor_summary_group = QGroupBox()
        summary_layout = QHBoxLayout(self.motor_summary_group)
        self.motor_online_summary = QLabel("--")
        self.motor_temp_summary = QLabel("--")
        self.motor_fault_summary = QLabel("--")
        summary_layout.addWidget(self.motor_online_summary)
        summary_layout.addWidget(self.motor_temp_summary)
        summary_layout.addWidget(self.motor_fault_summary)
        summary_layout.addStretch()
        self.motor_details_check = QCheckBox()
        summary_layout.addWidget(self.motor_details_check)
        layout.addWidget(self.motor_summary_group)

        self.revo3_motor_group = QGroupBox()
        motor_layout = QVBoxLayout(self.revo3_motor_group)
        grid = QGridLayout()
        grid.setSpacing(8)
        self.lbl_motor_id = QLabel()
        self.lbl_motor_sn = QLabel()
        self.lbl_motor_fw = QLabel()
        self.lbl_motor_temp = QLabel("Temp")
        self.lbl_motor_faults = QLabel("Error")
        grid.addWidget(self.lbl_motor_id, 0, 0)
        grid.addWidget(self.lbl_motor_sn, 0, 1)
        grid.addWidget(self.lbl_motor_fw, 0, 2)
        grid.addWidget(self.lbl_motor_temp, 0, 3)
        grid.addWidget(self.lbl_motor_faults, 0, 4)
        self.motor_row_labels = []
        self.motor_sn_labels = []
        self.motor_fw_labels = []
        self.motor_temp_labels = []
        self.motor_faults_labels = []
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
            self.motor_faults_labels.append(error_label)
            grid.addWidget(error_label, row, 4)
        grid.setColumnStretch(5, 1)
        motor_layout.addLayout(grid)
        layout.addWidget(self.revo3_motor_group)
        self.revo3_motor_group.setVisible(False)
        self.motor_details_check.toggled.connect(self.revo3_motor_group.setVisible)

        refresh = QHBoxLayout()
        self.refresh_revo3_btn = QPushButton()
        self.refresh_revo3_btn.clicked.connect(self._load_revo3_status)
        refresh.addWidget(self.refresh_revo3_btn)
        refresh.addStretch()
        layout.addLayout(refresh)

    def set_device(self, device, slave_id, device_info, protocol=None, shared_data=None):
        self.shared_data = shared_data
        self.protocol = protocol
        self.protocol_label.setText(protocol or "--")
        self.current_protocol_label.setText(protocol or "--")
        self.new_slave_id_spin.setValue(slave_id)

        if device_info:
            self.sn_label.setText(getattr(device_info, "serial_number", "--"))
            self.fw_label.setText(getattr(device_info, "firmware_version", "--"))
            self.hw_version_label.setText(getattr(device_info, "hardware_revision", "--") or "--")
            self.hw_label.setText(self._enum_name(getattr(device_info, "model", "--")))
            self.sku_label.setText(self._enum_name(getattr(device_info, "hand_side", "--")))
        self.update_touch_layout(self._device_touch_layout(device))
        self.connected_slave_id_label.setText(f"0x{slave_id:02X} ({slave_id})")

        self._load_runtime_settings()
        self._load_comm_settings()
        self._load_revo3_status()

    def set_connection_info(self, info):
        self.protocol_label.setText(info.get("protocol") or "--")
        self.current_protocol_label.setText(info.get("protocol") or "--")
        self.port_label.setText(info.get("port") or "--")
        slave_id = info.get("slave_id")
        self.connected_slave_id_label.setText(
            f"0x{slave_id:02X} ({slave_id})" if isinstance(slave_id, int) else "--"
        )
        canfd_arbitration_baudrate = info.get("canfd_arbitration_baudrate")
        if canfd_arbitration_baudrate:
            self.current_can_arb_label.setText(
                self._format_baudrate(canfd_arbitration_baudrate)
            )

    def clear_device(self):
        self.shared_data = None
        self._touch_layout = None
        self._touch_firmware_versions = []
        for label in [
            self.sn_label,
            self.fw_label,
            self.touch_fw_label,
            self.hw_label,
            self.hw_version_label,
            self.sku_label,
            self.touch_layout_label,
            self.protocol_label,
            self.port_label,
            self.connected_slave_id_label,
            self.current_modbus_label,
            self.current_can_arb_label,
            self.current_can_data_label,
            self.sys_state_label,
            self.sys_error_label,
            self.sys_current_label,
            self.sys_voltage_label,
            self.sys_power_label,
            self.sys_temp_label,
            self.motor_online_summary,
            self.motor_temp_summary,
            self.motor_fault_summary,
        ]:
            label.setText("--")
        for labels in [
            self.motor_sn_labels,
            self.motor_fw_labels,
            self.motor_temp_labels,
            self.motor_faults_labels,
        ]:
            for label in labels:
                label.setText("--")

    def update_texts(self):
        self.info_group.setTitle(tr("device_info"))
        self.sn_title.setText(tr("serial_number") + ":")
        self.fw_title.setText(tr("firmware_version") + ":")
        self.touch_fw_title.setText("Touch Firmware:")
        self.hw_title.setText(tr("model") + ":")
        self.touch_layout_title.setText("Touch Layout:")
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
        self.auto_clear_faults_check.setText(tr("v3_auto_clear_motor_faults"))
        self.runtime_group.setTitle(tr("runtime_flags"))
        self.protection_group.setTitle(tr("protection"))
        self.apply_global_current_btn.setText(tr("apply"))
        self.refresh_runtime_btn.setText(tr("refresh_settings"))
        self.refresh_comm_btn.setText(tr("refresh_settings"))
        self.refresh_revo3_btn.setText(tr("refresh_status_info"))
        self.log_group.setTitle(tr("operation_log"))
        self.revo3_sys_group.setTitle(tr("revo3_status"))
        self.motor_summary_group.setTitle(tr("motor_health_summary"))
        self.motor_details_check.setText(tr("show_motor_details"))
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
        self.tabs.setTabText(0, "📋 " + tr("system_overview"))
        self.tabs.setTabText(1, "⚙ " + tr("revo3_runtime"))
        self.tabs.setTabText(2, "📡 " + tr("communication"))

    def _load_runtime_settings(self):
        if not self.device:
            return
        self._loading_settings = True
        try:
            config = run_async(lambda: self.device.get_config_snapshot())
            if config:
                self.auto_calib_check.setChecked(
                    bool(config.power_on_auto_calibration_enabled)
                )
                self.touch_screen_check.setChecked(bool(getattr(config, 'touch_screen_enabled', getattr(config, 'touch_screen', False))))
                self.teaching_mode_check.setChecked(bool(getattr(config, 'teaching_mode_enabled', getattr(config, 'teaching_mode', False))))
                self.software_estop_check.setChecked(bool(getattr(config, 'software_stop_enabled', getattr(config, 'software_estop', False))))
                self.broadcast_id_check.setChecked(bool(getattr(config, 'use_broadcast_id', False)))
                self.auto_clear_faults_check.setChecked(
                    bool(getattr(config, "auto_clear_motor_faults_enabled", False))
                )
                current = getattr(config, 'global_protect_current_ma', None)
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
        self.current_modbus_label.setText("--")
        self.current_can_arb_label.setText("--")
        self.current_can_data_label.setText("--")

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

        self.modbus_group.setVisible(is_modbus)
        self.canfd_group.setVisible(is_canfd)
        try:
            if "Modbus" in protocol or "Mock" in protocol:
                if hasattr(self.device, "get_rs485_baudrate"):
                    baud = await self.device.get_rs485_baudrate()
                    self.current_modbus_label.setText(self._format_baudrate(baud))

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
                # Revo3 CANFD transports use a fixed 1 Mbps arbitration rate.
                self.current_can_arb_label.setText(self._format_baudrate(1_000_000))
                if hasattr(self.device, "get_canfd_baudrate"):
                    baud = await self.device.get_canfd_baudrate()
                    self.current_can_data_label.setText(self._format_baudrate(baud))

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
        self.fw_label.setText("--")
        self.touch_fw_label.setText("--")
        for label in self.motor_fw_labels:
            label.setText("--")
        try:
            if hasattr(device, "refresh_firmware_versions"):
                firmware = await device.refresh_firmware_versions(self.slave_id)
                controller_version = getattr(
                    firmware, "controller_firmware_version", None
                )
                if controller_version:
                    self.fw_label.setText(str(controller_version))
                motor_versions = list(
                    getattr(firmware, "motor_firmware_versions", []) or []
                )
                touch_versions = list(
                    getattr(firmware, "touch_firmware_versions", []) or []
                )
            else:
                motor_versions = list(
                    await device.get_motor_fw_versions(self.slave_id)
                )
                touch_versions = []
            self._touch_firmware_versions = touch_versions
            for i, value in enumerate(motor_versions[:21]):
                self.motor_fw_labels[i].setText(str(value))
            SystemConfigPanel._update_touch_firmware_display(self)
        except Exception as e:
            self._touch_firmware_versions = []
            SystemConfigPanel._update_touch_firmware_display(self)
            self._log(f"refresh_firmware_versions failed: {e}")

        system_labels = [
            self.sys_state_label,
            self.sys_error_label,
            self.sys_current_label,
            self.sys_voltage_label,
            self.sys_power_label,
            self.sys_temp_label,
        ]
        for label in system_labels:
            label.setText("--")
        try:
            status = await device.get_system_status(self.slave_id)
            self.sys_state_label.setText(str(getattr(status, "system_state", "--")))
            self.sys_error_label.setText(str(getattr(status, "error_code", "--")))
            self.sys_current_label.setText(str(getattr(status, "current_ma", "--")))
            self.sys_voltage_label.setText(str(getattr(status, "voltage_v", "--")))
            self.sys_power_label.setText(str(getattr(status, "power_w", "--")))
            self.sys_temp_label.setText(str(getattr(status, "temperature_c", "--")))
        except Exception as e:
            self._log(f"Failed to load system status: {e}")

        loaded_values = {}
        for method_name, labels in [
            ("get_all_motor_sns", self.motor_sn_labels),
            ("get_all_motor_module_temperatures", self.motor_temp_labels),
            ("get_all_joint_fault_codes", self.motor_faults_labels),
        ]:
            for label in labels:
                label.setText("--")
            try:
                values = list(await getattr(device, method_name)(self.slave_id))[:21]
                loaded_values[method_name] = values
                for i, value in enumerate(values):
                    labels[i].setText(str(value))
            except Exception as e:
                self._log(f"{method_name} failed: {e}")
        if hasattr(self, "motor_online_summary"):
            serial_numbers = loaded_values.get("get_all_motor_sns", [])
            temperatures = loaded_values.get("get_all_motor_module_temperatures", [])
            fault_codes = loaded_values.get("get_all_joint_fault_codes", [])
            online_count = sum(
                value is not None and bool(str(value).strip(" -"))
                for value in serial_numbers
            )
            numeric_temperatures = []
            for value in temperatures:
                try:
                    numeric_temperatures.append(float(value))
                except (TypeError, ValueError):
                    continue
            fault_count = 0
            for value in fault_codes:
                try:
                    fault_count += int(value) != 0
                except (TypeError, ValueError):
                    fault_count += bool(value)
            self.motor_online_summary.setText(
                tr("motor_online_summary").format(count=online_count)
                if "get_all_motor_sns" in loaded_values
                else tr("motor_online_summary_unavailable")
            )
            max_temp = max(numeric_temperatures, default=None)
            self.motor_temp_summary.setText(
                tr("motor_max_temp_summary").format(
                    value=f"{max_temp:g}" if max_temp is not None else "--"
                )
            )
            self.motor_fault_summary.setText(
                tr("motor_fault_summary").format(count=fault_count)
                if "get_all_joint_fault_codes" in loaded_values
                else tr("motor_fault_summary_unavailable")
            )
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
            if hasattr(self.device, "reboot"):
                run_async(lambda: self.device.reboot(), raise_exception=True)
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
            try:
                run_async(lambda: self.device.factory_reset(), raise_exception=True)
                self._log(tr("log_factory_reset_done"))
            except Exception as e:
                self._log(tr("log_factory_reset_failed").format(error=e))
                QMessageBox.critical(
                    self,
                    tr("btn_factory_reset"),
                    tr("log_factory_reset_failed").format(error=e),
                )

    def _manual_calibrate(self):
        if not self.device:
            return
        if hasattr(self.device, "manual_calibration"):
            run_async(lambda: self.device.manual_calibration())
        self._log("Manual calibration requested")

    def _on_buzzer_changed(self, state):
        self._set_flag("set_buzzer", state == Qt.Checked.value, "Buzzer")

    def _on_vibration_changed(self, state):
        self._set_flag("set_vibration", state == Qt.Checked.value, "Vibration")

    def _on_touch_screen_changed(self, state):
        self._set_flag("set_touch_screen", state == Qt.Checked.value, "Touch screen")

    def _on_auto_calib_changed(self, state):
        self._set_flag(
            "set_power_on_auto_calibration",
            state == Qt.Checked.value,
            "Power-on auto calibration",
        )

    def _on_teaching_mode_changed(self, state):
        self._set_flag("set_teaching_mode", state == Qt.Checked.value, "Teaching mode")

    def _on_software_estop_changed(self, state):
        self._set_flag("set_software_e_stop", state == Qt.Checked.value, "Software E-Stop")

    def _on_broadcast_id_changed(self, state):
        self._set_flag("set_use_broadcast_id", state == Qt.Checked.value, "Use broadcast ID")

    def _on_auto_clear_faults_changed(self, state):
        self._set_flag(
            "set_auto_clear_motor_faults",
            state == Qt.Checked.value,
            "Auto clear motor faults",
        )

    def _set_flag(self, clean_method_name: str, enabled: bool, label: str):
        if self._loading_settings or not self.device:
            return
        func = getattr(self.device, clean_method_name, None)
        if not callable(func):
            return
        try:
            run_async(lambda: func(self.slave_id, enabled))
            self._log(f"{label}: {enabled}")
        except Exception as e:
            self._log(f"Failed to set {label}: {e}")

    def _apply_global_current(self):
        if not self.device:
            return
        value = self.global_current_spin.value()
        try:
            run_async(lambda: self.device.set_global_protect_current(value))
            self._log(f"Global protect current set to {value} mA")
        except Exception as e:
            self._log(f"Failed to set global protect current: {e}")
        except Exception as e:
            self._log(f"Failed to set global protect current: {e}")

    def _set_modbus_baudrate(self):
        if not self.device or not hasattr(self.device, "set_rs485_baudrate"):
            return
        idx = self.modbus_baud_combo.currentIndex()
        # Options: ["1 Mbps", "2 Mbps", "3 Mbps", "5 Mbps"]
        baud_map = {
            0: sdk.Rs485Baudrate.Baud1Mbps,
            1: sdk.Rs485Baudrate.Baud2Mbps,
            2: sdk.Rs485Baudrate.Baud3Mbps,
            3: sdk.Rs485Baudrate.Baud5Mbps,
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

        current_baud_str = self._enum_name(current_baud) if current_baud is not None else "unknown"
        logger.info(f"User confirmed to change RS485 baudrate: {current_baud_str} -> {self._enum_name(baud_enum)}")
        if self.shared_data:
            self.shared_data.stop()

        try:
            run_async(lambda: self.device.set_rs485_baudrate(self.slave_id, baud_enum), raise_exception=True)
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
        if not self.device or not hasattr(self.device, "get_rs485_baudrate"):
            return None
        try:
            return run_async(lambda: self.device.get_rs485_baudrate(), raise_exception=True)
        except Exception as e:
            self._log(f"Could not read current RS485 baudrate before setting: {e}")
            return None

    def _read_current_canfd_baudrate(self):
        if not self.device or not hasattr(self.device, "get_canfd_baudrate"):
            return None
        try:
            return run_async(lambda: self.device.get_canfd_baudrate(), raise_exception=True)
        except Exception as e:
            self._log(f"Could not read current CANFD baudrate before setting: {e}")
            return None

    def _set_canfd_baudrate(self):
        if not self.device or not hasattr(self.device, "set_canfd_baudrate"):
            return
        idx = self.canfd_baud_combo.currentIndex()
        # Options: ["1 Mbps", "2 Mbps", "4 Mbps", "5 Mbps"]
        baud_map = {
            0: sdk.CanFdBaudrate.Baud1Mbps,
            1: sdk.CanFdBaudrate.Baud2Mbps,
            2: sdk.CanFdBaudrate.Baud4Mbps,
            3: sdk.CanFdBaudrate.Baud5Mbps,
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

        current_baud = self._read_current_canfd_baudrate()
        current_baud_str = self._enum_name(current_baud) if current_baud is not None else "unknown"
        logger.info(f"User confirmed to change CANFD baudrate: {current_baud_str} -> {self._enum_name(baud_enum)}")
        if self.shared_data:
            self.shared_data.stop()

        try:
            run_async(lambda: self.device.set_canfd_baudrate(self.slave_id, baud_enum), raise_exception=True)
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
        try:
            res = run_async(lambda: getattr(self.device, method_name)(self.slave_id))
            return bool(res) if res is not None else default
        except Exception as e:
            logger.error(f"Failed to query {method_name}: {e}")
            return default

    def _enum_name(self, value):
        if hasattr(value, "name"):
            return value.name
        text = str(value)
        return text.split(".")[-1]

    def _format_baudrate(self, value):
        """Format SDK baudrate enums and integer bps values for display."""
        name = self._enum_name(value)
        if name.startswith("Baud") and name.endswith("Mbps"):
            return f"{name[4:-4]} Mbps"

        try:
            bps = int(value)
        except (TypeError, ValueError):
            return name

        if bps >= 1_000_000 and bps % 1_000_000 == 0:
            return f"{bps // 1_000_000} Mbps"
        if bps >= 1_000 and bps % 1_000 == 0:
            return f"{bps // 1_000} kbps"
        return f"{bps} bps"

    @staticmethod
    def _device_touch_layout(device):
        return getattr(
            getattr(getattr(device, "hand", None), "touch", None),
            "layout",
            None,
        )

    def update_touch_layout(self, layout):
        self._touch_layout = layout
        self.touch_layout_label.setText(self._format_touch_layout(layout))
        self._update_touch_firmware_display()

    def _update_touch_firmware_display(self):
        versions = list(getattr(self, "_touch_firmware_versions", []) or [])
        self.touch_fw_label.setText(
            SystemConfigPanel._format_touch_firmware(
                versions, getattr(self, "_touch_layout", None)
            )
        )

    @staticmethod
    def _format_touch_firmware(versions, layout):
        if versions:
            return ", ".join(str(value) for value in versions)
        modules = list(getattr(layout, "modules", []) or [])
        families = []
        for module in modules:
            layout_id = str(getattr(module, "layout_id", "") or "")
            family = layout_id.split("_", 1)[0] if "_" in layout_id else ""
            if family and family not in families:
                families.append(family)
        if not families:
            return "--"
        return tr("touch_firmware_unavailable").format(
            families=" + ".join(f"{family}_*" for family in families)
        )

    @staticmethod
    def _format_touch_layout(layout):
        modules = list(getattr(layout, "modules", []) or [])
        if not modules:
            return "--"
        layout_counts = {}
        for module in modules:
            layout_id = str(getattr(module, "layout_id", "") or "").strip()
            if layout_id:
                layout_counts[layout_id] = layout_counts.get(layout_id, 0) + 1
        if not layout_counts:
            return "--"
        return ", ".join(
            f"{layout_id} x{count}" for layout_id, count in layout_counts.items()
        )

    def _touch_layout_name(self, device):
        layout = SystemConfigPanel._device_touch_layout(device)
        return SystemConfigPanel._format_touch_layout(layout)

    def _log(self, message):
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.append(f"[{timestamp}] {message}")
