"""Revo3-only mock device for GUI debugging."""

import math
import time
from dataclasses import dataclass
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))
from common_imports import sdk


REVO3_ULTRA_JOINT_COUNT = 21
# Runtime counts observed on the validated mx_* fixture, not protocol capacities.
MX_TOUCH_POINT_COUNTS = [53, 56, 22, 21, 27, 21, 27, 21, 27, 21, 27]

# MockDeviceInfo reports a right hand, so force-mode mock points use the
# documented right-hand per-point ranges. The SDK exposes the values in mN.
MX_FORCE_LIMITS_RAW = [
    226, 63, 113, 236, 141, 236, 141, 236, 141, 236, 141,
]

MT_FORCE_LIMIT_MN = 20000.0
MT_ADC_MAX = 4096.0


def _sdk_attr(enum_name: str, fallback):
    if sdk is None:
        return fallback
    enum = getattr(sdk, enum_name, None)
    return enum if enum is not None else fallback


def _sdk_enum_member(enum_name: str, names, fallback):
    enum_type = _sdk_attr(enum_name, None)
    if enum_type is None:
        return fallback
    for name in names:
        member = getattr(enum_type, name, None)
        if member is not None:
            return member
    return fallback


def mock_model(mock_type):
    kind = (mock_type or "revo3-touch").lower().replace("_", "-")
    if sdk is None:
        return 21
    if kind in ("revo3", "revo3-ultra", "ultra"):
        return sdk.Revo3Model.Ultra
    if kind in ("revo3-vision", "revo3-vision-touch", "vision", "vision-touch"):
        return sdk.Revo3Model.UltraVisionTouch
    if kind in ("revo3-pro", "pro"):
        return sdk.Revo3Model.Pro
    if kind in ("revo3-mx-touch", "mx-touch"):
        return sdk.Revo3Model.UltraTouch
    if kind in ("revo3-pro-touch", "pro-touch", "revo3-pro-mx-touch", "pro-mx-touch"):
        return sdk.Revo3Model.ProTouch
    if kind in ("revo3-basic", "basic"):
        return sdk.Revo3Model.Basic
    if kind in ("revo3-basic-touch", "basic-touch", "revo3-basic-mx-touch", "basic-mx-touch"):
        return sdk.Revo3Model.BasicTouch
    return sdk.Revo3Model.UltraTouch


@dataclass
class MockDeviceInfo:
    model: object
    hand_side: object
    serial_number: str
    firmware_version: str
    hardware_revision: str

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
        self.operating_states = [0] * REVO3_ULTRA_JOINT_COUNT
        self.positions = list(positions or [0.0] * REVO3_ULTRA_JOINT_COUNT)[:REVO3_ULTRA_JOINT_COUNT]
        self.velocities = list(velocities or [0.0] * REVO3_ULTRA_JOINT_COUNT)[:REVO3_ULTRA_JOINT_COUNT]
        self.currents = list(currents or [0.0] * REVO3_ULTRA_JOINT_COUNT)[:REVO3_ULTRA_JOINT_COUNT]
        self.fault_codes = [0] * REVO3_ULTRA_JOINT_COUNT
        self.temperatures = [34.0] * REVO3_ULTRA_JOINT_COUNT
        self.speeds = self.velocities


