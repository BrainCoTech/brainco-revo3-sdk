"""Modern Revo3-only connection panel with the legacy GUI layout."""

import asyncio
import sys
from pathlib import Path

from PySide6.QtCore import QObject, QThread, QTimer, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .i18n import tr
from .styles import COLORS, CONNECTION_STATUS_STYLES

sys.path.insert(0, str(Path(__file__).parent.parent))
from common_imports import get_protocol_display_name, int_to_baudrate, modbus_open, sdk, baudrate_to_int

PROTO_AUTO = "auto"
PROTO_MODBUS = "modbus"
PROTO_CANFD = "canfd"
PROTO_ETHERCAT = "ethercat"
PROTO_MOCK = "mock"

PROTOCOL_LABELS = {
    PROTO_AUTO: "Auto Detect",
    PROTO_MODBUS: "Modbus/RS485",
    PROTO_CANFD: "CANFD",
    PROTO_ETHERCAT: "EtherCAT",
}


def protocol_key_to_label(protocol_key) -> str:
    return PROTOCOL_LABELS.get(protocol_key or "", protocol_key or "")


def sdk_protocol_to_key(protocol_type):
    if sdk is None:
        return None
    if protocol_type == sdk.StarkProtocolType.Modbus:
        return PROTO_MODBUS
    if protocol_type == sdk.StarkProtocolType.CanFd:
        return PROTO_CANFD
    if protocol_type == sdk.StarkProtocolType.EtherCAT:
        return PROTO_ETHERCAT
    return None


def run_in_new_loop(async_factory):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        async def _runner():
            return await async_factory()

        return loop.run_until_complete(_runner())
    finally:
        loop.close()
        asyncio.set_event_loop(None)


try:
    import serial.tools.list_ports

    HAS_SERIAL = True
except ImportError:
    HAS_SERIAL = False


def list_serial_ports():
    if not HAS_SERIAL:
        return []
    ports = []
    for port in serial.tools.list_ports.comports():
        desc = f"{port.device}"
        if port.description and port.description != port.device:
            desc += f" - {port.description}"
        ports.append((port.device, desc))
    return ports


class AutoDetectWorker(QObject):
    finished = Signal(object)
    error = Signal(str)
    progress = Signal(str)

    def __init__(self, protocol=None, port=None, scan_all=False, slave_id=None, modbus_baudrate=None):
        super().__init__()
        self.protocol = protocol
        self.port = port
        self.scan_all = scan_all
        self.slave_id = slave_id
        self.modbus_baudrate = modbus_baudrate

    def run(self):
        loop = None
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(self._auto_detect())
            self.finished.emit(result)
        except Exception as e:
            import traceback

            traceback.print_exc()
            self.error.emit(str(e))
        finally:
            if loop is not None:
                loop.close()

    async def _auto_detect(self):
        self.progress.emit("Scanning Revo3 devices...")
        devices = []
        for attempt in range(3):
            devices = await sdk.revo3_auto_detect(
                scan_all=self.scan_all,
                port=self.port,
                protocol=self.protocol,
                slave_id=self.slave_id,
                modbus_baudrate=self.modbus_baudrate,
            )
            if devices:
                break
            if attempt < 2:
                import asyncio
                await asyncio.sleep(1.5)

        if not devices:
            raise RuntimeError("No Revo3 device found")

        return devices[0]


class ManualConnectWorker(QObject):
    finished = Signal(object, int, object, str, str)
    error = Signal(str)

    def __init__(self, protocol_key, params):
        super().__init__()
        self.protocol_key = protocol_key
        self.params = params

    def run(self):
        loop = None
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            ctx, slave_id, device_info = loop.run_until_complete(self._connect())
            self.finished.emit(
                ctx,
                slave_id,
                device_info,
                self.protocol_key,
                protocol_key_to_label(self.protocol_key),
            )
        except Exception as e:
            import traceback

            traceback.print_exc()
            self.error.emit(str(e))
        finally:
            if loop is not None:
                loop.close()

    async def _connect(self):
        if self.protocol_key == PROTO_MODBUS:
            ctx = await modbus_open(self.params["port"], int(self.params["baudrate"]))
            slave_id = self.params["slave_id"]
            await ctx.set_hardware_type(slave_id, sdk.StarkHardwareType.Revo3Ultra)
            device_info = await ctx.revo3_get_device_info(slave_id)
            return ctx, slave_id, device_info

        if self.protocol_key == PROTO_CANFD:
            port_name = self.params["port_name"]
            await sdk.init_zqwl_canfd(
                port_name,
                self.params["arb_baudrate"],
                self.params["data_baudrate"],
            )
            slave_id = self.params["slave_id"]
            ctx = sdk.init_device_handler(
                sdk.StarkProtocolType.CanFd,
                0,
                slave_id,
                sdk.StarkHardwareType.Revo3Ultra,
            )
            device_info = await ctx.revo3_get_device_info(slave_id)
            return ctx, slave_id, device_info

        if self.protocol_key == PROTO_ETHERCAT:
            slave_id = self.params["slave_pos"]
            ctx = sdk.init_device_handler(
                sdk.StarkProtocolType.EtherCAT,
                self.params["master_pos"],
                slave_id,
                sdk.StarkHardwareType.Revo3Ultra,
            )
            device_info = await ctx.revo3_get_device_info(slave_id)
            return ctx, slave_id, device_info

        raise RuntimeError(f"Unsupported protocol: {self.protocol_key}")


