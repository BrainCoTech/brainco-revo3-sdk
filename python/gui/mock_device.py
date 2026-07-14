"""Revo3-only mock device for GUI debugging."""

import math
import time
from dataclasses import dataclass
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))
from common_imports import has_touch, sdk


REVO3_MOTOR_COUNT = 21

# Matrix Touch force range upper limit in raw units.
# Raw unit: 0.0001 N. Convert raw -> N by dividing by 10000,
# or raw -> mN by dividing by 10.
MATRIX_FORCE_LIMITS = [
    800000,  # 0: Palm
    300000,  # 1: ThumbTip
    200000,  # 2: ThumbPad
    400000,  # 3: IndexTip
    300000,  # 4: IndexPad
    400000,  # 5: MiddleTip
    300000,  # 6: MiddlePad
    400000,  # 7: RingTip
    300000,  # 8: RingPad
    400000,  # 9: PinkyTip
    300000,  # 10: PinkyPad
]

PRESSURE_FORCE_LIMIT_MN = 20000.0


def _sdk_attr(enum_name: str, fallback):
    if sdk is None:
        return fallback
    enum = getattr(sdk, enum_name, None)
    return enum if enum is not None else fallback


TouchVendor = _sdk_attr("TouchVendor", None)
if TouchVendor is None:
    class TouchVendor:
        Unknown = 0
        Pressure = 1
        Matrix = 2


def mock_hardware_type(mock_type):
    kind = (mock_type or "revo3-touch").lower().replace("_", "-")
    if sdk is None:
        return 21
    if kind in ("revo3", "revo3-ultra", "ultra"):
        return sdk.StarkHardwareType.Revo3Ultra
    if kind in ("revo3-vision", "revo3-vision-touch", "vision", "vision-touch"):
        return sdk.StarkHardwareType.Revo3UltraVisionTouch
    if kind in ("revo3-pro", "pro"):
        return sdk.StarkHardwareType.Revo3Pro
    if kind in ("revo3-matrix-touch", "matrix-touch"):
        return sdk.StarkHardwareType.Revo3UltraTouch
    if kind in ("revo3-pro-touch", "pro-touch", "revo3-pro-matrix-touch", "pro-matrix-touch"):
        return sdk.StarkHardwareType.Revo3ProTouch
    if kind in ("revo3-basic", "basic"):
        return sdk.StarkHardwareType.Revo3Basic
    if kind in ("revo3-basic-touch", "basic-touch", "revo3-basic-matrix-touch", "basic-matrix-touch"):
        return sdk.StarkHardwareType.Revo3BasicTouch
    return sdk.StarkHardwareType.Revo3UltraTouch


@dataclass
class MockDeviceInfo:
    hardware_type: object
    sku_type: object
    hand_type: object
    serial_number: str
    firmware_version: str
    hardware_version: str

    def is_touch(self):
        return has_touch(self.hardware_type)

    def uses_revo3_motor_api(self):
        return True


class MockRevo3SystemStatus:
    def __init__(self, tick: float = 0.0):
        self.system_state = 0
        self.error_code = 0
        self.current_ma = int(1200 + 120 * math.sin(tick))
        self.voltage_v = int(24000 + 400 * math.sin(tick * 0.4))
        self.power_w = int(29 + 2 * math.sin(tick * 0.7))
        self.temperature_c = int(34 + 2 * math.sin(tick * 0.2))


class MockRevo3MotorStatusData:
    def __init__(self, positions=None, velocities=None, currents=None):
        self.statuses = [0] * REVO3_MOTOR_COUNT
        self.positions = list(positions or [0.0] * REVO3_MOTOR_COUNT)[:REVO3_MOTOR_COUNT]
        self.velocities = list(velocities or [0.0] * REVO3_MOTOR_COUNT)[:REVO3_MOTOR_COUNT]
        self.currents = list(currents or [0.0] * REVO3_MOTOR_COUNT)[:REVO3_MOTOR_COUNT]
        self.errors = [0] * REVO3_MOTOR_COUNT
        self.temperatures = [34.0] * REVO3_MOTOR_COUNT
        self.speeds = self.velocities


