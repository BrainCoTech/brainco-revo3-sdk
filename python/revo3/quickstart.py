"""Connect to one Revo3 hand through the object-oriented Manager API."""

import argparse
import asyncio

from bc_revo3_sdk import main_mod as sdk

REVO3_MOTOR_FAULT_MASK = (
    (1 << 0)
    | (1 << 1)
    | (1 << 2)
    | (1 << 3)
    | (1 << 4)
    | (1 << 8)
)


def enum_name(value) -> str:
    return str(value).rsplit(".", 1)[-1]


def parse_motor_fault_code(code: int) -> str:
    flags = []
    if code & (1 << 0): flags.append("OverCurrent")
    if code & (1 << 1): flags.append("OverVoltage")
    if code & (1 << 2): flags.append("UnderVoltage")
    if code & (1 << 3): flags.append("OverTemp")
    if code & (1 << 4): flags.append("CurrentSpike")
    if code & (1 << 8): flags.append("Stalled")
    return "|".join(flags) if flags else f"0x{code:04X}"


def active_motor_faults(fault_codes) -> dict[int, str]:
    return {
        idx: parse_motor_fault_code(code)
        for idx, code in enumerate(fault_codes)
        if code & REVO3_MOTOR_FAULT_MASK
    }


def motion_preflight_findings(health) -> list[str]:
    findings = []
    active_faults = active_motor_faults(health.motor_fault_codes)
    if active_faults:
        findings.append(f"motor_faults={active_faults}")
    if health.safety_state in (
        sdk.SafetyState.Faulted,
        sdk.SafetyState.RecoveryRequired,
    ):
        findings.append(f"safety={health.safety_state}")
    if health.system_state != 0:
        findings.append(f"system_state={health.system_state}")
    if health.error_code != 0:
        findings.append(f"error_code={health.error_code}")
    if health.faulted_motor_count != 0:
        findings.append(f"faulted_motor_count={health.faulted_motor_count}")
    return findings


def report_motion_preflight(health, strict: bool) -> None:
    findings = motion_preflight_findings(health)
    if not findings:
        return
    if strict:
        raise RuntimeError(
            "Refusing to move because strict Health preflight found: "
            + ", ".join(findings)
            + ". Resolve the device fault and re-run the read-only check first."
        )
    print(
        "Warning: Health/State preflight found "
        + ", ".join(findings)
        + "; continuing because --allow-unhealthy is set."
    )