class ConnectionPanel(QWidget):
    connected = Signal(object, int, object, str, str)
    disconnected = Signal()
    about_to_disconnect = Signal()

    def __init__(self, revo3_modbus=False, mock_type=None):
        super().__init__()
        self.ctx = None
        self.slave_id = None
        self.protocol = None
        self.protocol_key = None
        self.last_protocol_key = None
        self.last_slave_id = None
        self.last_reconnect_port = None
        self.last_reconnect_protocol = None
        self.last_modbus_baudrate = None
        self.revo3_modbus = revo3_modbus
        self.mock_type = mock_type
        self._thread = None
        self.worker = None
        self._setup_ui()
        if self.mock_type:
            QTimer.singleShot(0, self._connect_mock)
        else:
            QTimer.singleShot(100, self._on_auto_detect)

    def _setup_ui(self):
        self.setFrameStyle = getattr(self, "setFrameStyle", lambda *_: None)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(10)

        self.proto_label = QLabel(tr("protocol") + ":")
        layout.addWidget(self.proto_label)

        self.protocol_combo = QComboBox()
        for key in [PROTO_AUTO, PROTO_MODBUS, PROTO_CANFD, PROTO_ETHERCAT]:
            self.protocol_combo.addItem(PROTOCOL_LABELS[key], key)
        self.protocol_combo.currentTextChanged.connect(self._on_protocol_changed)
        layout.addWidget(self.protocol_combo)

        self.modbus_frame = QWidget()
        modbus_layout = QHBoxLayout(self.modbus_frame)
        modbus_layout.setContentsMargins(0, 0, 0, 0)
        self.modbus_port_label = QLabel(tr("port") + ":")
        modbus_layout.addWidget(self.modbus_port_label)
        self.port_combo = QComboBox()
        self.port_combo.setEditable(True)
        self.port_combo.setMinimumWidth(220)
        modbus_layout.addWidget(self.port_combo)
        self.refresh_port_btn = QToolButton()
        self.refresh_port_btn.setText("Refresh")
        self.refresh_port_btn.clicked.connect(self._refresh_port_list)
        modbus_layout.addWidget(self.refresh_port_btn)
        self.modbus_baud_label = QLabel(tr("baud") + ":")
        modbus_layout.addWidget(self.modbus_baud_label)
        self.baudrate_combo = QComboBox()
        for baud in ["5000000", "3000000", "2000000", "1000000"]:
            self.baudrate_combo.addItem(baud)
        modbus_layout.addWidget(self.baudrate_combo)
        self.modbus_id_label = QLabel(tr("id") + ":")
        modbus_layout.addWidget(self.modbus_id_label)
        self.slave_id_spin = QSpinBox()
        self.slave_id_spin.setRange(1, 255)
        self.slave_id_spin.setValue(1)
        modbus_layout.addWidget(self.slave_id_spin)
        self.modbus_frame.setVisible(False)
        layout.addWidget(self.modbus_frame)

        self.canfd_frame = QWidget()
        canfd_layout = QHBoxLayout(self.canfd_frame)
        canfd_layout.setContentsMargins(0, 0, 0, 0)
        self.canfd_adapter_label = QLabel(tr("adapter") + ":")
        canfd_layout.addWidget(self.canfd_adapter_label)
        self.canfd_port_combo = QComboBox()
        self.canfd_port_combo.setMinimumWidth(170)
        canfd_layout.addWidget(self.canfd_port_combo)
        self.canfd_id_label = QLabel(tr("id") + ":")
        canfd_layout.addWidget(self.canfd_id_label)
        self.canfd_slave_spin = QSpinBox()
        self.canfd_slave_spin.setRange(1, 255)
        self.canfd_slave_spin.setValue(1)
        canfd_layout.addWidget(self.canfd_slave_spin)
        self.canfd_frame.setVisible(False)
        layout.addWidget(self.canfd_frame)

        self.ethercat_frame = QWidget()
        ec_layout = QHBoxLayout(self.ethercat_frame)
        ec_layout.setContentsMargins(0, 0, 0, 0)
        self.ec_master_label = QLabel("Master:")
        ec_layout.addWidget(self.ec_master_label)
        self.ec_master_spin = QSpinBox()
        self.ec_master_spin.setRange(0, 15)
        ec_layout.addWidget(self.ec_master_spin)
        self.ec_slave_label = QLabel("Slave:")
        ec_layout.addWidget(self.ec_slave_label)
        self.ec_slave_spin = QSpinBox()
        self.ec_slave_spin.setRange(0, 255)
        ec_layout.addWidget(self.ec_slave_spin)
        self.ethercat_frame.setVisible(False)
        layout.addWidget(self.ethercat_frame)

        self.auto_detect_btn = QPushButton(tr("btn_auto_detect"))
        self.auto_detect_btn.clicked.connect(self._on_auto_detect)
        layout.addWidget(self.auto_detect_btn)

        self.connect_btn = QPushButton(tr("btn_connect"))
        self.connect_btn.clicked.connect(self._on_connect)
        self.connect_btn.setVisible(False)
        layout.addWidget(self.connect_btn)

        self.disconnect_btn = QPushButton(tr("btn_disconnect"))
        self.disconnect_btn.clicked.connect(self._on_disconnect)
        self.disconnect_btn.setEnabled(False)
        layout.addWidget(self.disconnect_btn)

        self.status_indicator = QLabel("● " + tr("status_disconnected"))
        self.status_indicator.setStyleSheet(CONNECTION_STATUS_STYLES["disconnected"])
        layout.addWidget(self.status_indicator)

        self.info_labels = {
            "hardware": QLabel("—"),
            "serial": QLabel(""),
            "protocol": QLabel(""),
            "port": QLabel(""),
            "slave_id": QLabel(""),
            "firmware": QLabel(""),
        }
        self.info_labels["hardware"].setStyleSheet(f"color: {COLORS['text_primary']};")
        layout.addWidget(self.info_labels["hardware"], 1)

        self.status_label = QLabel("")
        self.status_label.setVisible(False)
        layout.addWidget(self.status_label)
        self._refresh_port_list()
        self._refresh_zqwl_devices()

    def _refresh_zqwl_devices(self):
        if sdk is None or not hasattr(sdk, "list_zqwl_devices"):
            return
        try:
            self.canfd_port_combo.clear()
            for d in sdk.list_zqwl_devices():
                if getattr(d, "supports_canfd", True):
                    self.canfd_port_combo.addItem(d.port_name, d.port_name)
        except Exception as e:
            print(f"Error refreshing ZQWL devices: {e}")

    def update_texts(self):
        self.proto_label.setText(tr("protocol") + ":")
        self.modbus_port_label.setText(tr("port") + ":")
        self.modbus_baud_label.setText(tr("baud") + ":")
        self.modbus_id_label.setText(tr("id") + ":")
        self.canfd_adapter_label.setText(tr("adapter") + ":")
        self.canfd_id_label.setText(tr("id") + ":")
        self.auto_detect_btn.setText(tr("btn_auto_detect"))
        self.connect_btn.setText(tr("btn_connect"))
        self.disconnect_btn.setText(tr("btn_disconnect"))

    def _on_protocol_changed(self, _label):
        protocol_key = self.protocol_combo.currentData()
        self.modbus_frame.setVisible(protocol_key == PROTO_MODBUS)
        self.canfd_frame.setVisible(protocol_key == PROTO_CANFD)
        self.ethercat_frame.setVisible(protocol_key == PROTO_ETHERCAT)
        self.connect_btn.setVisible(protocol_key != PROTO_AUTO)
        self.auto_detect_btn.setVisible(protocol_key == PROTO_AUTO)
        if protocol_key == PROTO_MODBUS:
            self._refresh_port_list()
        elif protocol_key == PROTO_CANFD:
            self._refresh_zqwl_devices()

    def _refresh_port_list(self):
        current = self.port_combo.currentText() if hasattr(self, "port_combo") else ""
        self.port_combo.clear()
        ports = list_serial_ports()
        if ports:
            for device, desc in ports:
                self.port_combo.addItem(desc, device)
        else:
            self.port_combo.addItem("No ports found", "")
        if current:
            self.port_combo.setEditText(current)

    def _on_auto_detect(self):
        if sdk is None:
            self.status_label.setText("SDK not installed")
            return
        self._set_connecting_state()
        protocol_key = self.protocol_combo.currentData()
        protocol = None
        if protocol_key == PROTO_MODBUS:
            protocol = sdk.StarkProtocolType.Modbus
        elif protocol_key == PROTO_CANFD:
            protocol = sdk.StarkProtocolType.CanFd
        elif protocol_key == PROTO_ETHERCAT:
            protocol = sdk.StarkProtocolType.EtherCAT
        port = None
        if protocol_key == PROTO_MODBUS:
            port = self.port_combo.currentData() or self.port_combo.currentText() or None
            if port == "No ports found":
                port = None
        try:
            self._on_progress("Scanning Revo3 devices...")
            modbus_baudrate = None
            if protocol_key == PROTO_MODBUS:
                modbus_baudrate = int_to_baudrate(int(self.baudrate_combo.currentText()))
            device = run_in_new_loop(lambda: self._auto_detect_device(protocol, port, modbus_baudrate=modbus_baudrate))
            self._on_detect_success(device)
        except Exception as e:
            self._on_connect_error(str(e))

    async def _auto_detect_device(self, protocol, port, slave_id=None, modbus_baudrate=None):
        devices = []
        for attempt in range(3):
            devices = await sdk.revo3_auto_detect(
                scan_all=False,
                port=port,
                protocol=protocol,
                slave_id=slave_id,
                modbus_baudrate=modbus_baudrate,
            )
            if devices:
                break
            if attempt < 2:
                await asyncio.sleep(1.5)

        if not devices:
            raise RuntimeError("No Revo3 device found")
        return devices[0]

    def _on_detect_success(self, device):
        try:
            ctx, slave_id, device_info, protocol_key, protocol_label = run_in_new_loop(
                lambda: self._init_detected_device(device)
            )
            self._on_connect_success(
                ctx,
                slave_id,
                device_info,
                protocol_key,
                protocol_label,
                detected_device=device,
            )
        except Exception as e:
            self._on_connect_error(str(e))

    async def _init_detected_device(self, device):
        ctx = await sdk.init_from_detected(device)
        try:
            device_info = await ctx.revo3_get_device_info(device.slave_id)
        except Exception:
            device_info = sdk.DeviceInfo(
                sku_type=device.sku_type or sdk.SkuType.MediumRight,
                hand_type=sdk.HandType.Right,
                hardware_type=device.hardware_type or sdk.StarkHardwareType.Revo3Ultra,
                serial_number=device.serial_number or "",
                firmware_version=device.firmware_version or "",
                hardware_version="",
            )

        protocol_key = sdk_protocol_to_key(device.protocol_type)
        protocol_label = get_protocol_display_name(device.protocol_type)
        return ctx, device.slave_id, device_info, protocol_key, protocol_label

    def _on_connect(self):
        if self.mock_type:
            self._connect_mock()
            return
        protocol_key = self.protocol_combo.currentData()
        if protocol_key == PROTO_AUTO:
            self._on_auto_detect()
            return
        if protocol_key == PROTO_MODBUS:
            params = {
                "port": self.port_combo.currentData() or self.port_combo.currentText(),
                "baudrate": self.baudrate_combo.currentText(),
                "slave_id": self.slave_id_spin.value(),
            }
        elif protocol_key == PROTO_CANFD:
            idx = self.canfd_port_combo.currentIndex()
            params = {
                "port_name": self.canfd_port_combo.itemData(idx) if idx >= 0 else None,
                "slave_id": self.canfd_slave_spin.value(),
                "arb_baudrate": 1000000,
                "data_baudrate": 5000000,
            }
        elif protocol_key == PROTO_ETHERCAT:
            params = {
                "master_pos": self.ec_master_spin.value(),
                "slave_pos": self.ec_slave_spin.value(),
            }
        else:
            self.status_label.setText(f"Unknown protocol: {protocol_key}")
            return
        self._set_connecting_state()
        self._start_manual_connect(protocol_key, params, "Connecting...")

    def _start_manual_connect(self, protocol_key, params, status_text):
        self.status_label.setText(status_text)
        self._thread = QThread()
        self.worker = ManualConnectWorker(protocol_key, params)
        self.worker.moveToThread(self._thread)
        self._thread.started.connect(self.worker.run)
        self.worker.finished.connect(self._on_connect_success)
        self.worker.error.connect(self._on_connect_error)
        self.worker.finished.connect(self._thread.quit)
        self.worker.error.connect(self._thread.quit)
        self._thread.start()

    def reconnect_last_device(self):
        if self.mock_type:
            self._connect_mock()
            return

        # Disconnect old context to free up serial port for auto-detect
        if self.ctx is not None:
            self._on_disconnect()

        if self.last_reconnect_protocol is not None and self.last_reconnect_port and self.last_slave_id:
            self._set_connecting_state()
            try:
                self._on_progress("Reconnecting last Revo3 device...")
                device = run_in_new_loop(
                    lambda: self._auto_detect_device(
                        self.last_reconnect_protocol,
                        self.last_reconnect_port,
                        self.last_slave_id,
                        self.last_modbus_baudrate,
                    )
                )
                self._on_detect_success(device)
                return
            except Exception as e:
                print(f"Fast reconnect failed, falling back to full scan: {e}")

        self._on_auto_detect()

    def _connect_mock(self):
        try:
            from .mock_device import MockDeviceContext

            self._set_connecting_state()
            ctx = MockDeviceContext(self.mock_type)
            device_info = run_in_new_loop(lambda: ctx.revo3_get_device_info(1))
            self._on_connect_success(ctx, 1, device_info, PROTO_MOCK, f"Mock ({self.mock_type or 'revo3-touch'})")
        except Exception as e:
            self._on_connect_error(str(e))

    def _set_connecting_state(self):
        self.auto_detect_btn.setEnabled(False)
        self.connect_btn.setEnabled(False)
        self.status_indicator.setText("● Connecting...")
        self.status_indicator.setStyleSheet(CONNECTION_STATUS_STYLES["connecting"])

    def _on_progress(self, message):
        self.status_label.setText(message)

    def _on_connect_success(
        self,
        ctx,
        slave_id,
        device_info,
        protocol_key,
        protocol_label,
        detected_device=None,
    ):
        self.ctx = ctx
        self.slave_id = slave_id
        self.protocol_key = protocol_key
        self.protocol = protocol_label
        self.last_protocol_key = protocol_key
        self.last_slave_id = slave_id
        if detected_device is not None:
            self.last_reconnect_port = detected_device.port_name
            self.last_reconnect_protocol = detected_device.protocol_type
            self.last_modbus_baudrate = (
                detected_device.baudrate
                if detected_device.protocol_type == sdk.ProtocolType.Modbus
                else None
            )
        elif protocol_key == PROTO_MODBUS:
            self.last_reconnect_port = self.port_combo.currentData() or self.port_combo.currentText()
            self.last_reconnect_protocol = sdk.ProtocolType.Modbus
            self.last_modbus_baudrate = int_to_baudrate(int(self.baudrate_combo.currentText()))
        elif protocol_key == PROTO_CANFD:
            idx = self.canfd_port_combo.currentIndex()
            self.last_reconnect_port = self.canfd_port_combo.itemData(idx) if idx >= 0 else None
            self.last_reconnect_protocol = sdk.ProtocolType.CanFd
            self.last_modbus_baudrate = None
        elif protocol_key == PROTO_ETHERCAT:
            self.last_reconnect_port = None
            self.last_reconnect_protocol = sdk.ProtocolType.EtherCAT
            self.last_modbus_baudrate = None

        # Automatically switch protocol dropdown to the actually detected protocol
        self.protocol_combo.blockSignals(True)
        idx = self.protocol_combo.findData(protocol_key)
        if idx >= 0:
            self.protocol_combo.setCurrentIndex(idx)
        self.protocol_combo.blockSignals(False)

        # Update and show config frames corresponding to the actual connected protocol
        if protocol_key == PROTO_MODBUS:
            self.modbus_frame.setVisible(True)
            self.canfd_frame.setVisible(False)
            self.ethercat_frame.setVisible(False)
            self.connect_btn.setVisible(True)
            self.auto_detect_btn.setVisible(False)
            if detected_device is not None:
                port_idx = self.port_combo.findData(detected_device.port_name)
                if port_idx >= 0:
                    self.port_combo.setCurrentIndex(port_idx)
                else:
                    self.port_combo.setEditText(detected_device.port_name)
                baud_val = baudrate_to_int(detected_device.baudrate)
                baud_idx = self.baudrate_combo.findText(str(baud_val))
                if baud_idx >= 0:
                    self.baudrate_combo.setCurrentIndex(baud_idx)
                self.slave_id_spin.setValue(detected_device.slave_id)
        elif protocol_key == PROTO_CANFD:
            self.modbus_frame.setVisible(False)
            self.canfd_frame.setVisible(True)
            self.ethercat_frame.setVisible(False)
            self.connect_btn.setVisible(True)
            self.auto_detect_btn.setVisible(False)
            if detected_device is not None:
                port_idx = self.canfd_port_combo.findData(detected_device.port_name)
                if port_idx >= 0:
                    self.canfd_port_combo.setCurrentIndex(port_idx)
                self.canfd_slave_spin.setValue(detected_device.slave_id)
        elif protocol_key == PROTO_ETHERCAT:
            self.modbus_frame.setVisible(False)
            self.canfd_frame.setVisible(False)
            self.ethercat_frame.setVisible(True)
            self.connect_btn.setVisible(True)
            self.auto_detect_btn.setVisible(False)
            if detected_device is not None:
                self.ec_slave_spin.setValue(detected_device.slave_id)

        # Lock inputs in connected state
        self.protocol_combo.setEnabled(False)
        self.port_combo.setEnabled(False)
        self.baudrate_combo.setEnabled(False)
        self.slave_id_spin.setEnabled(False)
        self.canfd_port_combo.setEnabled(False)
        self.canfd_slave_spin.setEnabled(False)
        self.ec_master_spin.setEnabled(False)
        self.ec_slave_spin.setEnabled(False)

        self.auto_detect_btn.setEnabled(False)
        self.connect_btn.setEnabled(False)
        self.disconnect_btn.setEnabled(True)
        self.status_indicator.setText("● Connected")
        self.status_indicator.setStyleSheet(CONNECTION_STATUS_STYLES["connected"])
        if device_info:
            self.info_labels["hardware"].setText(str(device_info.hardware_type))
            self.info_labels["serial"].setText(device_info.serial_number)
            self.info_labels["firmware"].setText(device_info.firmware_version)
        self.connected.emit(ctx, slave_id, device_info, protocol_key, protocol_label)

    def _on_connect_error(self, error):
        self.auto_detect_btn.setEnabled(True)
        self.connect_btn.setEnabled(True)
        self.status_indicator.setText("● Error")
        self.status_indicator.setStyleSheet(CONNECTION_STATUS_STYLES["error"])
        self.status_label.setText(error)

    def _on_disconnect(self):
        if self.ctx:
            self.about_to_disconnect.emit()
            try:
                if getattr(self.ctx, "is_mock", False):
                    run_in_new_loop(lambda: self.ctx.close())
                elif self.protocol_key == PROTO_MODBUS and hasattr(sdk, "modbus_close"):
                    run_in_new_loop(lambda: sdk.modbus_close(self.ctx))
                elif hasattr(sdk, "close_device_handler"):
                    run_in_new_loop(lambda: sdk.close_device_handler(self.ctx))
                elif hasattr(self.ctx, "close"):
                    run_in_new_loop(lambda: self.ctx.close())
            except Exception as e:
                print(f"Error closing device: {e}")
        self.ctx = None
        self.slave_id = None
        self.protocol = None
        self.protocol_key = None

        # Restore widgets state
        self.protocol_combo.setEnabled(True)
        self.port_combo.setEnabled(True)
        self.baudrate_combo.setEnabled(True)
        self.slave_id_spin.setEnabled(True)
        self.canfd_port_combo.setEnabled(True)
        self.canfd_slave_spin.setEnabled(True)
        self.ec_master_spin.setEnabled(True)
        self.ec_slave_spin.setEnabled(True)

        # Update button visibilities based on current protocol dropdown selection
        current_proto = self.protocol_combo.currentData()
        self.connect_btn.setVisible(current_proto != PROTO_AUTO)
        self.auto_detect_btn.setVisible(current_proto == PROTO_AUTO)

        self.auto_detect_btn.setEnabled(True)
        self.connect_btn.setEnabled(True)
        self.disconnect_btn.setEnabled(False)
        self.status_indicator.setText("● Disconnected")
        self.status_indicator.setStyleSheet(CONNECTION_STATUS_STYLES["disconnected"])
        self.info_labels["hardware"].setText("—")
        self.disconnected.emit()
