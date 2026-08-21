"""Shared Revo3 data manager for GUI panels."""

import asyncio
import sys
import threading
import time
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, Signal

sys.path.insert(0, str(Path(__file__).parent.parent))
from common_imports import sdk, logger

from .constants import MOTOR_BUFFER_SIZE, TOUCH_BUFFER_SIZE

DEFAULT_MOTOR_FREQ = 60
DEFAULT_TOUCH_FREQ = 20
FORCE_TORQUE_TOUCH_FREQ = 5
DRAG_MOTOR_FREQ = 0
COLLECTOR_CONFIG_WARN_AFTER_S = 0.5
COLLECTOR_CONFIG_REPEAT_WARN_AFTER_S = 2.0
COLLECTOR_LIFECYCLE_WARN_AFTER_S = 0.5
COLLECTOR_LIFECYCLE_REPEAT_WARN_AFTER_S = 2.0
from .mock_device import MockRevo3MotorStatusData, MockRevo3TouchData


def _sdk_error_text(error) -> str:
    details = [str(error)]
    for name in ("category", "code", "retryable", "low_level_cause"):
        value = getattr(error, name, None)
        if value is not None and value != "":
            details.append(f"{name}={value}")
    return "; ".join(details)


class FpsCounter:
    """Thread-safe sliding-window FPS / frequency counter."""

    def __init__(self, window_seconds: float = 1.0, min_samples: int = 2):
        self._window_seconds = max(0.1, float(window_seconds))
        self._min_samples = max(2, int(min_samples))
        self._timestamps = []
        self._lock = threading.Lock()
        self._last_fps = 0.0

    def tick(self):
        """Record one incoming frame/event timestamp."""
        now = time.monotonic()
        with self._lock:
            self._timestamps.append(now)
            cutoff = now - self._window_seconds
            # Retain only timestamps within the window
            while self._timestamps and self._timestamps[0] < cutoff:
                self._timestamps.pop(0)

    def fps(self) -> float:
        """Calculate and return current instantaneous FPS."""
        now = time.monotonic()
        with self._lock:
            cutoff = now - self._window_seconds
            while self._timestamps and self._timestamps[0] < cutoff:
                self._timestamps.pop(0)
            n = len(self._timestamps)
            if n < self._min_samples:
                self._last_fps = 0.0
                return 0.0
            duration = self._timestamps[-1] - self._timestamps[0]
            if duration <= 1e-6:
                self._last_fps = float(n) / max(self._window_seconds, 1e-3)
            else:
                self._last_fps = (n - 1) / duration
            return self._last_fps

    def reset(self):
        """Reset all recorded timestamps."""
        with self._lock:
            self._timestamps.clear()
            self._last_fps = 0.0


class MockBuffer:
    def __init__(self, size: int):
        self.size = size
        self._items = []
        self._sequence = 0
        self._lock = threading.Lock()
        self._fps_counter = FpsCounter(window_seconds=1.0)

    def push(self, item):
        with self._lock:
            self._items.append(item)
            if len(self._items) > self.size:
                del self._items[:len(self._items) - self.size]
            self._sequence += 1
            self._fps_counter.tick()

    def fps(self) -> float:
        return self._fps_counter.fps()

    def peek_latest(self):
        with self._lock:
            return self._items[-1] if self._items else None

    def peek_latest_with_sequence(self):
        with self._lock:
            latest = self._items[-1] if self._items else None
            return latest, self._sequence

    def pop_all(self):
        with self._lock:
            items = list(self._items)
            self._items.clear()
            return items

    def len(self):
        with self._lock:
            return len(self._items)

    def sequence(self):
        with self._lock:
            return self._sequence

    def clear(self):
        with self._lock:
            self._items.clear()
            self._fps_counter.reset()