async def run(args: argparse.Namespace) -> None:
    print(f"SDK version: {sdk.get_sdk_version()}")
    manager = sdk.Manager()
    hand = None
    try:
        hand = await manager.connect_auto(
            port=args.port,
            slave_id=args.slave_id,
        )

        device_info = hand.device_info
        firmware_info = hand.firmware_info
        layout = hand.joint_layout
        if layout is None:
            raise RuntimeError("Joint layout is unavailable; reconnect with an explicit model")

        sn = device_info.serial_number if device_info else "unknown"
        side = (
            device_info.hand_side.name
            if device_info and hasattr(device_info.hand_side, "name")
            else (str(device_info.hand_side).replace("HandSide.", "") if device_info else "unknown")
        )
        hw_ver = device_info.hardware_revision if device_info and device_info.hardware_revision else "unknown"
        fw_ver = firmware_info.controller_firmware_version or "unknown"
        slave_id = getattr(hand, "slave_id", args.slave_id if args.slave_id is not None else 1)

        print(f"Device: {sn} ({side})")
        model = enum_name(device_info.model) if device_info else "unknown"
        print(f"Slave ID: {slave_id}")
        print(f"Model: {model} | Hardware revision: {hw_ver} | Firmware: {fw_ver}")
        print(f"Layout: {layout.layout_id} ({layout.joint_count} DOF)")
        touch_layout = hand.touch.layout
        touch_status = (
            f"{len(touch_layout.modules)} modules"
            if touch_layout is not None
            else "not available"
        )
        print(f"Touch layout: {touch_status}")
        print()

        snapshot = await hand.state.snapshot()
        print(
            f"State timestamp: {snapshot.timestamp.sec}.{snapshot.timestamp.nsec:09d} "
            f"({snapshot.timestamp.clock})"
        )
        print(f"Positions ({len(snapshot.positions_deg)}): {[round(value, 2) for value in snapshot.positions_deg]}")

        health = await hand.health.snapshot()
        active_errors = active_motor_faults(health.motor_fault_codes)
        print(f"Motor faults: {active_errors or 'None'}")
        print(
            f"Health: safety={health.safety_state}, system_state={health.system_state}, "
            f"error_code={health.error_code}, faulted_motor_count={health.faulted_motor_count}"
        )

        if args.move or args.move_joint or args.move_finger or args.move_thumb:
            report_motion_preflight(
                health,
                strict=args.strict_health or not args.allow_unhealthy,
            )
            ultra_models = {
                hand_type
                for hand_type in (
                    getattr(sdk.Revo3Model, "Ultra", None),
                    getattr(sdk.Revo3Model, "UltraTouch", None),
                    getattr(sdk.Revo3Model, "UltraVisionTouch", None),
                )
                if hand_type is not None
            }
            is_ultra = (
                device_info is not None
                and device_info.model in ultra_models
                and layout.joint_count == 21
            )
            if not is_ultra:
                raise RuntimeError("Motion currently requires a 21-DOF Revo3 Ultra")
            if args.speed is not None and (args.move_finger or args.move_thumb):
                raise RuntimeError("--speed is supported by move_to and move_joint only")
            duration = args.duration
            if duration is None and args.speed is None:
                duration = 1.5
            if args.move_joint:
                motion = await hand.motion.move_joint(
                    args.joint_index,
                    args.angle,
                    duration=duration,
                    speed=args.speed,
                    kp=args.kp,
                    kd=args.kd,
                    dt=args.dt,
                )
            elif args.move_finger:
                motion = await hand.motion.flex_finger(
                    args.finger_index,
                    args.angle,
                    duration=duration,
                    kp=args.kp,
                    kd=args.kd,
                    dt=args.dt,
                )
            elif args.move_thumb:
                thumb_targets = list(snapshot.positions_deg[16:21])
                thumb_targets[1] = args.angle
                thumb_targets[2] = args.angle
                thumb_targets[4] = args.angle
                motion = await hand.motion.move_thumb(
                    thumb_targets,
                    duration=duration,
                    kp=args.kp,
                    kd=args.kd,
                    dt=args.dt,
                )
            else:
                flex_angle = args.angle if args.angle != 30.0 else 45.0
                print(f"Phase 1: Flexing fingers to {flex_angle:.1f}°...")
                targets = list(snapshot.positions_deg)  # degrees
                # Flex MCP (1, 5, 9, 13) and PIP (2, 6, 10, 14) joints for 4 fingers (Pinky..Index)
                for joint in (1, 2, 5, 6, 9, 10, 13, 14):
                    targets[joint] = flex_angle
                motion = await hand.motion.move_to(
                    targets,
                    duration=duration,
                    speed=args.speed,
                    kp=args.kp,
                    kd=args.kd,
                    dt=args.dt,
                )
                state = await motion.wait(timeout=args.timeout)
                print(f"Motion 1 (Flex): {state}")
                if state != sdk.OperationState.Succeeded:
                    if motion.error is not None:
                        raise motion.error
                    raise RuntimeError(f"Flexion motion ended in {state}")

                await asyncio.sleep(0.5)

                print("Phase 2: Returning fingers to their initial positions...")
                extend_targets = list(snapshot.positions_deg)
                motion2 = await hand.motion.move_to(
                    extend_targets,
                    duration=duration,
                    speed=args.speed,
                    kp=args.kp,
                    kd=args.kd,
                    dt=args.dt,
                )
                state2 = await motion2.wait(timeout=args.timeout)
                print(f"Motion 2 (Return): {state2}")
                if state2 != sdk.OperationState.Succeeded:
                    if motion2.error is not None:
                        raise motion2.error
                    raise RuntimeError(f"Extension motion ended in {state2}")
                return
            state = await motion.wait(timeout=args.timeout)
            print(f"Motion {motion.id}: {state}")
            if state != sdk.OperationState.Succeeded:
                if motion.error is not None:
                    raise motion.error
                raise RuntimeError(f"Motion ended in {state}")
    finally:
        if hand is not None:
            await hand.close()
        await manager.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Quickstart demo for Revo3 hand.")
    parser.add_argument("positional_port", nargs="?", help="Optional serial or CAN port (e.g. /dev/ttyUSB0)")
    parser.add_argument("--port", help="Serial or CAN port (e.g. /dev/ttyUSB0)")
    parser.add_argument("--slave-id", type=lambda value: int(value, 0))
    motion = parser.add_mutually_exclusive_group()
    motion.add_argument("--move", action="store_true", help="Move the whole hand")
    motion.add_argument("--move-joint", action="store_true")
    motion.add_argument("--move-finger", action="store_true")
    motion.add_argument("--move-thumb", action="store_true")
    parser.add_argument("--joint-index", type=int, default=0)
    parser.add_argument("--finger-index", type=int, choices=range(1, 5), default=1)
    parser.add_argument(
        "--angle", "--deg", "--flexion",
        dest="angle",
        type=float,
        default=30.0,
        help="Target angle in degrees (e.g. 20 for 20 deg flexion)"
    )
    timing = parser.add_mutually_exclusive_group()
    timing.add_argument("--duration", type=float)
    timing.add_argument("--speed", type=float, help="Whole-hand or joint speed in rpm")
    parser.add_argument("--kp", type=float)
    parser.add_argument("--kd", type=float)
    parser.add_argument("--dt", type=float, default=0.01)
    parser.add_argument("--timeout", type=float, default=5.0, help="Motion timeout in seconds")
    safety = parser.add_mutually_exclusive_group()
    safety.add_argument(
        "--strict-health",
        action="store_true",
        help="Refuse motion when State or Health reports any real fault (default)",
    )
    safety.add_argument(
        "--allow-unhealthy",
        action="store_true",
        help="Allow motion despite Health or State faults after independent verification",
    )
    args = parser.parse_args()
    if not args.port and args.positional_port:
        args.port = args.positional_port
    if (args.kp is None) != (args.kd is None):
        parser.error("--kp and --kd must be provided together")
    return args


if __name__ == "__main__":
    try:
        asyncio.run(run(parse_args()))
    except sdk.SdkError as error:
        print(
            "SDK error: "
            f"code={error.code}, "
            f"effect={error.operation_effect}, "
            f"recovery={error.recovery_requirement}, "
            f"retryable={error.retryable}, message={error.message}"
        )
        if error.operation_effect == sdk.OperationEffect.Indeterminate:
            print("Command result is unknown; read state before deciding whether to retry")
        raise SystemExit(1) from error
    except RuntimeError as error:
        print(f"Error: {error}")
        raise SystemExit(1) from error
