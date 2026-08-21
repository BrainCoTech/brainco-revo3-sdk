"""Exercise one Revo3 2.0 public operation against real hardware."""

import argparse
import asyncio

from bc_revo3_sdk import main_mod as sdk


READ_ONLY_OPERATIONS = {
    "config-snapshot",
    "health-snapshot",
    "health-motor-status",
    "health-subscription",
    "touch-value-mode",
    "refresh-device-info",
    "refresh-firmware-info",
    "touch-config",
    "touch-module-enabled",
    "touch-point-counts",
    "touch-tare-status",
    "zero-positions",
}

OPERATIONS = sorted(
    READ_ONLY_OPERATIONS
    | {
        "abort-firmware-update",
        "calibrate",
        "clear-motor-faults",
        "factory-reset",
        "touch-restart",
        "touch-tare",
        "recover-software-stop",
        "replay-joint",
        "reset-finger-defaults",
        "reset-firmware-update-state",
        "servo-current",
        "servo-drag-cancel",
        "servo-drag-stop",
        "servo-impedance",
        "servo-mit",
        "servo-position",
        "servo-velocity",
        "set-power-on-auto-calibration",
        "set-auto-clear-motor-faults",
        "set-buzzer",
        "set-calibration-current",
        "set-canfd-baudrate",
        "set-current-position-as-zero",
        "set-global-protect-current",
        "set-joint-position-limits",
        "set-joint-protect-current",
        "set-joint-speed-limits",
        "set-max-continuous-current",
        "set-rs485-baudrate",
        "set-runtime-options",
        "set-touch-read-mode",
        "set-touch-enabled-mask",
        "set-touch-layout",
        "set-touch-module-enabled",
        "set-touch-screen",
        "set-touch-value-mode",
        "set-use-broadcast-id",
        "set-vibration",
        "set-zero-positions",
        "software-stop",
        "software-stop-cycle",
        "teach-joint",
        "touch-cancel-tare",
    }
)


async def wait_operation(name: str, handle, timeout: float) -> None:
    state = await handle.wait(timeout=timeout)
    print(f"{name}: id={handle.id}, state={state}")
    if handle.error is not None:
        raise handle.error
    if state != sdk.OperationState.Succeeded:
        raise RuntimeError(f"{name} did not succeed: {state}")


def require_layout(hand) -> int:
    layout = hand.joint_layout
    if layout is None:
        raise RuntimeError("Joint layout is unavailable")
    return layout.joint_count


def rs485_baudrate(value: int):
    mapping = {
        1_000_000: sdk.Rs485Baudrate.Baud1Mbps,
        2_000_000: sdk.Rs485Baudrate.Baud2Mbps,
        3_000_000: sdk.Rs485Baudrate.Baud3Mbps,
        5_000_000: sdk.Rs485Baudrate.Baud5Mbps,
    }
    try:
        return mapping[value]
    except KeyError as error:
        raise ValueError(f"Unsupported RS485 baudrate: {value}") from error


def canfd_baudrate(value: int):
    mapping = {
        1_000_000: sdk.CanFdBaudrate.Baud1Mbps,
        2_000_000: sdk.CanFdBaudrate.Baud2Mbps,
        4_000_000: sdk.CanFdBaudrate.Baud4Mbps,
        5_000_000: sdk.CanFdBaudrate.Baud5Mbps,
    }
    try:
        return mapping[value]
    except KeyError as error:
        raise ValueError(f"Unsupported CANFD baudrate: {value}") from error


async def exercise_servo(hand, operation: str, args: argparse.Namespace) -> None:
    state = await hand.state.snapshot()
    positions = list(state.positions_deg)
    zeros = [0.0] * len(positions)
    session = hand.motion.open_servo(command_timeout_ms=args.command_timeout_ms or 100)
    try:
        if operation == "servo-position":
            await session.send_position(positions)
        elif operation == "servo-velocity":
            await session.send_velocity(zeros)
        elif operation == "servo-current":
            await session.send_current(zeros)
        elif operation == "servo-impedance":
            await session.send_impedance(positions, zeros, args.kp, args.kd)
        elif operation == "servo-mit":
            gains_kp = [args.kp] * len(positions)
            gains_kd = [args.kd] * len(positions)
            await session.send_mit(positions, zeros, gains_kp, gains_kd, zeros)
        else:
            raise ValueError(f"Unsupported Servo operation: {operation}")
        print(f"{operation}: session_state={session.state}")
    finally:
        session.close()