class _SubscriptionCollector:
    """Run the public 2.x pull subscriptions on a dedicated event loop."""

    def __init__(self, device, motor_buffer, touch_buffer, motor_frequency, touch_frequency):
        self.device = device
        self.motor_buffer = motor_buffer
        self.touch_buffer = touch_buffer
        self.motor_frequency = motor_frequency
        self.touch_frequency = touch_frequency
        self._thread = None
        self._stop = threading.Event()

    def start(self):
        if self._thread and self._thread.is_alive():
            return True
        self._stop.clear()
        self._thread = threading.Thread(target=self._thread_main, daemon=True)
        self._thread.start()
        return True

    def stop(self):
        self._stop.set()
        thread = self._thread
        if thread and thread is not threading.current_thread():
            thread.join(timeout=2.0)
        self._thread = None
        return True

    def update_motor_frequency(self, frequency):
        self.motor_frequency = frequency
        self._restart()

    def update_touch_frequency(self, frequency):
        self.touch_frequency = frequency
        self._restart()

    def _restart(self):
        if self._thread and self._thread.is_alive():
            self.stop()
            self.start()

    def _thread_main(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self._run())
        except Exception as error:
            if not self._stop.is_set():
                logger.warning("[SharedDataManager] Subscription collector failed: %s", error)
        finally:
            loop.close()
            asyncio.set_event_loop(None)

    async def _run(self):
        motor_subscription = None
        if self.motor_frequency > 0 and self.motor_buffer is not None:
            motor_period = 1.0 / max(float(self.motor_frequency), 1.0)
            motor_subscription = self.device.hand.state.subscribe(period=motor_period)
        touch_subscription = None
        if self.touch_frequency > 0 and self.touch_buffer is not None:
            touch_period = 1.0 / max(float(self.touch_frequency), 1.0)
            touch_subscription = self.device.subscribe_touch(period=touch_period)

        async def collect_motor():
            while not self._stop.is_set() and motor_subscription is not None:
                try:
                    self.motor_buffer.push(await motor_subscription.next())
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.warning("[SharedData] collect_motor error: %s", _sdk_error_text(e))
                    await asyncio.sleep(0.01)

        async def collect_touch():
            last_error = None
            last_warning_at = 0.0
            while not self._stop.is_set() and touch_subscription is not None:
                try:
                    frame = await touch_subscription.next()
                    self.touch_buffer.push(self.device.touch_frame_payload(frame))
                    last_error = None
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    now = time.monotonic()
                    error_text = _sdk_error_text(e)
                    if error_text != last_error or now - last_warning_at >= 2.0:
                        logger.warning("[SharedData] collect_touch error: %s", error_text)
                        last_error = error_text
                        last_warning_at = now
                    await asyncio.sleep(max(touch_period, 0.1))

        tasks = []
        if motor_subscription is not None:
            tasks.append(asyncio.create_task(collect_motor()))
        if touch_subscription is not None:
            tasks.append(asyncio.create_task(collect_touch()))
        try:
            while not self._stop.is_set():
                await asyncio.sleep(0.02)
        finally:
            if motor_subscription is not None:
                motor_subscription.close()
            if touch_subscription is not None:
                touch_subscription.close()
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)


