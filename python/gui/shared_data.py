"""Shared Revo3 data manager for GUI panels."""

import sys
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, Signal

sys.path.insert(0, str(Path(__file__).parent.parent))
from common_imports import sdk

from .constants import MOTOR_BUFFER_SIZE, TOUCH_BUFFER_SIZE
from .mock_device import MockRevo3MotorStatusData, MockRevo3TouchData


class MockBuffer:
    def __init__(self, size: int):
        self.size = size
        self._items = []

    def push(self, item):
        self._items.append(item)
        if len(self._items) > self.size:
            del self._items[:len(self._items) - self.size]

    def peek_latest(self):
        return self._items[-1] if self._items else None

    def pop_all(self):
        items = list(self._items)
        self._items.clear()
        return items

    def len(self):
        return len(self._items)


class SharedDataManager(QObject):
    revo3_motor_updated = Signal(object)
    touch_updated = Signal(object)
    connection_lost = Signal()
    slave_id_updated = Signal(int)

    def __init__(self):
        super().__init__()
        self._device = None
        self._slave_id = 1
        self._device_info = None
        self.revo3_motor_buffer = None
        self.revo3_touch_buffer = None
        self.data_collector = None
        self.is_running = False
        self._mock_tick = 0
        self._update_timer = QTimer()
        self._update_timer.timeout.connect(self._emit_updates)
        self._update_timer.setInterval(50)

    @property
    def device(self):
        return self._device

    @property
    def slave_id(self):
        return self._slave_id

    @property
    def device_info(self):
        return self._device_info

    @property
    def hw_type(self):
        return getattr(self._device_info, "hardware_type", None) if self._device_info else None

    def set_device(self, device, slave_id: int, device_info):
        if self.is_running:
            self.stop()
        self._device = device
        self._slave_id = slave_id
        self._device_info = device_info
        if getattr(device, "is_mock", False):
            self.revo3_motor_buffer = MockBuffer(MOTOR_BUFFER_SIZE)
            self.revo3_touch_buffer = MockBuffer(TOUCH_BUFFER_SIZE)
        elif sdk and device:
            self.revo3_motor_buffer = sdk.Revo3MotorStatusBuffer(MOTOR_BUFFER_SIZE)
            self.revo3_touch_buffer = sdk.Revo3TouchDataBuffer(TOUCH_BUFFER_SIZE)

    def clear_device(self):
        self.stop()
        self._device = None
        self._slave_id = 1
        self._device_info = None
        self.revo3_motor_buffer = None
        self.revo3_touch_buffer = None

    def update_slave_id(self, new_id: int):
        if new_id == self._slave_id:
            return
        was_running = self.is_running
        if was_running:
            self.stop()
        self._slave_id = new_id
        self.slave_id_updated.emit(new_id)
        if was_running:
            self.start()

    def start(self, motor_freq=200, touch_freq=0):
        if not self._device:
            return False
        if self.is_running:
            return True
        if getattr(self._device, "is_mock", False):
            self.is_running = True
            self._update_timer.start()
            return True
        if not sdk:
            return False
        try:
            from common_imports import has_touch
            is_touch_device = has_touch(self.hw_type)

            if is_touch_device or touch_freq > 0:
                self.data_collector = sdk.DataCollector.new_revo3_full(
                    self._device,
                    self.revo3_motor_buffer,
                    self.revo3_touch_buffer,
                    self._slave_id,
                    motor_freq,
                    touch_freq,
                    True,
                )
            else:
                self.data_collector = sdk.DataCollector.new_revo3_basic(
                    self._device,
                    self.revo3_motor_buffer,
                    self._slave_id,
                    motor_freq,
                    True,
                )
            ok = self.data_collector.start()
            if ok:
                self.is_running = True
                self._update_timer.start()
            return ok
        except Exception as e:
            print(f"[SharedDataManager] Failed to start DataCollector: {e}")
            return False

    def stop(self):
        self._update_timer.stop()
        if self.data_collector:
            try:
                self.data_collector.stop()
                # Do not call wait() here as it blocks the GUI thread and can deadlock
            except Exception as e:
                print(f"[SharedDataManager] Stop error: {e}")
        self.data_collector = None
        self.is_running = False

    def get_latest_revo3_motor(self):
        if self.revo3_motor_buffer:
            return self.revo3_motor_buffer.peek_latest()
        return None

    def get_latest_revo3_touch(self):
        if self.revo3_touch_buffer:
            return self.revo3_touch_buffer.peek_latest()
        return None

    def _emit_updates(self):
        if getattr(self._device, "is_mock", False):
            self._mock_tick += 1
            motor = self._device._status()
            self.revo3_motor_buffer.push(motor)
            self.revo3_motor_updated.emit(motor)
            if self.revo3_touch_buffer:
                touch = MockRevo3TouchData(self._mock_tick * 0.05)
                self.revo3_touch_buffer.push(touch)
                self.touch_updated.emit(touch)
            return
        motor = self.get_latest_revo3_motor()
        if motor:
            self.revo3_motor_updated.emit(motor)
        touch = self.get_latest_revo3_touch()
        if touch:
            self.touch_updated.emit(touch)