class MockRevo3TouchData:
    def __init__(
        self,
        tick: float = 0.0,
        read_mode: int = 0,
        is_mx: bool = False,
        mx_modes=None,
        mt_value_mode: int = 2,
    ):
        physical_sizes = (
            MX_TOUCH_POINT_COUNTS
            if is_mx
            else [36, 31, 57, 21, 52, 21, 52, 21, 52, 21, 52]
        )
        mx_modes = list(mx_modes or [2] * 11)
        module_sizes = physical_sizes
        
        force_summary_val = int(
            _sdk_enum_member(
                "TouchReadMode",
                ("LegacyForceSummary", "ForceSummary"),
                1,
            )
        )
        
        if int(read_mode) == force_summary_val:
            self.summary_values = [
                int(MT_FORCE_LIMIT_MN * (0.08 + 0.72 * abs(math.sin(tick + i * 0.31))))
                for i in range(42)
            ]
            self.modules = [[0] * size for size in module_sizes]
        else:
            self.summary_values = [int(120 + 80 * abs(math.sin(tick + i * 0.31))) for i in range(42)]
            self.modules = []
            for module_index, size in enumerate(module_sizes):
                # Calculate the limit from the module layout and data type.
                if is_mx:
                    is_force = mx_modes[module_index] == 2
                    limit_raw = MX_FORCE_LIMITS_RAW[module_index] * 10 if is_force else 255.0
                else:
                    limit_raw = (
                        MT_FORCE_LIMIT_MN
                        if int(mt_value_mode) == 2
                        else MT_ADC_MAX
                    )

                if is_mx:
                    # mx_* mode: fill every point reported by the public layout.
                    p_size = module_sizes[module_index]
                    active_part = []
                    for i in range(p_size):
                        # High quality randomized wave using double frequency sines to simulate vibration/jitter
                        base_ratio = 0.35 + 0.25 * math.sin(tick * 0.6 + module_index * 1.3)
                        grid_noise = 0.08 * math.sin(tick * 4.7 + i * 2.9) + 0.04 * math.cos(tick * 9.3 - i * 4.3)
                        ratio = max(0.01, min(0.78, base_ratio + grid_noise))
                        active_part.append(int(limit_raw * ratio))
                    inactive_part = [0] * (size - p_size)
                    self.modules.append(active_part + inactive_part)
                else:
                    pts_val = []
                    for i in range(size):
                        base_ratio = 0.35 + 0.25 * math.sin(tick * 0.6 + module_index * 1.3)
                        grid_noise = 0.08 * math.sin(tick * 4.7 + i * 2.9) + 0.04 * math.cos(tick * 9.3 - i * 4.3)
                        ratio = max(0.01, min(0.78, base_ratio + grid_noise))
                        pts_val.append(int(limit_raw * ratio))
                    self.modules.append(pts_val)