class SharedDataManager(QObject):
    revo3_motor_updated = Signal(object)
    touch_updated = Signal(object)
    connection_lost = Signal()
    slave_id_updated = Signal(int)
    fps_updated = Signal(float, float, float)
    _update_timer_start_requested = Signal()
    _update_timer_stop_requested = Signal()

    def __init__(self):
        super().__init__()
        self._device = None
        self._slave_id = 1
        self._device_info = None
        self.revo3_motor_buffer = None
        self.revo3_touch_buffer = None
        self.data_collector = None
        self.is_running = False
        self.motor_frequency = DEFAULT_MOTOR_FREQ
        self.touch_frequency = DEFAULT_TOUCH_FREQ
        self._control_priority_depth = 0
        self._saved_frequencies = None
        self._mock_tick = 0
        self._latest_revo3_motor = None
        self._latest_revo3_motor_sequence = 0
        self._latest_revo3_touch = None
        self._latest_revo3_touch_sequence = 0
        self._ui_fps_counter = FpsCounter(window_seconds=1.0)
        self._last_fps_emit_time = 0.0
        self._collector_config_lock = threading.Lock()
        self._collector_config_pending = None
        self._collector_config_worker_running = False
        self._collector_config_seq = 0
        self._collector_config_blocked_collector = None
        self._collector_lifecycle_lock = threading.Lock()
        self._collector_lifecycle_seq = 0
        self._collector_lifecycle_blocked_keys = set()
        self._update_timer = QTimer()
        self._update_timer.timeout.connect(self._emit_updates)
        self._update_timer.setInterval(50)
        self._update_timer_start_requested.connect(self._start_update_timer)
        self._update_timer_stop_requested.connect(self._stop_update_timer)

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
    def model(self):
        return getattr(self._device_info, "model", None) if self._device_info else None

    def set_device(self, device, slave_id: int, device_info):
        if self.is_running:
            self.stop()
        self._device = device
        self._slave_id = slave_id
        self._device_info = device_info
        if device:
            self.revo3_motor_buffer = MockBuffer(MOTOR_BUFFER_SIZE)
            self.revo3_touch_buffer = MockBuffer(TOUCH_BUFFER_SIZE)

    def clear_device(self):
        self.stop()
        self._device = None
        self._slave_id = 1
        self._device_info = None
        self.revo3_motor_buffer = None
        self.revo3_touch_buffer = None
        self._latest_revo3_motor = None
        self._latest_revo3_motor_sequence = 0
        self._latest_revo3_touch = None
        self._latest_revo3_touch_sequence = 0
        self._ui_fps_counter.reset()
        self._last_fps_emit_time = 0.0
        self.fps_updated.emit(0.0, 0.0, 0.0)

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

    def _start_update_timer(self):
        if not self._update_timer.isActive():
            self._update_timer.start()

    def _stop_update_timer(self):
        if self._update_timer.isActive():
            self._update_timer.stop()

    def _request_update_timer_start(self):
        self._update_timer_start_requested.emit()

    def _request_update_timer_stop(self):
        self._update_timer_stop_requested.emit()

    def _effective_touch_frequency(self, requested_frequency):
        frequency = max(0, int(requested_frequency or 0))
        layout = getattr(
            getattr(getattr(self._device, "hand", None), "touch", None),
            "layout",
            None,
        )
        modules = list(getattr(layout, "modules", []) or [])
        layout_ids = [str(getattr(module, "layout_id", "")) for module in modules]
        signal_names = {
            getattr(signal, "name", str(signal)).split(".")[-1]
            for module in modules
            for signal in list(getattr(module, "signals", []) or [])
        }
        is_force_torque_layout = any(
            layout_id.startswith("hp_") for layout_id in layout_ids
        ) or bool({"Force3D", "Torque2D", "ResultantForce"} & signal_names)
        if is_force_torque_layout:
            return min(frequency, FORCE_TORQUE_TOUCH_FREQ)
        return frequency

    def start(self, motor_freq=DEFAULT_MOTOR_FREQ, touch_freq=DEFAULT_TOUCH_FREQ):
        if not self._device:
            return False
        touch_freq = self._effective_touch_frequency(touch_freq)
        self.motor_frequency = motor_freq
        self.touch_frequency = touch_freq
        if self.is_running:
            self.update_frequencies(motor_freq, touch_freq)
            return True
        if getattr(self._device, "is_mock", False):
            self.is_running = True
            self._request_update_timer_start()
            return True
        if not sdk:
            return False
        try:
            touch_layout = getattr(
                getattr(getattr(self._device, "hand", None), "touch", None),
                "layout",
                None,
            )
            is_touch_device = (
                bool(getattr(self._device, "supports_touch", False))
                and touch_layout is not None
            )
            if not is_touch_device:
                touch_freq = 0

            self.data_collector = _SubscriptionCollector(
                self._device,
                self.revo3_motor_buffer,
                self.revo3_touch_buffer,
                motor_freq,
                touch_freq,
            )
            collector = self.data_collector
            self.is_running = True
            self._request_update_timer_start()

            def _on_start_done(ok):
                if not ok and self.data_collector is collector:
                    logger.warning("[SharedDataManager] DataCollector start returned false")
                    self.is_running = False
                    self._request_update_timer_stop()

            def _start_collector():
                if self.data_collector is not collector:
                    return False
                ok = collector.start()
                if self.data_collector is not collector:
                    try:
                        collector.stop()
                    except Exception:
                        pass
                    return False
                return ok

            self._run_collector_lifecycle_call(
                "collector.start",
                collector,
                _start_collector,
                on_done=_on_start_done,
            )
            return True
        except Exception as e:
            print(f"[SharedDataManager] Failed to start DataCollector: {e}")
            return False

    def update_frequencies(self, motor_freq=None, touch_freq=None):
        if motor_freq is not None:
            self.motor_frequency = motor_freq
        if touch_freq is not None:
            touch_freq = self._effective_touch_frequency(touch_freq)
            self.touch_frequency = touch_freq
        collector = self.data_collector
        if collector:
            self._run_collector_config_update(collector, motor_freq, touch_freq)

    def _run_collector_config_update(self, collector, motor_freq=None, touch_freq=None):
        target_motor_freq = self.motor_frequency if motor_freq is None else motor_freq
        target_touch_freq = self.touch_frequency if touch_freq is None else touch_freq
        with self._collector_config_lock:
            if self._collector_config_blocked_collector is collector:
                logger.warning(
                    "[SharedDataManager] Merging collector frequency update because a previous "
                    "update call is still blocked (motor=%s, touch=%s)",
                    target_motor_freq,
                    target_touch_freq,
                )
            self._collector_config_seq += 1
            self._collector_config_pending = (
                self._collector_config_seq,
                collector,
                target_motor_freq,
                target_touch_freq,
            )
            if self._collector_config_worker_running:
                return
            self._collector_config_worker_running = True

        def _worker():
            while True:
                with self._collector_config_lock:
                    pending = self._collector_config_pending
                    self._collector_config_pending = None
                    if pending is None:
                        self._collector_config_worker_running = False
                        return
                seq, pending_collector, pending_motor_freq, pending_touch_freq = pending
                if pending_collector is not self.data_collector:
                    continue
                completed = self._call_collector_config_update(
                    seq,
                    pending_collector,
                    pending_motor_freq,
                    pending_touch_freq,
                )
                if not completed:
                    logger.warning(
                        "[SharedDataManager] Collector frequency update #%s completed after a stuck period; "
                        "continuing with latest pending target if any",
                        seq,
                    )

        threading.Thread(target=_worker, daemon=True).start()

    def _call_collector_config_update(self, seq, collector, motor_freq=None, touch_freq=None):
        done = threading.Event()
        result = {"error": None}
        started_at = time.monotonic()

        def _call():
            try:
                if motor_freq is not None:
                    collector.update_motor_frequency(motor_freq)
                if touch_freq is not None:
                    collector.update_touch_frequency(touch_freq)
            except Exception as e:
                result["error"] = e
            finally:
                elapsed_ms = int((time.monotonic() - started_at) * 1000)
                if result["error"] is not None:
                    logger.warning(
                        "[SharedDataManager] Collector frequency update #%s failed after %sms: %s",
                        seq,
                        elapsed_ms,
                        result["error"],
                    )
                elif elapsed_ms >= int(COLLECTOR_CONFIG_WARN_AFTER_S * 1000):
                    logger.warning(
                        "[SharedDataManager] Collector frequency update #%s completed slowly in %sms",
                        seq,
                        elapsed_ms,
                    )
                done.set()

        threading.Thread(target=_call, daemon=True).start()
        if not done.wait(COLLECTOR_CONFIG_WARN_AFTER_S):
            logger.warning(
                "[SharedDataManager] Collector frequency update #%s is still running after %sms "
                "(motor=%s, touch=%s); GUI will not wait",
                seq,
                int(COLLECTOR_CONFIG_WARN_AFTER_S * 1000),
                motor_freq,
                touch_freq,
            )
            with self._collector_config_lock:
                if collector is self.data_collector:
                    self._collector_config_blocked_collector = collector

            def _monitor_stuck_call():
                while not done.wait(COLLECTOR_CONFIG_REPEAT_WARN_AFTER_S):
                    elapsed_ms = int((time.monotonic() - started_at) * 1000)
                    with self._collector_config_lock:
                        pending = self._collector_config_pending
                    pending_text = ""
                    if pending is not None:
                        _, pending_collector, pending_motor_freq, pending_touch_freq = pending
                        if pending_collector is collector:
                            pending_text = f", merged_target=({pending_motor_freq}Hz, {pending_touch_freq}Hz)"
                    logger.warning(
                        "[SharedDataManager] Collector frequency update #%s still has not returned after %sms%s",
                        seq,
                        elapsed_ms,
                        pending_text,
                    )
                with self._collector_config_lock:
                    if self._collector_config_blocked_collector is collector:
                        self._collector_config_blocked_collector = None

            threading.Thread(target=_monitor_stuck_call, daemon=True).start()
            done.wait()
            return False
        return True

    def _run_collector_lifecycle_call(self, label, collector, call_fn, on_done=None):
        if not collector:
            return
        key = (id(collector), label)
        with self._collector_lifecycle_lock:
            if key in self._collector_lifecycle_blocked_keys:
                logger.warning(
                    "[SharedDataManager] Skipping %s because a previous call is still blocked",
                    label,
                )
                return
            self._collector_lifecycle_blocked_keys.add(key)
            self._collector_lifecycle_seq += 1
            seq = self._collector_lifecycle_seq

        done = threading.Event()
        result = {"value": None, "error": None}
        started_at = time.monotonic()

        def _call():
            try:
                result["value"] = call_fn()
            except Exception as e:
                result["error"] = e
            finally:
                elapsed_ms = int((time.monotonic() - started_at) * 1000)
                if result["error"] is not None:
                    logger.warning(
                        "[SharedDataManager] %s #%s failed after %sms: %s",
                        label,
                        seq,
                        elapsed_ms,
                        result["error"],
                    )
                elif elapsed_ms >= int(COLLECTOR_LIFECYCLE_WARN_AFTER_S * 1000):
                    logger.warning(
                        "[SharedDataManager] %s #%s completed slowly in %sms",
                        label,
                        seq,
                        elapsed_ms,
                    )
                done.set()
                if on_done is not None:
                    try:
                        on_done(result["value"] if result["error"] is None else False)
                    except Exception as e:
                        logger.warning("[SharedDataManager] %s completion hook failed: %s", label, e)
                with self._collector_lifecycle_lock:
                    self._collector_lifecycle_blocked_keys.discard(key)

        threading.Thread(target=_call, daemon=True).start()

        def _monitor_call():
            if done.wait(COLLECTOR_LIFECYCLE_WARN_AFTER_S):
                return
            logger.warning(
                "[SharedDataManager] %s #%s is still running after %sms; GUI will not wait",
                label,
                seq,
                int(COLLECTOR_LIFECYCLE_WARN_AFTER_S * 1000),
            )
            while not done.wait(COLLECTOR_LIFECYCLE_REPEAT_WARN_AFTER_S):
                elapsed_ms = int((time.monotonic() - started_at) * 1000)
                logger.warning(
                    "[SharedDataManager] %s #%s still has not returned after %sms",
                    label,
                    seq,
                    elapsed_ms,
                )

        threading.Thread(target=_monitor_call, daemon=True).start()

    def pause_collector(self):
        collector = self.data_collector
        if not collector:
            return False
        self.is_running = False
        self._request_update_timer_stop()
        self._run_collector_lifecycle_call("collector.stop", collector, collector.stop)
        return True

    def resume_collector(self):
        collector = self.data_collector
        if not collector:
            return False
        self.is_running = True
        self._request_update_timer_start()

        def _on_start_done(ok):
            if not ok and self.data_collector is collector:
                logger.warning("[SharedDataManager] DataCollector resume returned false")
                self.is_running = False
                self._request_update_timer_stop()

        def _start_collector():
            if self.data_collector is not collector:
                return False
            ok = collector.start()
            if self.data_collector is not collector:
                try:
                    collector.stop()
                except Exception:
                    pass
                return False
            return ok

        self._run_collector_lifecycle_call(
            "collector.start",
            collector,
            _start_collector,
            on_done=_on_start_done,
        )
        return True

    def begin_control_priority(self, motor_freq=DRAG_MOTOR_FREQ):
        if self._control_priority_depth == 0:
            self._saved_frequencies = (self.motor_frequency, self.touch_frequency)
            self.motor_frequency = motor_freq
            self.touch_frequency = 0
            collector = self.data_collector
            if collector:
                started_at = time.monotonic()
                self.is_running = False
                self._request_update_timer_stop()
                collector.motor_frequency = motor_freq
                collector.touch_frequency = 0
                collector.stop()
                elapsed_ms = int((time.monotonic() - started_at) * 1000)
                if elapsed_ms >= int(COLLECTOR_LIFECYCLE_WARN_AFTER_S * 1000):
                    logger.warning(
                        "[SharedDataManager] collector.stop for control priority completed slowly in %sms",
                        elapsed_ms,
                    )
        self._control_priority_depth += 1

    def end_control_priority(self):
        if self._control_priority_depth <= 0:
            return
        self._control_priority_depth -= 1
        if self._control_priority_depth == 0:
            motor_freq, touch_freq = self._saved_frequencies or (DEFAULT_MOTOR_FREQ, DEFAULT_TOUCH_FREQ)
            self._saved_frequencies = None
            self.motor_frequency = motor_freq
            self.touch_frequency = touch_freq
            collector = self.data_collector
            if collector:
                collector.update_motor_frequency(motor_freq)
                collector.update_touch_frequency(touch_freq)
                self.resume_collector()

    def stop(self):
        self._request_update_timer_stop()
        collector = self.data_collector
        if collector:
            self._run_collector_lifecycle_call("collector.stop", collector, collector.stop)
        self.data_collector = None
        self.is_running = False
        self._control_priority_depth = 0
        self._saved_frequencies = None
        if self.revo3_motor_buffer:
            try:
                self.revo3_motor_buffer.clear()
            except Exception:
                pass
        if self.revo3_touch_buffer:
            try:
                self.revo3_touch_buffer.clear()
            except Exception:
                pass
        self._latest_revo3_motor = None
        self._latest_revo3_motor_sequence = 0
        self._latest_revo3_touch = None
        self._latest_revo3_touch_sequence = 0
        self._ui_fps_counter.reset()
        self._last_fps_emit_time = 0.0
        self.fps_updated.emit(0.0, 0.0, 0.0)

    def get_latest_revo3_motor(self):
        return self._latest_revo3_motor

    def get_latest_revo3_motor_sequence(self):
        return self._latest_revo3_motor_sequence

    def get_latest_revo3_touch(self):
        return self._latest_revo3_touch

    def get_latest_revo3_touch_sequence(self):
        return self._latest_revo3_touch_sequence

    def get_motor_fps(self) -> float:
        """Get live motor status sampling rate (FPS / Hz)."""
        return self.revo3_motor_buffer.fps() if self.revo3_motor_buffer else 0.0

    def get_touch_fps(self) -> float:
        """Get live touch sensor sampling rate (FPS / Hz)."""
        return self.revo3_touch_buffer.fps() if self.revo3_touch_buffer else 0.0

    def get_ui_fps(self) -> float:
        """Get live UI dispatch frame rate (FPS)."""
        return self._ui_fps_counter.fps()

    def get_fps_summary(self) -> dict:
        """Get summary dictionary of all live FPS rates."""
        return {
            "motor": self.get_motor_fps(),
            "touch": self.get_touch_fps(),
            "ui": self.get_ui_fps(),
        }

    def _emit_updates(self):
        self._ui_fps_counter.tick()
        if getattr(self._device, "is_mock", False):
            self._mock_tick += 1
            motor = self._device._status()
            self.revo3_motor_buffer.push(motor)
            motor, motor_sequence = self.revo3_motor_buffer.peek_latest_with_sequence()
            self._latest_revo3_motor = motor
            self._latest_revo3_motor_sequence = motor_sequence
            self.revo3_motor_updated.emit(motor)
            if self.revo3_touch_buffer:
                touch = MockRevo3TouchData(self._mock_tick * 0.05)
                self.revo3_touch_buffer.push(touch)
                touch, touch_sequence = self.revo3_touch_buffer.peek_latest_with_sequence()
                self._latest_revo3_touch = touch
                self._latest_revo3_touch_sequence = touch_sequence
                self.touch_updated.emit(touch)
            now = time.monotonic()
            if now - self._last_fps_emit_time >= 0.2:
                self._last_fps_emit_time = now
                self.fps_updated.emit(self.get_motor_fps(), self.get_touch_fps(), self.get_ui_fps())
            return
        motor, motor_sequence = (
            self.revo3_motor_buffer.peek_latest_with_sequence()
            if self.revo3_motor_buffer
            else (None, 0)
        )
        if motor and motor_sequence != self._latest_revo3_motor_sequence:
            self._latest_revo3_motor = motor
            self._latest_revo3_motor_sequence = motor_sequence
            self.revo3_motor_updated.emit(motor)
        touch, touch_sequence = (
            self.revo3_touch_buffer.peek_latest_with_sequence()
            if self.revo3_touch_buffer
            else (None, 0)
        )
        if touch and touch_sequence != self._latest_revo3_touch_sequence:
            self._latest_revo3_touch = touch
            self._latest_revo3_touch_sequence = touch_sequence
            self.touch_updated.emit(touch)
        now = time.monotonic()
        if now - self._last_fps_emit_time >= 0.2:
            self._last_fps_emit_time = now
            self.fps_updated.emit(self.get_motor_fps(), self.get_touch_fps(), self.get_ui_fps())