async def exercise_config(hand, operation: str, args: argparse.Namespace) -> None:
    config = await hand.config.snapshot()
    if operation == "config-snapshot":
        print(config)
    elif operation == "set-runtime-options":
        current = hand.config.runtime_options
        options = sdk.RuntimeOptions(
            state_subscription_period_ms=(
                args.subscription_period_ms or current.state_subscription_period_ms
            ),
            servo_command_timeout_ms=(
                args.command_timeout_ms or current.servo_command_timeout_ms
            ),
        )
        hand.config.set_runtime_options(options)
    elif operation == "set-buzzer":
        await hand.config.set_buzzer(config.buzzer_enabled)
    elif operation == "set-vibration":
        await hand.config.set_vibration(config.vibration_enabled)
    elif operation == "set-touch-screen":
        await hand.config.set_touch_screen(config.touch_screen_enabled)
    elif operation == "set-use-broadcast-id":
        await hand.config.set_use_broadcast_id(config.use_broadcast_id)
    elif operation == "set-power-on-auto-calibration":
        await hand.config.set_power_on_auto_calibration(
            config.power_on_auto_calibration_enabled
        )
    elif operation == "set-auto-clear-motor-faults":
        await hand.config.set_auto_clear_motor_faults(config.auto_clear_motor_faults_enabled)
    elif operation == "set-max-continuous-current":
        await hand.config.set_max_continuous_current(config.max_continuous_current_ma)
    elif operation == "set-global-protect-current":
        await hand.config.set_global_protect_current(config.global_protect_current_ma)
    elif operation == "set-joint-protect-current":
        await hand.config.set_joint_protect_current(
            args.joint, config.joint_protect_current_ma[args.joint]
        )
    elif operation == "set-joint-position-limits":
        await hand.config.set_joint_position_limits(
            args.joint,
            config.joint_min_position_deg[args.joint],
            config.joint_max_position_deg[args.joint],
        )
    elif operation == "set-joint-speed-limits":
        await hand.config.set_joint_speed_limits(
            args.joint,
            config.joint_min_speed_rpm[args.joint],
            config.joint_max_speed_rpm[args.joint],
        )
    elif operation == "set-rs485-baudrate":
        await hand.config.set_rs485_baudrate(rs485_baudrate(config.rs485_baudrate))
    elif operation == "set-canfd-baudrate":
        await hand.config.set_canfd_baudrate(canfd_baudrate(config.canfd_baudrate))
    else:
        raise ValueError(f"Unsupported Config operation: {operation}")
    print(f"{operation}: completed")


async def exercise_touch(hand, operation: str, args: argparse.Namespace) -> None:
    touch = hand.touch
    if operation == "touch-config":
        print(
            f"enabled_mask=0x{await touch.enabled_mask():04x}, "
            f"read_mode={await touch.read_mode()}, "
            f"value_mode={await touch.value_mode()}"
        )
    elif operation == "touch-module-enabled":
        print(await touch.module_enabled(args.module))
    elif operation == "touch-tare-status":
        print(await touch.tare_status(args.module))
    elif operation == "touch-point-counts":
        print(await touch.point_counts())
    elif operation == "set-touch-enabled-mask":
        await touch.set_enabled_mask(await touch.enabled_mask())
    elif operation == "set-touch-layout":
        layout = touch.layout
        if layout is None:
            raise RuntimeError("Touch layout is unavailable")
        await touch.set_layout(layout)
    elif operation == "set-touch-module-enabled":
        enabled = await touch.module_enabled(args.module)
        await touch.set_module_enabled(args.module, enabled)
    elif operation == "set-touch-read-mode":
        await touch.set_read_mode(await touch.read_mode())
    elif operation == "set-touch-value-mode":
        await touch.set_value_mode(await touch.value_mode(args.module), args.module)
    elif operation == "touch-value-mode":
        print(await touch.value_mode(args.module))
    elif operation == "touch-tare":
        await touch.tare(args.module)
    elif operation == "touch-cancel-tare":
        await touch.cancel_tare(args.module)
    elif operation == "touch-restart":
        await touch.restart(args.module)
    else:
        raise ValueError(f"Unsupported Touch operation: {operation}")
    print(f"{operation}: completed")