class MockRevo3TouchData:
    def __init__(self, tick: float = 0.0, data_type: int = 0, touch_vendor: int = 2):
        physical_sizes = [53, 56, 22, 22, 27, 22, 27, 22, 27, 22, 27] if int(touch_vendor) == TouchVendor.Matrix else [36, 31, 57, 21, 52, 21, 52, 21, 52, 21, 52]
        module_sizes = [60] * 11 if int(touch_vendor) == TouchVendor.Matrix else physical_sizes
        
        TouchDataMode = _sdk_attr("TouchDataMode", None)
        force_summary_val = int(TouchDataMode.ForceSummary) if TouchDataMode is not None else 1
        
        if int(data_type) == force_summary_val:
            self.summary = [
                int(PRESSURE_FORCE_LIMIT_MN * (0.08 + 0.72 * abs(math.sin(tick + i * 0.31))))
                for i in range(42)
            ]
            self.modules = [[0] * size for size in module_sizes]
        else:
            self.summary = [int(120 + 80 * abs(math.sin(tick + i * 0.31))) for i in range(42)]
            self.modules = []
            for module_index, size in enumerate(module_sizes):
                # Calculate limit dynamically based on vendor and data type to perfectly fit ranges
                if int(touch_vendor) == TouchVendor.Matrix:
                    p_size = physical_sizes[module_index]
                    limit_raw = (MATRIX_FORCE_LIMITS[module_index] / p_size) if module_index < len(MATRIX_FORCE_LIMITS) else 3000.0
                else:
                    limit_raw = 255.0 if int(data_type) == 0 else PRESSURE_FORCE_LIMIT_MN

                if int(touch_vendor) == TouchVendor.Matrix:
                    # Matrix mode: fill the active physical part with simulated values, 
                    # and pad the rest up to 60 with zeros.
                    p_size = physical_sizes[module_index]
                    active_part = []
                    for i in range(p_size):
                        # High quality randomized wave using double frequency sines to simulate vibration/jitter
                        base_ratio = 0.35 + 0.25 * math.sin(tick * 0.6 + module_index * 1.3)
                        grid_noise = 0.08 * math.sin(tick * 4.7 + i * 2.9) + 0.04 * math.cos(tick * 9.3 - i * 4.3)
                        ratio = max(0.01, min(0.78, base_ratio + grid_noise))
                        active_part.append(int(limit_raw * ratio))
                    inactive_part = [0] * (60 - p_size)
                    self.modules.append(active_part + inactive_part)
                else:
                    pts_val = []
                    for i in range(size):
                        base_ratio = 0.35 + 0.25 * math.sin(tick * 0.6 + module_index * 1.3)
                        grid_noise = 0.08 * math.sin(tick * 4.7 + i * 2.9) + 0.04 * math.cos(tick * 9.3 - i * 4.3)
                        ratio = max(0.01, min(0.78, base_ratio + grid_noise))
                        pts_val.append(int(limit_raw * ratio))
                    self.modules.append(pts_val)


