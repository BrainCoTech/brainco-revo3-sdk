"""GUI-only adapter from the existing panels to the public 2.x object API."""

import asyncio
from dataclasses import dataclass
from types import SimpleNamespace

try:
    from common_imports import sdk
except ImportError:
    from ..common_imports import sdk


TOUCH_VALUE_MODE_ADC = 0
TOUCH_VALUE_MODE_FORCE = 2


def touch_value_mode_options(has_mt_touch: bool, has_mx_touch: bool):
    """Return public TouchValueMode values supported by the active layout."""
    options = [("ADC", TOUCH_VALUE_MODE_ADC)]
    if has_mt_touch or has_mx_touch:
        options.append(("Force", TOUCH_VALUE_MODE_FORCE))
    return options


def map_touch_metadata_by_public_module_id(
    layout, layout_prefix: str, values, default, size: int = 11
):
    """Map public-ID-ordered metadata onto sparse public touch module IDs."""
    modules = sorted(
        (
            module
            for module in list(getattr(layout, "modules", []) or [])
            if str(getattr(module, "layout_id", "") or "").startswith(
                layout_prefix
            )
        ),
        key=lambda module: int(getattr(module, "module_id", -1)),
    )
    values = list(values or [])
    if len(values) == size:
        selected_values = []
        for module in modules:
            module_id = int(getattr(module, "module_id", -1))
            if not 0 <= module_id < len(values):
                raise RuntimeError(
                    f"{layout_prefix} public module ID {module_id} is out of range"
                )
            selected_values.append(values[module_id])
    elif len(values) == len(modules):
        selected_values = values
    else:
        raise RuntimeError(
            f"{layout_prefix} metadata returned {len(values)} values "
            f"for {len(modules)} modules"
        )
    mapped = [default for _ in range(size)]
    for module, value in zip(modules, selected_values):
        module_id = int(getattr(module, "module_id", -1))
        if not 0 <= module_id < len(mapped):
            raise RuntimeError(
                f"{layout_prefix} public module ID {module_id} is out of range"
            )
        mapped[module_id] = value
    return mapped


def _has_touch_layout_prefix(layout, prefix: str) -> bool:
    return any(
        str(getattr(module, "layout_id", "")).startswith(prefix)
        for module in list(getattr(layout, "modules", []) or [])
    )


def _to_sdk_enum(enum_cls_name, val, int_map=None):
    if val is None:
        return None
    if sdk is not None and hasattr(sdk, enum_cls_name):
        enum_cls = getattr(sdk, enum_cls_name)
        if isinstance(val, enum_cls):
            return val
        if isinstance(val, int):
            if int_map and val in int_map:
                attr = int_map[val]
                if hasattr(enum_cls, attr):
                    return getattr(enum_cls, attr)
            try:
                return enum_cls(val)
            except Exception:
                pass
    return val


@dataclass
class GuiDeviceInfo:
    model: object
    hand_side: object
    serial_number: str
    firmware_version: str
    hardware_revision: str