class MockHand:
    """Small Hand-compatible mock for Revo3 GUI panels."""

    is_mock = True

    def __init__(self, mock_type=None):
        self.mock_type = mock_type or "revo3-touch"
        self.model = mock_model(self.mock_type)
        self.supports_touch = "touch" in self.mock_type.lower()
        self.has_mx_touch = self.supports_touch and "mx" in self.mock_type.lower()
        self.is_hp_touch = self.supports_touch and "hp" in self.mock_type.lower()
        self.start_time = time.time()
        self.positions = [0.0] * REVO3_ULTRA_JOINT_COUNT
        self.velocities = [0.0] * REVO3_ULTRA_JOINT_COUNT
        self.currents = [0.0] * REVO3_ULTRA_JOINT_COUNT
        self.servo_drags = {}
        self.collision_config = None
        self.collision_active = [False] * REVO3_ULTRA_JOINT_COUNT
        self.flags = {
            "auto_calibration": True,
            "touch_screen": self.supports_touch,
            "buzzer": True,
            "vibration": True,
            "teaching_mode": False,
            "software_e_stop": False,
            "use_broadcast_id": False,
            "auto_clear_motor_faults": False,
            "touch_read_mode": 0,
            "touch_modules_enabled": 0x7FF,
        }
        self.global_protect_current = 1500
        self.max_continuous_current = 1000.0
        self.joint_protect_currents = [1200] * REVO3_ULTRA_JOINT_COUNT
        self.joint_position_limits = [(0.0, 100.0)] * REVO3_ULTRA_JOINT_COUNT
        self.joint_speed_limits = [(0.0, 360.0)] * REVO3_ULTRA_JOINT_COUNT

    def _device_info(self):
        hand = getattr(_sdk_attr("HandSide", None), "Right", 0)
        return MockDeviceInfo(
            model=self.model,
            hand_side=hand,
            serial_number=(
                "BCUTL40000000000"
                if self.has_mx_touch
                else f"MOCK-{str(self.model).upper()}"
            ),
            firmware_version="mock-3.0.0",
            hardware_revision="mock-hw-1.0",
        )

    def _status(self):
        t = time.time() - self.start_time
        positions = [p + math.sin(t + i * 0.2) * 0.15 for i, p in enumerate(self.positions)]
        velocities = [v + math.sin(t * 1.5 + i * 0.1) * 0.5 for i, v in enumerate(self.velocities)]
        currents = [c + 80.0 + 20.0 * math.sin(t + i * 0.33) for i, c in enumerate(self.currents)]
        status = MockRevo3MotorStatusData(positions, velocities, currents)
        status.temperatures = [34.0 + 2.0 * math.sin(t * 0.2 + i) for i in range(REVO3_ULTRA_JOINT_COUNT)]
        return status

    async def get_device_info(self, _slave_id):
        return self._device_info()

    @property
    def touch_layout(self):
        class MockTouchModule:
            def __init__(self, layout_id):
                self.layout_id = layout_id
        class MockTouchLayout:
            def __init__(self, modules):
                self.modules = modules

        if not self.supports_touch:
            lids = []
        elif self.has_mx_touch:
            lids = [f"mx_module_{i}" for i in range(11)]
        elif self.is_hp_touch:
            lids = [f"hp_fingertip_48_{i}" for i in range(5)]
        else:
            lids = [f"mt_module_{i}" for i in range(11)]
        return MockTouchLayout([MockTouchModule(lid) for lid in lids])

    async def get_touch_layout(self, _slave_id=None):
        return self.touch_layout

    async def get_hardware_revision(self, _slave_id):
        return "mock-hw-1.0"

    async def get_motor_online_mask(self, _slave_id):
        return (1 << REVO3_ULTRA_JOINT_COUNT) - 1

    async def get_all_motor_module_temperatures(self, _slave_id):
        return self._status().temperatures

    async def get_all_joint_fault_codes(self, _slave_id):
        return [0] * REVO3_ULTRA_JOINT_COUNT

    async def get_all_motor_sns(self, _slave_id):
        return [f"MOCK-M{i:02d}" for i in range(REVO3_ULTRA_JOINT_COUNT)]

    async def get_motor_fw_versions(self, _slave_id):
        return ["mock-1.0"] * REVO3_ULTRA_JOINT_COUNT

    async def get_system_status(self, _slave_id):
        return MockRevo3SystemStatus(time.time() - self.start_time)

    async def get_global_protect_current(self, _slave_id):
        return self.global_protect_current

    async def set_global_protect_current(self, _slave_id, value):
        self.global_protect_current = value

    async def set_calibration_current(self, _slave_id, _value):
        return True

    async def manual_calibration(self, _slave_id):
        return True

    async def get_all_joint_protect_currents(self, _slave_id):
        return list(self.joint_protect_currents)

    async def set_joint_protect_current(self, _slave_id, motor_id, value):
        self.joint_protect_currents[int(motor_id)] = value

    async def get_all_joint_position_limits(self, _slave_id):
        return list(self.joint_position_limits)

    async def set_joint_position_limits(self, _slave_id, motor_id, min_value, max_value):
        self.joint_position_limits[int(motor_id)] = (min_value, max_value)

    async def get_all_joint_speed_limits(self, _slave_id):
        return list(self.joint_speed_limits)

    async def set_joint_speed_limits(self, _slave_id, motor_id, min_value, max_value):
        self.joint_speed_limits[int(motor_id)] = (min_value, max_value)

    async def set_joint_position(self, _slave_id, motor_id, value):
        self.positions[int(motor_id)] = float(value)

    async def set_all_motor_positions(self, _slave_id, values):
        self.positions = self._pad(values)

    async def set_joint_velocity(self, _slave_id, motor_id, value):
        self.velocities[int(motor_id)] = float(value)

    async def set_all_motor_velocities(self, _slave_id, values):
        self.velocities = self._pad(values)

    async def set_joint_current(self, _slave_id, motor_id, value):
        self.currents[int(motor_id)] = float(value)

    async def set_all_motor_currents(self, _slave_id, values):
        self.currents = self._pad(values)

    async def set_joint_mit(self, _slave_id, motor_id, position, velocity=0.0, *_args):
        self.positions[int(motor_id)] = float(position)
        self.velocities[int(motor_id)] = float(velocity)

    async def start_servo_drag(self, _slave_id, motor_id, target_pos, *_args):
        motor_id = int(motor_id)
        self.servo_drags[motor_id] = float(target_pos)
        self.positions[motor_id] = float(target_pos)

    def update_servo_drag(self, _slave_id, motor_id, target_pos):
        motor_id = int(motor_id)
        if motor_id not in self.servo_drags:
            raise RuntimeError(f"servo_drag is not active for joint {motor_id}")
        self.servo_drags[motor_id] = float(target_pos)
        self.positions[motor_id] = float(target_pos)

    async def cancel_servo_drag(self, _slave_id, motor_id):
        self.servo_drags.pop(int(motor_id), None)

    async def stop_servo_drag(self, _slave_id, motor_id, final_pos):
        motor_id = int(motor_id)
        self.servo_drags.pop(motor_id, None)
        self.positions[motor_id] = float(final_pos)

    async def single_joint_control(self, _slave_id, motor_id, mode, value):
        if int(mode) in (0, 4, 5):
            self.positions[int(motor_id)] = float(value) / (100.0 if int(mode) in (4, 5) else 1.0)

    async def multi_joint_control(self, _slave_id, _mode, values):
        self.positions = self._pad(values)

    async def set_all_mit_params(
        self,
        _slave_id,
        _kp_values,
        _kd_values,
        positions,
        velocities,
        _feedforward_currents,
    ):
        self.positions = self._pad(positions)
        self.velocities = self._pad(velocities)

    def set_collision_protection_config(self, _slave_id, config):
        self.collision_config = config
        return True

    def get_collision_protection_config(self, _slave_id):
        return self.collision_config

    def is_collision_active(self, _slave_id, joint_id):
        return self.collision_active[int(joint_id)]

    def get_all_collision_active(self, _slave_id):
        return list(self.collision_active)

    def reset_collision_state(self, _slave_id):
        self.collision_active = [False] * REVO3_ULTRA_JOINT_COUNT
        return True

    async def get_config_snapshot(self, _slave_id=None):
        class _MockConfig:
            pass

        config = _MockConfig()
        config.power_on_auto_calibration_enabled = self.flags["auto_calibration"]
        config.touch_screen_enabled = self.flags["touch_screen"]
        config.buzzer_enabled = self.flags["buzzer"]
        config.vibration_enabled = self.flags["vibration"]
        config.teaching_mode_enabled = self.flags["teaching_mode"]
        config.software_stop_enabled = self.flags["software_e_stop"]
        config.use_broadcast_id = self.flags["use_broadcast_id"]
        config.auto_clear_motor_faults_enabled = self.flags[
            "auto_clear_motor_faults"
        ]
        config.global_protect_current_ma = float(self.global_protect_current)
        config.max_continuous_current_ma = float(self.max_continuous_current)
        config.joint_protect_current_ma = list(self.joint_protect_currents)
        config.joint_min_position_deg = [
            limits[0] for limits in self.joint_position_limits
        ]
        config.joint_max_position_deg = [
            limits[1] for limits in self.joint_position_limits
        ]
        config.joint_min_speed_rpm = [
            limits[0] for limits in self.joint_speed_limits
        ]
        config.joint_max_speed_rpm = [
            limits[1] for limits in self.joint_speed_limits
        ]
        return config

    async def move_joint_with_gains(self, slave_id, motor_id, position, *_args):
        await self.set_joint_position(slave_id, motor_id, position)

    async def move_joint_with_gains_wait(self, slave_id, motor_id, position, *_args):
        await self.set_joint_position(slave_id, motor_id, position)

    async def move_joint_with_speed_and_gains(self, slave_id, motor_id, position, *_args):
        await self.set_joint_position(slave_id, motor_id, position)

    async def move_joint_with_speed_and_gains_wait(self, slave_id, motor_id, position, *_args):
        await self.set_joint_position(slave_id, motor_id, position)

    async def move_hand_with_gains(self, slave_id, positions, *_args):
        await self.set_all_motor_positions(slave_id, positions)

    async def move_hand_with_gains_wait(self, slave_id, positions, *_args):
        await self.set_all_motor_positions(slave_id, positions)

    async def move_hand_with_speed_and_gains(self, slave_id, positions, *_args):
        await self.set_all_motor_positions(slave_id, positions)

    async def move_hand_with_speed_and_gains_wait(self, slave_id, positions, *_args):
        await self.set_all_motor_positions(slave_id, positions)

    async def clear_motor_faults(self, _slave_id):
        return True

    async def reset_finger_defaults(self, _slave_id):
        return True

    async def get_power_on_auto_calibration(self, _slave_id):
        return self.flags["auto_calibration"]

    async def set_power_on_auto_calibration(self, _slave_id, enabled):
        self.flags["auto_calibration"] = bool(enabled)

    async def get_touch_screen(self, _slave_id):
        return self.flags["touch_screen"]

    async def set_touch_screen(self, _slave_id, enabled):
        self.flags["touch_screen"] = bool(enabled)

    async def get_buzzer_switch(self, _slave_id):
        return self.flags["buzzer"]

    async def set_buzzer_switch(self, _slave_id, enabled):
        self.flags["buzzer"] = bool(enabled)

    async def set_buzzer(self, _slave_id, enabled):
        self.flags["buzzer"] = bool(enabled)

    async def get_vibration_switch(self, _slave_id):
        return self.flags["vibration"]

    async def set_vibration_switch(self, _slave_id, enabled):
        self.flags["vibration"] = bool(enabled)

    async def set_vibration(self, _slave_id, enabled):
        self.flags["vibration"] = bool(enabled)

    async def get_teaching_mode(self, _slave_id):
        return self.flags["teaching_mode"]

    async def set_teaching_mode(self, _slave_id, enabled):
        self.flags["teaching_mode"] = bool(enabled)

    async def get_software_e_stop(self, _slave_id):
        return self.flags["software_e_stop"]

    async def set_software_e_stop(self, _slave_id, enabled):
        self.flags["software_e_stop"] = bool(enabled)

    async def get_use_broadcast_id(self, _slave_id):
        return self.flags["use_broadcast_id"]

    async def set_use_broadcast_id(self, _slave_id, enabled):
        self.flags["use_broadcast_id"] = bool(enabled)

    async def set_auto_clear_motor_faults(self, _slave_id, enabled):
        self.flags["auto_clear_motor_faults"] = bool(enabled)

    async def set_max_continuous_current(self, _slave_id, value):
        self.max_continuous_current = float(value)

    async def get_all_touch_data(self, _slave_id):
        read_mode = self.flags.get("touch_read_mode", 0)
        global_mode = self.flags.get("touch_value_mode", 2)
        mx_modes = [
            self.flags.get(f"touch_value_mode_{module_id}", global_mode)
            for module_id in range(11)
        ]
        return MockRevo3TouchData(
            time.time() - self.start_time,
            read_mode=read_mode,
            is_mx=self.has_mx_touch,
            mx_modes=mx_modes,
            mt_value_mode=global_mode,
        )

    async def get_touch_read_mode(self, _slave_id):
        return self.flags.get("touch_read_mode", 0)

    async def set_touch_read_mode(self, _slave_id, read_mode):
        self.flags["touch_read_mode"] = int(read_mode)
        return True

    async def get_all_touch_modules_enabled(self, _slave_id):
        return self.flags.get("touch_modules_enabled", 0x7FF)

    async def set_all_touch_modules_enabled(self, _slave_id, enabled_mask):
        self.flags["touch_modules_enabled"] = int(enabled_mask)
        return True

    async def get_touch_module_enabled(self, _slave_id, module_id):
        mask = self.flags.get("touch_modules_enabled", 0x7FF)
        return bool(mask & (1 << int(module_id)))

    async def set_touch_module_enabled(self, _slave_id, module_id, enabled):
        mask = self.flags.get("touch_modules_enabled", 0x7FF)
        if enabled:
            mask |= (1 << int(module_id))
        else:
            mask &= ~(1 << int(module_id))
        self.flags["touch_modules_enabled"] = mask
        return True

    async def calibrate_touch_zero(self, _slave_id):
        self.flags["touch_tare_status"] = 1
        return True

    async def calibrate_touch_zero_single(self, _slave_id, module_id):
        # Mark as tared
        self.flags[f"touch_tare_status_{int(module_id)}"] = 1
        return True



    async def get_touch_module_serial_numbers(self, _slave_id):
        return [f"MX-MOCK-{i:02d}" for i in range(11)]

    async def get_touch_module_serial_number(self, _slave_id, module_id):
        return f"MX-MOCK-{int(module_id):02d}"

    async def restart_touch_modules(self, _slave_id):
        return True

    async def restart_touch_module(self, _slave_id, module_id):
        self.flags[f"touch_tare_status_{int(module_id)}"] = 0
        return True

    async def get_touch_module_point_counts(self, _slave_id):
        return MX_TOUCH_POINT_COUNTS.copy()

    async def get_touch_value_mode(self, _slave_id):
        value = self.flags.get("touch_value_mode", 2)
        return value

    async def set_touch_value_mode(self, _slave_id, mode):
        self.flags["touch_value_mode"] = int(mode)
        return True

    async def get_touch_module_value_mode(self, _slave_id, module_id):
        value = self.flags.get(f"touch_value_mode_{int(module_id)}", 2)
        return value

    async def set_touch_module_value_mode(self, _slave_id, module_id, mode):
        self.flags[f"touch_value_mode_{int(module_id)}"] = int(mode)
        return True

    async def get_touch_tare_status(self, _slave_id):
        value = self.flags.get("touch_tare_status", 1)
        return value

    async def set_touch_tare(self, _slave_id, command):
        self.flags["touch_tare_status"] = 1 if int(command) == 1 else 0
        return True

    async def get_touch_module_tare_status(self, _slave_id, module_id):
        value = self.flags.get(f"touch_tare_status_{int(module_id)}", 1)
        return value

    async def get_touch_module_tare_statuses(self, _slave_id):
        return [await self.get_touch_module_tare_status(_slave_id, index) for index in range(11)]

    async def set_touch_module_tare(self, _slave_id, module_id, command):
        self.flags[f"touch_tare_status_{int(module_id)}"] = 1 if int(command) == 1 else 0
        return True

    async def reboot(self, _slave_id):
        return True

    async def start_dfu(
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
        return sdk.ProtocolType.Modbus

    def _pad(self, values):
        padded = list(values or [])[:REVO3_ULTRA_JOINT_COUNT]
        padded.extend([0.0] * (REVO3_ULTRA_JOINT_COUNT - len(padded)))
        return [float(v) for v in padded]