class MockDeviceContext:
    """Small PyDeviceContext-compatible mock for Revo3 GUI panels."""

    is_mock = True

    def __init__(self, mock_type=None):
        self.mock_type = mock_type or "revo3-touch"
        self.hw_type = mock_hardware_type(self.mock_type)
        self.touch_vendor = 2 if "matrix" in (self.mock_type or "").lower() else 1
        self.start_time = time.time()
        self.positions = [0.0] * REVO3_MOTOR_COUNT
        self.velocities = [0.0] * REVO3_MOTOR_COUNT
        self.currents = [0.0] * REVO3_MOTOR_COUNT
        self.servo_drags = {}
        self.collision_config = None
        self.collision_active = [False] * REVO3_MOTOR_COUNT
        self.flags = {
            "auto_calibration": True,
            "touch_screen": has_touch(self.hw_type),
            "buzzer": True,
            "vibration": True,
            "teaching_mode": False,
            "software_e_stop": False,
            "use_broadcast_id": False,
            "touch_data_type": 0,
            "touch_module_value_type": 2,
            "touch_modules_enabled": 0x7FF,
        }
        self.global_protect_current = 1500
        self.joint_protect_currents = [1200] * REVO3_MOTOR_COUNT
        self.joint_position_limits = [(0.0, 100.0)] * REVO3_MOTOR_COUNT
        self.joint_speed_limits = [(0.0, 360.0)] * REVO3_MOTOR_COUNT

    def _device_info(self):
        sku = getattr(_sdk_attr("SkuType", None), "MediumRight", 0)
        hand = getattr(_sdk_attr("HandType", None), "Right", 0)
        return MockDeviceInfo(
            hardware_type=self.hw_type,
            sku_type=sku,
            hand_type=hand,
            serial_number=(
                "BCUTL40000000000"
                if self.touch_vendor == TouchVendor.Matrix
                else f"MOCK-{str(self.hw_type).upper()}"
            ),
            firmware_version="mock-3.0.0",
            hardware_version="mock-hw-1.0",
        )

    def _status(self):
        t = time.time() - self.start_time
        positions = [p + math.sin(t + i * 0.2) * 0.15 for i, p in enumerate(self.positions)]
        velocities = [v + math.sin(t * 1.5 + i * 0.1) * 0.5 for i, v in enumerate(self.velocities)]
        currents = [c + 80.0 + 20.0 * math.sin(t + i * 0.33) for i, c in enumerate(self.currents)]
        status = MockRevo3MotorStatusData(positions, velocities, currents)
        status.temperatures = [34.0 + 2.0 * math.sin(t * 0.2 + i) for i in range(REVO3_MOTOR_COUNT)]
        return status

    async def get_device_info(self, _slave_id):
        return self._device_info()

    async def revo3_get_device_info(self, _slave_id):
        return self._device_info()

    async def get_touch_vendor(self, _slave_id):
        TouchVendor = _sdk_attr("TouchVendor", None)
        if TouchVendor is not None:
            return TouchVendor(self.touch_vendor)
        return self.touch_vendor

    async def revo3_get_touch_vendor(self, _slave_id):
        TouchVendor = _sdk_attr("TouchVendor", None)
        if TouchVendor is not None:
            return TouchVendor(self.touch_vendor)
        return self.touch_vendor

    async def revo3_set_touch_vendor(self, _slave_id, vendor):
        self.touch_vendor = int(vendor)
        return True

    async def revo3_get_hardware_version(self, _slave_id):
        return "mock-hw-1.0"

    async def revo3_get_motor_online_status(self, _slave_id):
        return (1 << REVO3_MOTOR_COUNT) - 1

    async def revo3_get_all_motor_temperatures(self, _slave_id):
        return self._status().temperatures

    async def revo3_get_all_motor_errors(self, _slave_id):
        return [0] * REVO3_MOTOR_COUNT

    async def revo3_get_all_motor_sns(self, _slave_id):
        return [f"MOCK-M{i:02d}" for i in range(REVO3_MOTOR_COUNT)]

    async def revo3_get_motor_fw_versions(self, _slave_id):
        return ["mock-1.0"] * REVO3_MOTOR_COUNT

    async def revo3_get_system_status(self, _slave_id):
        return MockRevo3SystemStatus(time.time() - self.start_time)

    async def revo3_get_global_protect_current(self, _slave_id):
        return self.global_protect_current

    async def revo3_set_global_protect_current(self, _slave_id, value):
        self.global_protect_current = value

    async def revo3_set_calibration_current(self, _slave_id, _value):
        return True

    async def revo3_manual_calibration(self, _slave_id):
        return True

    async def revo3_get_all_joint_protect_currents(self, _slave_id):
        return list(self.joint_protect_currents)

    async def revo3_set_joint_protect_current(self, _slave_id, motor_id, value):
        self.joint_protect_currents[int(motor_id)] = value

    async def revo3_get_all_joint_position_limits(self, _slave_id):
        return list(self.joint_position_limits)

    async def revo3_set_joint_position_limits(self, _slave_id, motor_id, min_value, max_value):
        self.joint_position_limits[int(motor_id)] = (min_value, max_value)

    async def revo3_get_all_joint_speed_limits(self, _slave_id):
        return list(self.joint_speed_limits)

    async def revo3_set_joint_speed_limits(self, _slave_id, motor_id, min_value, max_value):
        self.joint_speed_limits[int(motor_id)] = (min_value, max_value)

    async def revo3_set_motor_position(self, _slave_id, motor_id, value):
        self.positions[int(motor_id)] = float(value)

    async def revo3_set_all_motor_positions(self, _slave_id, values):
        self.positions = self._pad(values)

    async def revo3_set_motor_velocity(self, _slave_id, motor_id, value):
        self.velocities[int(motor_id)] = float(value)

    async def revo3_set_all_motor_velocities(self, _slave_id, values):
        self.velocities = self._pad(values)

    async def revo3_set_motor_current(self, _slave_id, motor_id, value):
        self.currents[int(motor_id)] = float(value)

    async def revo3_set_all_motor_currents(self, _slave_id, values):
        self.currents = self._pad(values)

    async def revo3_set_motor_mit(self, _slave_id, motor_id, position, velocity=0.0, *_args):
        self.positions[int(motor_id)] = float(position)
        self.velocities[int(motor_id)] = float(velocity)

    async def revo3_start_servo_drag(self, _slave_id, motor_id, target_pos, *_args):
        motor_id = int(motor_id)
        self.servo_drags[motor_id] = float(target_pos)
        self.positions[motor_id] = float(target_pos)

    def revo3_update_servo_drag(self, _slave_id, motor_id, target_pos):
        motor_id = int(motor_id)
        if motor_id not in self.servo_drags:
            raise RuntimeError(f"servo_drag is not active for joint {motor_id}")
        self.servo_drags[motor_id] = float(target_pos)
        self.positions[motor_id] = float(target_pos)

    async def revo3_cancel_servo_drag(self, _slave_id, motor_id):
        self.servo_drags.pop(int(motor_id), None)

    async def revo3_stop_servo_drag(self, _slave_id, motor_id, final_pos):
        motor_id = int(motor_id)
        self.servo_drags.pop(motor_id, None)
        self.positions[motor_id] = float(final_pos)

    async def revo3_single_joint_control(self, _slave_id, motor_id, mode, value):
        if int(mode) in (0, 4, 5):
            self.positions[int(motor_id)] = float(value) / (100.0 if int(mode) in (4, 5) else 1.0)

    async def revo3_multi_joint_control(self, _slave_id, _mode, values):
        self.positions = self._pad(values)

    async def revo3_set_all_mit_params(
        self, _slave_id, _kp_values, _kd_values, positions, velocities, _torques
    ):
        self.positions = self._pad(positions)
        self.velocities = self._pad(velocities)

    def revo3_set_collision_protection_config(self, _slave_id, config):
        self.collision_config = config
        return True

    def revo3_get_collision_protection_config(self, _slave_id):
        return self.collision_config

    def revo3_is_collision_active(self, _slave_id, joint_id):
        return self.collision_active[int(joint_id)]

    def revo3_get_all_collision_active(self, _slave_id):
        return list(self.collision_active)

    def revo3_reset_collision_state(self, _slave_id):
        self.collision_active = [False] * REVO3_MOTOR_COUNT
        return True

    async def revo3_move_joint_with_gains(self, slave_id, motor_id, position, *_args):
        await self.revo3_set_motor_position(slave_id, motor_id, position)

    async def revo3_move_joint_with_gains_wait(self, slave_id, motor_id, position, *_args):
        await self.revo3_set_motor_position(slave_id, motor_id, position)

    async def revo3_move_joint_with_speed_and_gains(self, slave_id, motor_id, position, *_args):
        await self.revo3_set_motor_position(slave_id, motor_id, position)

    async def revo3_move_joint_with_speed_and_gains_wait(self, slave_id, motor_id, position, *_args):
        await self.revo3_set_motor_position(slave_id, motor_id, position)

    async def revo3_move_hand_with_gains(self, slave_id, positions, *_args):
        await self.revo3_set_all_motor_positions(slave_id, positions)

    async def revo3_move_hand_with_gains_wait(self, slave_id, positions, *_args):
        await self.revo3_set_all_motor_positions(slave_id, positions)

    async def revo3_move_hand_with_speed_and_gains(self, slave_id, positions, *_args):
        await self.revo3_set_all_motor_positions(slave_id, positions)

    async def revo3_move_hand_with_speed_and_gains_wait(self, slave_id, positions, *_args):
        await self.revo3_set_all_motor_positions(slave_id, positions)

    async def revo3_set_fingertip_pose(self, _slave_id, _finger_id, _pose):
        return True

    async def revo3_clear_motor_errors(self, _slave_id):
        return True

    async def revo3_reset_finger_defaults(self, _slave_id):
        return True

    async def revo3_get_auto_calibration(self, _slave_id):
        return self.flags["auto_calibration"]

    async def revo3_set_auto_calibration(self, _slave_id, enabled):
        self.flags["auto_calibration"] = bool(enabled)

    async def revo3_get_touch_screen(self, _slave_id):
        return self.flags["touch_screen"]

    async def revo3_set_touch_screen(self, _slave_id, enabled):
        self.flags["touch_screen"] = bool(enabled)

    async def revo3_get_buzzer_switch(self, _slave_id):
        return self.flags["buzzer"]

    async def revo3_set_buzzer_switch(self, _slave_id, enabled):
        self.flags["buzzer"] = bool(enabled)

    async def revo3_get_vibration_switch(self, _slave_id):
        return self.flags["vibration"]

    async def revo3_set_vibration_switch(self, _slave_id, enabled):
        self.flags["vibration"] = bool(enabled)

    async def revo3_get_teaching_mode(self, _slave_id):
        return self.flags["teaching_mode"]

    async def revo3_set_teaching_mode(self, _slave_id, enabled):
        self.flags["teaching_mode"] = bool(enabled)

    async def revo3_get_software_e_stop(self, _slave_id):
        return self.flags["software_e_stop"]

    async def revo3_set_software_e_stop(self, _slave_id, enabled):
        self.flags["software_e_stop"] = bool(enabled)

    async def revo3_get_use_broadcast_id(self, _slave_id):
        return self.flags["use_broadcast_id"]

    async def revo3_set_use_broadcast_id(self, _slave_id, enabled):
        self.flags["use_broadcast_id"] = bool(enabled)

    async def revo3_get_all_touch_data(self, _slave_id):
        data_type = self.flags.get("touch_data_type", 0)
        return MockRevo3TouchData(
            time.time() - self.start_time,
            data_type=data_type,
            touch_vendor=self.touch_vendor,
        )

    async def revo3_get_touch_data_type(self, _slave_id):
        return self.flags.get("touch_data_type", 0)

    async def revo3_set_touch_data_type(self, _slave_id, data_type):
        self.flags["touch_data_type"] = int(data_type)
        return True

    async def revo3_get_touch_module_value_type(self, _slave_id):
        return self.flags.get("touch_module_value_type", 2)

    async def revo3_set_touch_module_value_type(self, _slave_id, value_type):
        self.flags["touch_module_value_type"] = int(value_type)
        return True

    async def revo3_get_all_touch_modules_enabled(self, _slave_id):
        return self.flags.get("touch_modules_enabled", 0x7FF)

    async def revo3_set_all_touch_modules_enabled(self, _slave_id, enabled_mask):
        self.flags["touch_modules_enabled"] = int(enabled_mask)
        return True

    async def revo3_get_touch_module_enabled(self, _slave_id, module_id):
        mask = self.flags.get("touch_modules_enabled", 0x7FF)
        return bool(mask & (1 << int(module_id)))

    async def revo3_set_touch_module_enabled(self, _slave_id, module_id, enabled):
        mask = self.flags.get("touch_modules_enabled", 0x7FF)
        if enabled:
            mask |= (1 << int(module_id))
        else:
            mask &= ~(1 << int(module_id))
        self.flags["touch_modules_enabled"] = mask
        return True

    async def revo3_get_touch_module_data(self, _slave_id, module_id):
        data = await self.revo3_get_all_touch_data(_slave_id)
        if int(module_id) < len(data.modules):
            return data.modules[int(module_id)]
        return [0] * 60

    async def revo3_calibrate_touch_zero(self, _slave_id):
        self.flags["matrix_touch_tare_status"] = 1
        return True

    async def revo3_calibrate_touch_zero_single(self, _slave_id, module_id):
        # Mark as tared
        self.flags[f"matrix_touch_tare_status_{int(module_id)}"] = 1
        return True

    async def revo3_calibrate_pressure_touch_zero(self, _slave_id):
        self.flags["pressure_touch_zero"] = True
        return True

    async def revo3_calibrate_pressure_touch_module_zero(self, _slave_id, module_id):
        self.flags[f"pressure_touch_zero_{int(module_id)}"] = True
        return True

    async def revo3_set_pressure_touch_force_tare(self, _slave_id, command):
        self.flags["pressure_touch_force_tare"] = int(command)
        return True

    async def revo3_set_pressure_touch_module_force_tare(self, _slave_id, module_id, command):
        self.flags[f"pressure_touch_force_tare_{int(module_id)}"] = int(command)
        return True

    async def revo3_get_all_matrix_touch_module_serial_numbers(self, _slave_id):
        return [f"MATRIX-MOCK-{i:02d}" for i in range(11)]

    async def revo3_get_matrix_touch_module_serial_number(self, _slave_id, module_id):
        return f"MATRIX-MOCK-{int(module_id):02d}"

    async def revo3_restart_matrix_touch_modules(self, _slave_id):
        return True

    async def revo3_restart_matrix_touch_module(self, _slave_id, module_id):
        self.flags[f"matrix_touch_tare_status_{int(module_id)}"] = 0
        return True

    async def revo3_get_all_matrix_touch_module_point_counts(self, _slave_id):
        return [60] * 11

    async def revo3_get_matrix_touch_output_mode(self, _slave_id):
        MatrixTouchOutputMode = _sdk_attr("MatrixTouchOutputMode", None)
        value = self.flags.get("matrix_touch_output_mode", 1)
        return MatrixTouchOutputMode(value) if MatrixTouchOutputMode is not None else value

    async def revo3_set_matrix_touch_output_mode(self, _slave_id, mode):
        self.flags["matrix_touch_output_mode"] = int(mode)
        return True

    async def revo3_get_matrix_touch_module_output_mode(self, _slave_id, module_id):
        MatrixTouchOutputMode = _sdk_attr("MatrixTouchOutputMode", None)
        value = self.flags.get(f"matrix_touch_output_mode_{int(module_id)}", 1)
        return MatrixTouchOutputMode(value) if MatrixTouchOutputMode is not None else value

    async def revo3_set_matrix_touch_module_output_mode(self, _slave_id, module_id, mode):
        self.flags[f"matrix_touch_output_mode_{int(module_id)}"] = int(mode)
        return True

    async def revo3_get_matrix_touch_tare_status(self, _slave_id):
        MatrixTouchTareStatus = _sdk_attr("MatrixTouchTareStatus", None)
        value = self.flags.get("matrix_touch_tare_status", 1)
        return MatrixTouchTareStatus(value) if MatrixTouchTareStatus is not None else value

    async def revo3_set_matrix_touch_tare(self, _slave_id, command):
        self.flags["matrix_touch_tare_status"] = 1 if int(command) == 1 else 0
        return True

    async def revo3_get_matrix_touch_module_tare_status(self, _slave_id, module_id):
        MatrixTouchTareStatus = _sdk_attr("MatrixTouchTareStatus", None)
        value = self.flags.get(f"matrix_touch_tare_status_{int(module_id)}", 1)
        return MatrixTouchTareStatus(value) if MatrixTouchTareStatus is not None else value

    async def revo3_set_matrix_touch_module_tare(self, _slave_id, module_id, command):
        self.flags[f"matrix_touch_tare_status_{int(module_id)}"] = 1 if int(command) == 1 else 0
        return True

    async def revo3_reboot(self, _slave_id):
        return True

    async def revo3_start_dfu(
        self,
        slave_id,
        _firmware_path,
        _timeout=5,
        on_dfu_state=None,
        on_dfu_progress=None,
    ):
        if on_dfu_state:
            on_dfu_state(slave_id, 1)
        if on_dfu_progress:
            on_dfu_progress(slave_id, 1.0)
        if on_dfu_state:
            on_dfu_state(slave_id, 4)
        return True

    async def close(self):
        return True

    def get_protocol_type(self):
        if sdk is None:
            return None
        return sdk.StarkProtocolType.Modbus

    def _pad(self, values):
        padded = list(values or [])[:REVO3_MOTOR_COUNT]
        padded.extend([0.0] * (REVO3_MOTOR_COUNT - len(padded)))
        return [float(v) for v in padded]