class GuiHandAdapter:
    """Preserve panel behavior while keeping the SDK boundary on Manager/Hand."""

    def __init__(self, manager, hand, detected=None):
        self.manager = manager
        self.hand = hand
        self.detected = detected
        self.is_mock = False
        self._servo = None
        self._positions = [0.0] * 21
        self._velocities = [0.0] * 21
        self._currents = [0.0] * 21
        self._kp = [0.0] * 21
        self._kd = [0.0] * 21
        self._feedforward_currents = [0.0] * 21
        self._servo_filter_mode = 0
        self._servo_damping_omega = 25.0
        self._servo_lpf_alpha = 1.0
        self._active_servo_drag_joints = set()

    @classmethod
    async def connect(cls, sdk, detected):
        manager = sdk.Manager()
        try:
            hand = await manager.connect(detected)
        except (Exception, asyncio.CancelledError):
            try:
                await asyncio.wait_for(manager.close(), timeout=0.5)
            except (Exception, asyncio.CancelledError):
                pass
            raise
        return cls(manager, hand, detected)

    @classmethod
    async def connect_auto(cls, sdk, **kwargs):
        manager = sdk.Manager()
        try:
            hand = await manager.connect_auto(**kwargs)
        except Exception:
            await manager.close()
            raise
        return cls(manager, hand)

    async def close(self):
        if self._servo is not None:
            self._servo.close()
            self._servo = None
        for joint_index in list(self._active_servo_drag_joints):
            try:
                await self.hand.motion.cancel_servo_drag(joint_index)
            finally:
                self._active_servo_drag_joints.discard(joint_index)
        await self.hand.close()
        await self.manager.close()

    @property
    def supports_touch(self):
        return self.hand.touch.layout is not None

    @property
    def supports_touch_layout_override(self):
        info = getattr(self.hand, "device_info", None)
        model = getattr(info, "model", None)
        if sdk is not None and hasattr(sdk, "Revo3Model"):
            return model == sdk.Revo3Model.UltraTouch
        return "UltraTouch" in str(model) and "Vision" not in str(model)

    async def get_device_info(self, _slave_id=None):
        info = self.hand.device_info
        if info is None:
            raise RuntimeError("Device identity is unavailable")
        firmware = self.hand.firmware_info
        return GuiDeviceInfo(
            model=info.model,
            hand_side=info.hand_side,
            serial_number=info.serial_number,
            firmware_version=firmware.controller_firmware_version or "",
            hardware_revision=info.hardware_revision,
        )

    async def get_touch_layout(self, _slave_id=None):
        return getattr(getattr(self.hand, "touch", None), "layout", None)

    async def set_touch_layout(self, _slave_id, layout):
        return await self.hand.touch.set_layout(layout)

    def subscribe_touch(self, period=None):
        return self.hand.touch.subscribe(period=period)

    @property
    def touch_layout(self):
        return getattr(getattr(self.hand, "touch", None), "layout", None)

    async def get_hardware_revision(self, _slave_id=None):
        return (await self.get_device_info()).hardware_revision

    async def get_motor_status_data(self, _slave_id=None):
        snapshot = await self.hand.state.snapshot()
        self._positions = list(snapshot.positions_deg)
        self._velocities = list(snapshot.velocities_rpm)
        self._currents = list(snapshot.currents_ma)
        return snapshot

    async def get_all_joint_positions(self, _slave_id=None):
        return list((await self.get_motor_status_data()).positions)

    async def get_all_joint_velocities(self, _slave_id=None):
        return list((await self.get_motor_status_data()).velocities)

    async def get_all_joint_currents(self, _slave_id=None):
        return list((await self.get_motor_status_data()).currents)

    async def get_all_joint_operating_states(self, _slave_id=None):
        return list((await self.get_motor_status_data()).operating_states)

    async def get_motor_temperature(self, slave_id, motor_id):
        return (await self.get_all_motor_module_temperatures(slave_id))[int(motor_id)]

    async def get_motor_sn(self, slave_id, motor_id):
        return (await self.get_all_motor_sns(slave_id))[int(motor_id)]

    async def get_all_joint_fault_codes(self, _slave_id=None):
        return list((await self.hand.health.snapshot()).motor_fault_codes)

    async def get_all_motor_module_temperatures(self, _slave_id=None):
        return await self.hand.health.motor_module_temperatures_c()

    async def get_motor_online_mask(self, _slave_id=None):
        return await self.hand.health.motor_online_mask()

    async def get_all_motor_sns(self, _slave_id=None):
        info = await self.hand.refresh_device_info()
        return list(info.motor_serial_numbers) if info is not None else []

    async def get_motor_fw_versions(self, _slave_id=None):
        firmware = await self.hand.refresh_firmware_info()
        return list(firmware.motor_firmware_versions)

    async def refresh_firmware_versions(self, _slave_id=None):
        return await self.hand.refresh_firmware_info()

    async def get_system_status(self, _slave_id=None):
        return await self.hand.health.snapshot()

    async def get_system_current(self, slave_id=None):
        return (await self.get_system_status(slave_id)).current_ma

    async def get_system_voltage(self, slave_id=None):
        return (await self.get_system_status(slave_id)).voltage_v

    async def get_system_power(self, slave_id=None):
        return (await self.get_system_status(slave_id)).power_w

    async def get_system_temperature(self, slave_id=None):
        return (await self.get_system_status(slave_id)).temperature_c

    async def _servo_session(self):
        if self._servo is not None:
            state_str = str(getattr(self._servo, "state", ""))
            if state_str != "Active" and "Active" not in state_str:
                self._servo = None
        if self._servo is None:
            try:
                self._servo = self.hand.motion.open_servo()
            except Exception as e:
                if "not ready" in str(e):
                    await asyncio.sleep(0.1)
                    self._servo = self.hand.motion.open_servo()
                else:
                    raise
        return self._servo

    def _close_servo(self):
        if self._servo is not None:
            try:
                self._servo.close()
            except Exception:
                pass
            self._servo = None

    async def _refresh_control_state(self):
        snapshot = await self.get_motor_status_data()
        self._positions = list(snapshot.positions_deg)
        self._velocities = list(snapshot.velocities_rpm)
        self._currents = list(snapshot.currents_ma)

    async def _send_servo_action(self, action_fn):
        try:
            session = await self._servo_session()
            return await action_fn(session)
        except Exception as e:
            err_msg = str(e)
            if "closed" in err_msg or "expired" in err_msg or "not ready" in err_msg:
                self._servo = None
                await asyncio.sleep(0.1)
                session = await self._servo_session()
                return await action_fn(session)
            raise

    async def set_joint_position(self, _slave_id, motor_id, value):
        await self._refresh_control_state()
        self._positions[int(motor_id)] = float(value)
        await self._send_servo_action(lambda s: s.send_position(self._positions))

    async def set_all_motor_positions(self, _slave_id, values):
        self._positions = list(values)
        await self._send_servo_action(lambda s: s.send_position(self._positions))

    async def set_joint_velocity(self, _slave_id, motor_id, value):
        self._velocities[int(motor_id)] = float(value)
        await self._send_servo_action(lambda s: s.send_velocity(self._velocities))

    async def set_all_motor_velocities(self, _slave_id, values):
        self._velocities = list(values)
        await self._send_servo_action(lambda s: s.send_velocity(self._velocities))

    async def set_joint_current(self, _slave_id, motor_id, value):
        self._currents[int(motor_id)] = float(value)
        await self._send_servo_action(lambda s: s.send_current(self._currents))

    async def set_all_motor_currents(self, _slave_id, values):
        self._currents = list(values)
        await self._send_servo_action(lambda s: s.send_current(self._currents))

    async def set_joint_mit(
        self, _slave_id, motor_id, position, velocity, feedforward_current, kp, kd
    ):
        index = int(motor_id)
        self._positions[index] = float(position)
        self._velocities[index] = float(velocity)
        self._feedforward_currents[index] = float(feedforward_current)
        self._kp[index] = float(kp)
        self._kd[index] = float(kd)
        await self._send_servo_action(
            lambda s: s.send_mit(
                self._positions,
                self._velocities,
                self._kp,
                self._kd,
                self._feedforward_currents,
            )
        )

    async def set_all_mit_params(
        self, _slave_id, kp, kd, positions, velocities, feedforward_currents
    ):
        self._kp, self._kd = list(kp), list(kd)
        self._positions, self._velocities, self._feedforward_currents = (
            list(positions),
            list(velocities),
            list(feedforward_currents),
        )
        await self._send_servo_action(
            lambda s: s.send_mit(
                self._positions,
                self._velocities,
                self._kp,
                self._kd,
                self._feedforward_currents,
            )
        )

    async def set_all_mit_params_without_retry(self, *args):
        await self.set_all_mit_params(*args)

    async def joint_mit_control(self, *args):
        await self.set_joint_mit(*args)

    async def hand_mit_control(
        self, slave_id, kp, kd, positions, velocities, feedforward_currents
    ):
        await self.set_all_mit_params(
            slave_id, kp, kd, positions, velocities, feedforward_currents
        )

    async def finger_mit_control(self, slave_id, finger, params):
        start = (4 - int(finger)) * 4
        for offset in range(4):
            kp, kd, position, velocity, feedforward_current = params[
                offset * 5 : offset * 5 + 5
            ]
            await self.set_joint_mit(
                slave_id,
                start + offset,
                position,
                velocity,
                feedforward_current,
                kp,
                kd,
            )

    async def thumb_mit_control(self, slave_id, params):
        for offset in range(5):
            kp, kd, position, velocity, feedforward_current = params[
                offset * 5 : offset * 5 + 5
            ]
            await self.set_joint_mit(
                slave_id,
                16 + offset,
                position,
                velocity,
                feedforward_current,
                kp,
                kd,
            )

    async def set_joint_mit_params(
        self, slave_id, joint, kp, kd, position, velocity, feedforward_current
    ):
        await self.set_joint_mit(
            slave_id, joint, position, velocity, feedforward_current, kp, kd
        )

    async def set_all_mit_kp(self, _slave_id, values):
        self._kp = list(values)

    async def set_all_mit_kd(self, _slave_id, values):
        self._kd = list(values)

    async def set_all_mit_positions(self, _slave_id, values):
        self._positions = list(values)

    async def set_all_mit_velocities(self, _slave_id, values):
        self._velocities = list(values)

    async def set_all_mit_currents(self, _slave_id, values):
        self._feedforward_currents = list(values)

    async def start_servo_drag(
        self,
        _slave_id,
        motor_id,
        target_position,
        kp=2.0,
        kd=0.25,
        vel_cap_rpm=60.0,
        interval_ms=15,
        idle_timeout_ms=300,
        filter_mode=0,
        omega=35.0,
    ):
        self._close_servo()
        filter_mode = _to_sdk_enum(
            "ServoFilterMode",
            filter_mode,
            {
                0: "Disabled",
                1: "FirstOrderLpf",
                2: "SecondOrderCriticallyDamped",
            },
        )
        result = await self.hand.motion.start_servo_drag(
            int(motor_id),
            float(target_position),
            float(kp),
            float(kd),
            float(vel_cap_rpm),
            int(interval_ms),
            int(idle_timeout_ms),
            filter_mode,
            float(omega),
        )
        self._active_servo_drag_joints.add(int(motor_id))
        return result

    def update_servo_drag(self, _slave_id, motor_id, target_position):
        return self.hand.motion.update_servo_drag(int(motor_id), float(target_position))

    async def stop_servo_drag(self, _slave_id, motor_id, final_position):
        try:
            return await self.hand.motion.stop_servo_drag(int(motor_id), float(final_position))
        finally:
            self._active_servo_drag_joints.discard(int(motor_id))

    async def cancel_servo_drag(self, _slave_id, motor_id):
        try:
            return await self.hand.motion.cancel_servo_drag(int(motor_id))
        finally:
            self._active_servo_drag_joints.discard(int(motor_id))

    async def revo3_cancel_servo_drag(self, slave_id, motor_id):
        return await self.cancel_servo_drag(slave_id, motor_id)

    async def single_joint_control(self, slave_id, motor_id, mode, value):
        if int(mode) in (4, 5):
            await self.set_joint_mit(slave_id, motor_id, 0.0, 0.0, 0.0, value / 100.0, 0.0)
        else:
            await self.set_joint_position(slave_id, motor_id, value)

    async def multi_joint_control(self, slave_id, mode, values):
        if int(mode) in (4, 5):
            gains = [float(value) / 100.0 for value in values]
            await self.set_all_mit_params(slave_id, gains, [0.0] * 21, self._positions, [0.0] * 21, [0.0] * 21)
        else:
            await self.set_all_motor_positions(slave_id, values)

    async def finger_control(self, slave_id, finger, mode, values):
        start = (4 - int(finger)) * 4
        if int(mode) == 0:
            await self._refresh_control_state()
            self._positions[start : start + 4] = list(values)
            await self.set_all_motor_positions(slave_id, self._positions)
        else:
            for offset, value in enumerate(values):
                await self.single_joint_control(slave_id, start + offset, mode, value)

    async def thumb_control(self, slave_id, mode, values):
        if int(mode) == 0:
            await self._refresh_control_state()
            self._positions[16:21] = list(values)
            await self.set_all_motor_positions(slave_id, self._positions)
        else:
            for offset, value in enumerate(values):
                await self.single_joint_control(slave_id, 16 + offset, mode, value)

    async def servo_joint_with_gains(self, slave_id, joint, position, velocity, kp, kd):
        await self._refresh_control_state()
        self._positions[int(joint)] = float(position)
        self._velocities[int(joint)] = float(velocity)
        await (await self._servo_session()).send_impedance(
            self._positions, self._velocities, kp, kd
        )

    async def _wait_motion(self, handle, timeout):
        return await handle.wait(timeout=max(float(timeout), 0.1) + 5.0)

    async def move_joint_with_gains(self, _slave_id, joint, target, duration, dt, kp, kd):
        self._close_servo()
        return await self.hand.motion.move_joint(joint, target, duration=duration, kp=kp, kd=kd, dt=dt)

    async def move_joint_with_gains_wait(self, *args):
        handle = await self.move_joint_with_gains(*args)
        return await self._wait_motion(handle, args[3])

    async def move_joint_with_speed_and_gains(self, _slave_id, joint, target, speed, dt, kp, kd):
        self._close_servo()
        return await self.hand.motion.move_joint(joint, target, speed=speed, kp=kp, kd=kd, dt=dt)

    async def move_joint_with_speed_and_gains_wait(self, *args):
        handle = await self.move_joint_with_speed_and_gains(*args)
        return await self._wait_motion(handle, 10.0)

    async def move_hand_with_gains(self, _slave_id, targets, duration, dt, kp, kd):
        self._close_servo()
        return await self.hand.motion.move_to(targets, duration=duration, kp=kp, kd=kd, dt=dt)

    async def move_hand_with_gains_wait(self, *args):
        handle = await self.move_hand_with_gains(*args)
        return await self._wait_motion(handle, args[2])

    async def move_hand_with_speed_and_gains(self, _slave_id, targets, speed, dt, kp, kd):
        self._close_servo()
        return await self.hand.motion.move_to(targets, speed=speed, kp=kp, kd=kd, dt=dt)

    async def move_hand_with_speed_and_gains_wait(self, *args):
        handle = await self.move_hand_with_speed_and_gains(*args)
        return await self._wait_motion(handle, 10.0)

    async def move_hand_wait(self, slave_id, targets, duration, dt):
        return await self.move_hand_with_gains_wait(slave_id, targets, duration, dt, None, None)

    async def move_hand_with_speed_wait(self, _slave_id, targets, speed, dt):
        self._close_servo()
        handle = await self.hand.motion.move_to(targets, speed=speed, dt=dt)
        return await self._wait_motion(handle, 10.0)

    async def move_joint(self, _slave_id, joint, target, duration, dt):
        self._close_servo()
        return await self.hand.motion.move_joint(joint, target, duration=duration, dt=dt)

    async def move_joint_wait(self, *args):
        handle = await self.move_joint(*args)
        return await self._wait_motion(handle, args[3])

    async def move_joint_with_speed_wait(self, _slave_id, joint, target, speed, dt):
        self._close_servo()
        handle = await self.hand.motion.move_joint(joint, target, speed=speed, dt=dt)
        return await self._wait_motion(handle, 10.0)

    async def move_finger_wait(self, _slave_id, finger, targets, duration, dt):
        self._close_servo()
        handle = await self.hand.motion.move_finger(int(finger), targets, duration, dt=dt)
        return await self._wait_motion(handle, duration)

    async def move_finger_with_joint_gains_wait(
        self, _slave_id, finger, targets, duration, dt, kp, kd
    ):
        self._close_servo()
        handle = await self.hand.motion.move_finger(
            int(finger), targets, duration, kp=kp, kd=kd, dt=dt
        )
        return await self._wait_motion(handle, duration)

    async def move_thumb_wait(self, _slave_id, targets, duration, dt):
        self._close_servo()
        handle = await self.hand.motion.move_thumb(targets, duration, dt=dt)
        return await self._wait_motion(handle, duration)

    async def move_thumb_with_joint_gains_wait(
        self, _slave_id, targets, duration, dt, kp, kd
    ):
        self._close_servo()
        handle = await self.hand.motion.move_thumb(targets, duration, kp=kp, kd=kd, dt=dt)
        return await self._wait_motion(handle, duration)

    async def teach_joint(self, _slave_id, joint, dt, duration):
        self._close_servo()
        return await self.hand.motion.teach_joint(joint, duration, dt=dt)

    async def teach_hand(self, _slave_id, dt, duration):
        self._close_servo()
        return await self.hand.motion.teach_hand(duration, dt=dt)

    async def replay_joint(self, _slave_id, joint, positions, dt, kp, kd):
        return await self.hand.motion.replay_joint(joint, positions, dt=dt, kp=kp, kd=kd)

    async def replay_hand(self, _slave_id, trajectory, dt, kp, kd):
        return await self.hand.motion.replay_hand(trajectory, dt=dt, kp=kp, kd=kd)

    async def servo_hand(self, slave_id, positions, velocities):
        await (await self._servo_session()).send_impedance(positions, velocities, 1.0, 0.1)

    async def servo_hand_with_gains(self, slave_id, positions, velocities, kp, kd):
        await (await self._servo_session()).send_impedance(positions, velocities, kp, kd)

    async def set_servo_filter_mode(self, mode):
        self._servo_filter_mode = mode

    async def get_servo_filter_mode(self):
        return self._servo_filter_mode

    async def set_servo_damping_omega(self, omega):
        self._servo_damping_omega = float(omega)

    async def get_servo_damping_omega(self):
        return self._servo_damping_omega

    async def get_servo_lpf_alpha(self):
        return self._servo_lpf_alpha

    async def clear_motor_faults(self, _slave_id=None):
        return await self.hand.health.clear_motor_faults()

    async def get_all_collision_active(self, _slave_id=None):
        return await self.hand.experimental_collision.active_joints()

    async def is_collision_active(self, slave_id, joint):
        return bool((await self.get_all_collision_active(slave_id))[int(joint)])

    async def set_collision_protection_config(self, _slave_id, config):
        collision_config = sdk.ExperimentalCollisionConfig(
            enable=config["enable"],
            source=getattr(sdk.CollisionDetectionSource, config["source"]),
            position_error_threshold_deg=config["position_error_threshold_deg"],
            current_threshold_ma=config["current_threshold_ma"],
            debounce_time_ms=config["debounce_time_ms"],
            max_cached_status_age_ms=config["max_cached_status_age_ms"],
            strategy=getattr(
                sdk.CollisionProtectionStrategy, config["strategy"]
            ),
            auto_clear_time_ms=config["auto_clear_time_ms"],
        )
        return await self.hand.experimental_collision.configure(collision_config)

    async def reset_collision_state(self, _slave_id=None):
        return await self.hand.experimental_collision.reset()

    async def set_teaching_mode(self, _slave_id, enabled):
        self._close_servo()
        return await self.hand.motion.set_zero_force_enabled(bool(enabled))

    async def set_software_e_stop(self, _slave_id, enabled):
        self._close_servo()
        operation = (
            self.hand.motion.software_stop()
            if enabled
            else self.hand.motion.recover_software_stop()
        )
        return await operation

    async def manual_calibration(self, _slave_id=None):
        self._close_servo()
        return await self.hand.calibration.calibrate_joints()

    async def set_calibration_current(self, _slave_id, value):
        return await self.hand.calibration.set_current(value)

    async def reset_finger_defaults(self, _slave_id=None):
        return await self.hand.calibration.reset_finger_defaults()

    async def _config(self):
        return await self.hand.config.snapshot()

    async def get_config_snapshot(self, _slave_id=None):
        return await self._config()

    async def set_buzzer(self, _slave_id_or_enabled, enabled=None):
        if enabled is None:
            enabled = _slave_id_or_enabled
        return await self.hand.config.set_buzzer(bool(enabled))

    async def set_vibration(self, _slave_id_or_enabled, enabled=None):
        if enabled is None:
            enabled = _slave_id_or_enabled
        return await self.hand.config.set_vibration(bool(enabled))

    async def get_global_protect_current(self, _slave_id=None):
        return (await self._config()).global_protect_current_ma

    async def set_global_protect_current(self, _slave_id, value):
        return await self.hand.config.set_global_protect_current(value)

    async def get_all_joint_protect_currents(self, _slave_id=None):
        return list((await self._config()).joint_protect_current_ma)

    async def set_joint_protect_current(self, _slave_id, joint, value):
        return await self.hand.config.set_joint_protect_current(joint, value)

    async def get_all_joint_position_limits(self, _slave_id=None):
        cfg = await self._config()
        return list(zip(cfg.joint_min_position_deg, cfg.joint_max_position_deg))

    async def set_joint_position_limits(self, _slave_id, joint, minimum, maximum):
        return await self.hand.config.set_joint_position_limits(joint, minimum, maximum)

    async def get_all_joint_speed_limits(self, _slave_id=None):
        cfg = await self._config()
        return list(zip(cfg.joint_min_speed_rpm, cfg.joint_max_speed_rpm))

    async def set_joint_speed_limits(self, _slave_id, joint, minimum, maximum):
        return await self.hand.config.set_joint_speed_limits(joint, minimum, maximum)

    async def set_power_on_auto_calibration(self, _slave_id, enabled):
        return await self.hand.config.set_power_on_auto_calibration(enabled)

    async def get_power_on_auto_calibration(self, _slave_id=None):
        return (await self._config()).power_on_auto_calibration_enabled

    async def get_auto_clear_motor_faults(self, _slave_id=None):
        return (await self._config()).auto_clear_motor_faults_enabled

    async def set_auto_clear_motor_faults(self, _slave_id, enabled):
        return await self.hand.config.set_auto_clear_motor_faults(bool(enabled))

    async def get_max_continuous_current(self, _slave_id=None):
        return (await self._config()).max_continuous_current_ma

    async def set_max_continuous_current(self, _slave_id, value):
        return await self.hand.config.set_max_continuous_current(value)

    async def get_touch_screen(self, _slave_id=None):
        return (await self._config()).touch_screen_enabled

    async def get_use_broadcast_id(self, _slave_id=None):
        return (await self._config()).use_broadcast_id

    async def get_software_e_stop(self, _slave_id=None):
        return (await self._config()).software_stop_enabled

    async def get_zero_position(self, _slave_id=None):
        return await self.hand.calibration.zero_positions()

    async def set_touch_screen(self, _slave_id, enabled):
        return await self.hand.config.set_touch_screen(enabled)

    async def set_use_broadcast_id(self, _slave_id, enabled):
        return await self.hand.config.set_use_broadcast_id(enabled)

    async def get_rs485_baudrate(self, _slave_id=None):
        return (await self._config()).rs485_baudrate

    async def get_canfd_baudrate(self, _slave_id=None):
        return (await self._config()).canfd_baudrate

    async def set_rs485_baudrate(self, _slave_id, baudrate):
        baudrate = _to_sdk_enum("Rs485Baudrate", baudrate)
        return await self.hand.config.set_rs485_baudrate(baudrate)

    async def set_canfd_baudrate(self, _slave_id, baudrate):
        baudrate = _to_sdk_enum("CanFdBaudrate", baudrate)
        return await self.hand.config.set_canfd_baudrate(baudrate)

    async def get_touch_read_mode(self, _slave_id=None):
        if not _has_touch_layout_prefix(self.touch_layout, "mt_"):
            return None
        return await self.hand.touch.read_mode()

    async def set_touch_read_mode(self, _slave_id, mode):
        if not _has_touch_layout_prefix(self.touch_layout, "mt_"):
            return None
        mode = _to_sdk_enum(
            "TouchReadMode",
            mode,
            {0: "PointArray", 1: "LegacyForceSummary"},
        )
        return await self.hand.touch.set_read_mode(mode)

    async def get_all_touch_modules_enabled(self, _slave_id=None):
        return await self.hand.touch.enabled_mask()

    async def set_all_touch_modules_enabled(self, _slave_id, mask):
        return await self.hand.touch.set_enabled_mask(mask)

    async def set_touch_module_enabled(self, _slave_id, module, enabled):
        return await self.hand.touch.set_module_enabled(module, enabled)

    async def get_touch_module_enabled(self, _slave_id, module):
        return await self.hand.touch.module_enabled(module)

    async def get_all_touch_data(self, _slave_id=None):
        return self.touch_frame_payload(await self.hand.touch.snapshot())

    @staticmethod
    def touch_frame_payload(frame):
        modules = getattr(frame, "modules", None)
        if modules is not None:
            return GuiHandAdapter._touch_frame_payload_from_modules(modules)
        return SimpleNamespace(summary_values=[], modules=[], force_torque_modules=[])

    @staticmethod
    def _touch_frame_payload_from_modules(frame_modules):
        frame_modules = list(frame_modules or [])
        ft_modules_by_index = {}
        dense_modules = [[] for _ in range(11)]
        summary_values = []

        for module in sorted(frame_modules, key=lambda item: int(getattr(item, "module_id", 0))):
            module_id = int(getattr(module, "module_id", 0) or 0)
            layout_id = str(getattr(module, "layout_id", "") or "")
            points = list(getattr(module, "points", []) or [])
            regional_forces = list(getattr(module, "regional_forces_mn", []) or [])
            if not points and regional_forces:
                points = regional_forces
            if module_id >= len(dense_modules):
                dense_modules.extend([[] for _ in range(module_id + 1 - len(dense_modules))])
            dense_modules[module_id] = points

            force3d = getattr(module, "force3d", None)
            torque2d = getattr(module, "torque2d", None)
            resultant_force = getattr(module, "resultant_force_mn", None)
            is_hp_module = layout_id.startswith("hp_")
            if (
                is_hp_module
                or force3d is not None
                or torque2d is not None
                or resultant_force is not None
            ):
                resultant_force_mn = float(resultant_force or 0.0)
                region_index = int(getattr(module, "region_index", module_id) or 0)
                sample_state = getattr(module, "sample_state", None)
                ft_modules_by_index[module_id] = SimpleNamespace(
                    module_id=module_id,
                    region_index=region_index,
                    sample_state=sample_state,
                    status=int(getattr(module, "module_status", 0) or 0),
                    sensor_status=int(getattr(module, "sensor_status", 0) or 0),
                    fx=float(getattr(force3d, "x", 0.0) if force3d is not None else 0.0),
                    fy=float(getattr(force3d, "y", 0.0) if force3d is not None else 0.0),
                    fz=float(getattr(force3d, "z", 0.0) if force3d is not None else 0.0),
                    mx=float(getattr(torque2d, "x", 0.0) if torque2d is not None else 0.0),
                    my=float(getattr(torque2d, "y", 0.0) if torque2d is not None else 0.0),
                    resultant_force_mn=resultant_force_mn,
                    points=points,
                )

        ft_modules = [ft_modules_by_index[index] for index in sorted(ft_modules_by_index)]
        if any(getattr(m, "regional_forces_mn", None) for m in frame_modules):
            for module in sorted(frame_modules, key=lambda item: int(getattr(item, "module_id", 0))):
                regional_forces = getattr(module, "regional_forces_mn", None)
                if regional_forces:
                    summary_values.extend(regional_forces)
        elif ft_modules:
            summary_values = [module.resultant_force_mn for module in ft_modules]

        return SimpleNamespace(
            summary_values=summary_values,
            modules=dense_modules,
            force_torque_modules=ft_modules,
            module_objects=frame_modules,
        )

    async def calibrate_touch_zero(self, _slave_id=None):
        return await self.hand.touch.tare()

    async def calibrate_touch_zero_single(self, _slave_id, module):
        return await self.hand.touch.tare(module)

    async def get_touch_module_serial_numbers(self, _slave_id=None):
        info = await self.hand.refresh_device_info()
        return list(info.touch_serial_numbers) if info is not None else []

    async def get_touch_module_serial_number(self, slave_id, module):
        serial_numbers = await self.get_touch_module_serial_numbers(slave_id)
        if _has_touch_layout_prefix(self.touch_layout, "mx_"):
            mapped = map_touch_metadata_by_public_module_id(
                self.touch_layout, "mx_", serial_numbers, None
            )
            serial_number = mapped[int(module)]
            if serial_number is None:
                raise ValueError(f"module {module} is not an mx_* touch module")
            return serial_number
        return serial_numbers[int(module)]

    async def restart_touch_modules(self, _slave_id=None):
        return await self.hand.touch.restart()

    async def restart_touch_module(self, _slave_id, module):
        return await self.hand.touch.restart(module)

    async def get_touch_module_point_counts(self, _slave_id=None):
        return await self.hand.touch.point_counts()

    async def get_touch_value_mode(self, _slave_id=None):
        return await self.hand.touch.value_mode()

    async def get_touch_module_value_mode(self, _slave_id, module):
        return await self.hand.touch.value_mode(module)

    async def set_touch_value_mode(self, _slave_id, mode):
        mode = _to_sdk_enum(
            "TouchValueMode",
            mode,
            {0: "Adc", 2: "Force"},
        )
        return await self.hand.touch.set_value_mode(mode)

    async def set_touch_module_value_mode(self, _slave_id, module, mode):
        mode = _to_sdk_enum(
            "TouchValueMode",
            mode,
            {0: "Adc", 2: "Force"},
        )
        return await self.hand.touch.set_value_mode(mode, module)

    async def get_touch_tare_status(self, _slave_id=None):
        return await self.hand.touch.tare_status()

    async def get_touch_module_tare_status(self, _slave_id, module):
        return await self.hand.touch.tare_status(module)

    async def get_touch_module_tare_statuses(self, _slave_id=None):
        modules = list(getattr(self.touch_layout, "modules", []) or [])
        module_ids = [
            int(getattr(module, "module_id", 0) or 0)
            for module in modules
            if str(getattr(module, "layout_id", "")).startswith("mx_")
        ]
        if not modules:
            module_ids = list(range(11))

        statuses = [None] * 11
        for module_id in module_ids:
            if module_id >= len(statuses):
                statuses.extend([None] * (module_id + 1 - len(statuses)))
            statuses[module_id] = await self.hand.touch.tare_status(module_id)
        return statuses

    async def set_touch_tare(self, _slave_id, command):
        if int(command) == 1:
            return await self.hand.touch.tare()
        if int(command) == 2:
            return await self.hand.touch.cancel_tare()
        raise ValueError("tare command must be 1 or 2")

    async def set_touch_module_tare(self, _slave_id, module, command):
        if int(command) == 1:
            return await self.hand.touch.tare(module)
        if int(command) == 2:
            return await self.hand.touch.cancel_tare(module)
        raise ValueError("tare command must be 1 or 2")

    async def reboot(self, _slave_id=None):
        self._close_servo()
        handle = self.hand.maintenance.reboot()
        return await handle.wait(timeout=10.0)

    async def factory_reset(self, _slave_id=None):
        self._close_servo()
        return await self.hand.maintenance.factory_reset()

    async def start_dfu(self, slave_id, path, wait_secs=5, on_state=None, on_progress=None):
        self._close_servo()
        if on_state:
            on_state(slave_id, 1)
        handle = self.hand.maintenance.update_firmware(path, wait_secs=wait_secs)
        # DFU transfers the full firmware image and the device reboots
        # afterwards; this routinely takes several minutes.
        state = await handle.wait(timeout=max(600.0, float(wait_secs)))
        if on_progress:
            on_progress(slave_id, 1.0)
        if on_state:
            on_state(slave_id, 4 if state == sdk.OperationState.Succeeded else 5)
        return state

    async def _start_target_dfu(self, slave_id, path, target, wait_secs=5):
        target = _to_sdk_enum("FirmwareTarget", target, {0: "MainFirmware", 1: "Image", 2: "MotorFirmware"})
        handle = self.hand.maintenance.update_firmware(path, target=target, wait_secs=wait_secs)
        return await handle.wait(timeout=max(30.0, float(wait_secs)))

    async def start_mcu_dfu(self, slave_id, path, wait_secs=5, *_callbacks):
        return await self._start_target_dfu(slave_id, path, 0, wait_secs)

    async def start_image_dfu(self, slave_id, path, wait_secs=5, *_callbacks):
        return await self._start_target_dfu(slave_id, path, 1, wait_secs)

    async def start_motor_dfu(self, slave_id, path, wait_secs=5, *_callbacks):
        return await self._start_target_dfu(slave_id, path, 2, wait_secs)

    def get_protocol_type(self):
        return getattr(self.detected, "protocol_type", None)
