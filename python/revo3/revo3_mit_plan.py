"""Run a repeating MIT quintic plan over Modbus or CANFD."""

import argparse
import asyncio
import math
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from revo3.mit_debug.trajectory import QuinticTrajectory
from revo3.revo3_utils import libstark, logger, open_revo3

MOTOR_COUNT = 21
DEG_PER_SECOND_PER_RPM = 6.0

FINGER_SPECS = (
    ("Pinky", (1,)),
    ("Ring", (5,)),
    ("Middle", (9,)),
    ("Index", (13,)),
    ("Thumb Rot", (16,)),
    ("Thumb Flex", (20,)),
)

FULL_HAND_JOINTS = (1, 5, 9, 13, 16, 20)
OBSERVED_JOINTS = (
    (1, "Pinky"),
    (5, "Ring"),
    (9, "Middle"),
    (13, "Index"),
    (16, "ThumbRot"),
    (20, "ThumbFlex"),
)


def observed_joint_summary(status) -> str:
    return " ".join(
        (
            f"J{joint}({name})={status.positions[joint]:.2f}deg/"
            f"{status.velocities[joint]:.2f}rpm/"
            f"{status.currents[joint]:.2f}mA/"
            f"0x{status.statuses[joint]:04X}"
        )
        for joint, name in OBSERVED_JOINTS
    )


async def clear_mit_gains(client, slave_id, joints) -> None:
    for joint in joints:
        try:
            await client.revo3_joint_mit_control(slave_id, joint, 0.0, 0.0, 0.0, 0.0, 0.0)
        except Exception:
            pass


async def run_plan_group(client, slave_id, group_name: str, joints: tuple, args: argparse.Namespace) -> bool:
    initial_status = await client.revo3_get_motor_status_data(slave_id)
    start_positions = [initial_status.positions[j] for j in joints]

    logger.info(
        "MIT quintic plan [%s] joints %s: target %.2f deg, %.2fs/segment, %d repeats, %d Hz",
        group_name,
        list(joints),
        args.target,
        args.duration,
        args.repeat,
        args.frequency,
    )

    period = 1.0 / args.frequency
    cycle = 0
    command_count = 0
    interrupted = False
    plan_start = time.perf_counter()
    last_print = plan_start - 1.0

    try:
        for repeat_index in range(args.repeat):
            for returning in (False, True):
                trajectories = []
                for start_pos, joint in zip(start_positions, joints):
                    joint_target = min(args.target, 50.0) if joint == 16 else args.target
                    if returning:
                        from_pos, to_pos = joint_target, start_pos
                    else:
                        from_pos, to_pos = start_pos, joint_target
                    trajectories.append(QuinticTrajectory(from_pos, to_pos, args.duration))

                segment_start = time.perf_counter()
                segment_cycle = 0
                while True:
                    elapsed = min(time.perf_counter() - segment_start, args.duration)

                    for i, joint in enumerate(joints):
                        pos, vel_deg_s = trajectories[i].get(elapsed)
                        vel_rpm = vel_deg_s / DEG_PER_SECOND_PER_RPM
                        await client.revo3_joint_mit_control(
                            slave_id,
                            joint,
                            args.kp,
                            args.kd,
                            pos,
                            vel_rpm,
                            0.0,
                        )
                        command_count += 1

                    status = await client.revo3_get_motor_status_data(slave_id)
                    now = time.perf_counter()
                    if now - last_print >= 1.0 or elapsed >= args.duration:
                        targets_summary = " ".join(
                            f"J{j}={trajectories[i].get(elapsed)[0]:.2f}deg/"
                            f"{(trajectories[i].get(elapsed)[1] / DEG_PER_SECOND_PER_RPM):.2f}rpm"
                            for i, j in enumerate(joints)
                        )
                        logger.info(
                            "cycle=%d phase=%s repeat=%d/%d group=[%s] targets=[%s] observed=%s",
                            cycle,
                            "return" if returning else "outbound",
                            repeat_index + 1,
                            args.repeat,
                            group_name,
                            targets_summary,
                            observed_joint_summary(status),
                        )
                        last_print = now

                    if elapsed >= args.duration:
                        break

                    cycle += 1
                    segment_cycle += 1
                    next_tick = segment_start + segment_cycle * period
                    await asyncio.sleep(max(0.0, next_tick - time.perf_counter()))
    except asyncio.CancelledError:
        interrupted = True

    await clear_mit_gains(client, slave_id, joints)

    if interrupted:
        logger.info("MIT plan interrupted by user during [%s]", group_name)
        return False

    elapsed_total = time.perf_counter() - plan_start
    actual_frequency = command_count / elapsed_total if elapsed_total > 0 else 0.0
    logger.info(
        "MIT plan [%s] rate: %.1f Hz actual, %d Hz requested (%d commands in %.2fs)",
        group_name,
        actual_frequency,
        args.frequency,
        command_count,
        elapsed_total,
    )
    if actual_frequency < args.frequency * 0.8:
        logger.warning(
            "Control loop missed requested rate during [%s]; consider using CANFD/EtherCAT or lower frequency",
            group_name,
        )
    return True


