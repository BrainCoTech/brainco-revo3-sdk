"""Inspect configuration and optionally start calibration or maintenance operations."""

import argparse
import asyncio

from bc_revo3_sdk import main_mod as sdk


async def wait_for_operation(name: str, handle, timeout: float) -> None:
    state = await handle.wait(timeout=timeout)
    print(f"{name}: id={handle.id}, state={state}")
    if handle.error:
        error = handle.error
        print(
            f"{name} error: code={error.code}, "
            f"effect={error.operation_effect}, recovery={error.recovery_requirement}, "
            f"message={error.message}"
        )


async def run(args: argparse.Namespace) -> None:
    manager = sdk.Manager()
    hand = None
    try:
        hand = await manager.connect_auto(port=args.port, slave_id=args.slave_id)

        device_config = await hand.config.snapshot()
        runtime = hand.config.runtime_options
        statistics = hand.statistics
        print(
            "DeviceConfig: "
            f"slave_id={device_config.slave_id}, "
            f"rs485_baudrate={device_config.rs485_baudrate}, "
            f"canfd_baudrate={device_config.canfd_baudrate}, "
            f"buzzer_enabled={device_config.buzzer_enabled}, "
            f"vibration_enabled={device_config.vibration_enabled}, "
            f"touch_screen_enabled={device_config.touch_screen_enabled}, "
            f"teaching_mode_enabled={device_config.teaching_mode_enabled}, "
            f"software_stop_enabled={device_config.software_stop_enabled}, "
            f"use_broadcast_id={device_config.use_broadcast_id}, "
            "power_on_auto_calibration_enabled="
            f"{device_config.power_on_auto_calibration_enabled}, "
            f"auto_clear_motor_faults_enabled={device_config.auto_clear_motor_faults_enabled}, "
            f"max_continuous_current_ma={device_config.max_continuous_current_ma}, "
            f"global_protect_current_ma={device_config.global_protect_current_ma}"
        )
        print(f"Joint protect currents (mA): {device_config.joint_protect_current_ma}")
        print(f"Joint position minimums (deg): {device_config.joint_min_position_deg}")
        print(f"Joint position maximums (deg): {device_config.joint_max_position_deg}")
        print(f"Joint speed minimums (rpm): {device_config.joint_min_speed_rpm}")
        print(f"Joint speed maximums (rpm): {device_config.joint_max_speed_rpm}")
        print(
            "RuntimeOptions: "
            f"state_subscription_period_ms={runtime.state_subscription_period_ms}, "
            f"servo_command_timeout_ms={runtime.servo_command_timeout_ms}"
        )
        print(
            "RuntimeStatistics: "
            f"state_reads={statistics.state_reads}, "
            f"touch_reads={statistics.touch_reads}, "
            f"commands_sent={statistics.commands_sent}"
        )

        if args.calibrate:
            await hand.calibration.calibrate_joints()
            print("calibration command sent")
        if args.reboot:
            await wait_for_operation("reboot", hand.maintenance.reboot(), args.timeout)
    finally:
        if hand is not None:
            await hand.close()
        await manager.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port")
    parser.add_argument("--slave-id", type=lambda value: int(value, 0))
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--calibrate", action="store_true")
    parser.add_argument("--reboot", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    asyncio.run(run(parse_args()))