async def exercise(hand, args: argparse.Namespace) -> None:
    operation = args.operation
    if operation.startswith("servo-") and operation not in {
        "servo-drag-cancel",
        "servo-drag-stop",
    }:
        await exercise_servo(hand, operation, args)
        return
    if operation == "config-snapshot" or operation.startswith("set-") and operation in {
        "set-runtime-options",
        "set-buzzer",
        "set-vibration",
        "set-touch-screen",
        "set-use-broadcast-id",
        "set-power-on-auto-calibration",
        "set-auto-clear-motor-faults",
        "set-max-continuous-current",
        "set-global-protect-current",
        "set-joint-protect-current",
        "set-joint-position-limits",
        "set-joint-speed-limits",
        "set-rs485-baudrate",
        "set-canfd-baudrate",
    }:
        await exercise_config(hand, operation, args)
        return
    if operation.startswith("touch-") or operation.startswith("set-touch-"):
        await exercise_touch(hand, operation, args)
        return

    if operation == "refresh-device-info":
        print(await hand.refresh_device_info())
    elif operation == "refresh-firmware-info":
        print(await hand.refresh_firmware_info())
    elif operation == "health-snapshot":
        print(await hand.health.snapshot())
    elif operation == "health-motor-status":
        temperatures = await hand.health.motor_module_temperatures_c()
        online_mask = await hand.health.motor_online_mask()
        print(f"motor_module_temperatures_c={temperatures}, online_mask=0x{online_mask:08x}")
    elif operation == "health-subscription":
        subscription = hand.health.subscribe(period=args.period)
        try:
            print(
                await asyncio.wait_for(subscription.next(), timeout=args.timeout)
            )
        finally:
            subscription.close()
    elif operation == "clear-motor-faults":
        await hand.health.clear_motor_faults()
    elif operation == "zero-positions":
        print(await hand.calibration.zero_positions())
    elif operation == "set-zero-positions":
        await hand.calibration.set_zero_positions(await hand.calibration.zero_positions())
    elif operation == "calibrate":
        await hand.calibration.calibrate_joints()
    elif operation == "set-calibration-current":
        await hand.calibration.set_current(args.value)
    elif operation == "set-current-position-as-zero":
        await hand.calibration.set_current_position_as_zero()
    elif operation == "reset-finger-defaults":
        await hand.calibration.reset_finger_defaults()
    elif operation == "abort-firmware-update":
        await hand.maintenance.abort_firmware_update()
    elif operation == "reset-firmware-update-state":
        await hand.maintenance.reset_firmware_update_state()
    elif operation == "factory-reset":
        await hand.maintenance.factory_reset()
    elif operation == "software-stop":
        await hand.motion.software_stop()
    elif operation == "recover-software-stop":
        await hand.motion.recover_software_stop()
    elif operation == "software-stop-cycle":
        await hand.motion.software_stop()
        await hand.motion.recover_software_stop()
    elif operation == "teach-joint":
        positions = await hand.motion.teach_joint(
            args.joint, duration=args.duration, dt=args.period
        )
        print(f"teach-joint: samples={len(positions)}")
    elif operation == "replay-joint":
        position = (await hand.state.snapshot()).positions[args.joint]
        await hand.motion.replay_joint(
            args.joint, [position, position], dt=args.period, kp=args.kp, kd=args.kd
        )
    elif operation in {"servo-drag-cancel", "servo-drag-stop"}:
        position = (await hand.state.snapshot()).positions[args.joint]
        await hand.motion.start_servo_drag(
            args.joint,
            position,
            kp=args.kp,
            kd=args.kd,
            filter_mode=sdk.ServoFilterMode.Disabled,
        )
        hand.motion.update_servo_drag(args.joint, position)
        if operation == "servo-drag-cancel":
            await hand.motion.cancel_servo_drag(args.joint)
        else:
            await hand.motion.stop_servo_drag(args.joint, position)
    else:
        raise ValueError(f"Unsupported operation: {operation}")
    print(f"{operation}: completed")


async def run(args: argparse.Namespace) -> None:
    if args.operation not in READ_ONLY_OPERATIONS and not args.run:
        raise RuntimeError(
            "This operation can change device state. Pass --run after completing the "
            "required hardware risk review."
        )
    manager = sdk.Manager()
    hand = None
    try:
        hand = await manager.connect_auto(port=args.port, slave_id=args.slave_id)
        joint_count = require_layout(hand)
        if not 0 <= args.joint < joint_count:
            raise ValueError(f"joint must be in [0, {joint_count - 1}]")
        await exercise(hand, args)
    finally:
        if hand is not None:
            await hand.close()
        await manager.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("operation", choices=OPERATIONS)
    parser.add_argument("--port")
    parser.add_argument("--slave-id", type=lambda value: int(value, 0))
    parser.add_argument("--joint", type=int, default=0)
    parser.add_argument("--module", type=int, default=0)
    parser.add_argument("--duration", type=float, default=1.0)
    parser.add_argument("--period", type=float, default=0.02)
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--command-timeout-ms", type=int)
    parser.add_argument("--subscription-period-ms", type=int)
    parser.add_argument("--kp", type=float, default=1.0)
    parser.add_argument("--kd", type=float, default=0.1)
    parser.add_argument("--value", type=float, default=500.0)
    parser.add_argument("--run", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    asyncio.run(run(parse_args()))