async def run(args: argparse.Namespace) -> None:
    client = None
    slave_id = None
    try:
        client, slave_id = await open_revo3(
            port_name=args.port,
            baudrate=args.baudrate,
            slave_id=args.slave_id,
        )

        if args.joint is not None:
            logger.info("Executing single joint J%d MIT plan", args.joint)
            await run_plan_group(client, slave_id, f"Joint {args.joint}", (args.joint,), args)
        else:
            logger.info("=== Phase 1: Full Hand Quintic MIT Plan ===")
            completed = await run_plan_group(client, slave_id, "Full Hand", FULL_HAND_JOINTS, args)
            if completed:
                logger.info("=== Phase 2: Sequential Individual Finger MIT Plans ===")
                for name, joints in FINGER_SPECS:
                    await asyncio.sleep(0.3)
                    ok = await run_plan_group(client, slave_id, name, joints, args)
                    if not ok:
                        break
    finally:
        if client is not None and slave_id is not None:
            await clear_mit_gains(client, slave_id, FULL_HAND_JOINTS)
            logger.info("MIT plan finished; all gains were cleared")
            try:
                await libstark.modbus_close(client)
            except Exception as error:
                logger.warning("Failed to close device context: %s", error)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a repeating MIT trajectory generated by a 5th-order quintic formula"
    )
    parser.add_argument("--port", help="Serial or CANFD adapter port")
    parser.add_argument("--baudrate", type=int, default=5_000_000)
    parser.add_argument("--slave-id", type=lambda value: int(value, 0))
    parser.add_argument("--joint", type=int, default=None, help="Optional joint ID 0..20")
    parser.add_argument("--target", type=float, default=80.0, help="Target position in degrees")
    parser.add_argument("--duration", type=float, default=0.8, help="Seconds per segment")
    parser.add_argument("--repeat", type=int, default=1, help="Outbound/return round trips")
    parser.add_argument("--frequency", type=int, default=100, help="Control frequency in Hz")
    parser.add_argument("--kp", type=float, default=3.0)
    parser.add_argument("--kd", type=float, default=0.3)
    args = parser.parse_args()
    if not (
        (args.joint is None or 0 <= args.joint < MOTOR_COUNT)
        and args.repeat > 0
        and 0 < args.frequency <= 10_000
        and math.isfinite(args.target)
        and math.isfinite(args.duration)
        and args.duration > 0.0
        and math.isfinite(args.kp)
        and 0.0 <= args.kp <= 10.0
        and math.isfinite(args.kd)
        and 0.0 <= args.kd <= 10.0
    ):
        parser.error("invalid MIT plan configuration")
    return args


if __name__ == "__main__":
    try:
        asyncio.run(run(parse_args()))
    except KeyboardInterrupt:
        logger.info("MIT plan interrupted by user")

