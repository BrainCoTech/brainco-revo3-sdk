"""Run a quintic MIT plan through the Revo3 2.0 Manager API."""

import argparse
import asyncio
import math
import time

from bc_revo3_sdk import main_mod as sdk

MOTOR_COUNT = 21
DEG_PER_SECOND_PER_RPM = 6.0
FULL_HAND_JOINTS = (1, 5, 9, 13, 16, 20)
MIN_RANGE_FRACTION = 0.05
MAX_RANGE_FRACTION = 0.95
QUINTIC_PEAK_RATE_FACTOR = 1.875


def quintic_sample(start: float, target: float, duration: float, elapsed: float) -> tuple[float, float]:
    ratio = min(max(elapsed / duration, 0.0), 1.0)
    blend = 10.0 * ratio**3 - 15.0 * ratio**4 + 6.0 * ratio**5
    blend_rate = (30.0 * ratio**2 - 60.0 * ratio**3 + 30.0 * ratio**4) / duration
    distance = target - start
    return start + distance * blend, distance * blend_rate / DEG_PER_SECOND_PER_RPM


async def send_zero_gains(session, positions: list[float]) -> None:
    zeros = [0.0] * len(positions)
    await session.send_mit(positions, zeros, zeros, zeros, zeros)


async def run_segment(
    hand,
    session,
    start_positions: list[float],
    target_positions: list[float],
    args: argparse.Namespace,
) -> int:
    period = 1.0 / args.frequency
    started_at = time.perf_counter()
    cycle = 0
    while True:
        elapsed = min(time.perf_counter() - started_at, args.duration)
        positions = start_positions.copy()
        velocities = [0.0] * MOTOR_COUNT
        for joint in args.joints:
            positions[joint], velocities[joint] = quintic_sample(
                start_positions[joint], target_positions[joint], args.duration, elapsed
            )

        kp = [args.kp] * MOTOR_COUNT
        kd = [args.kd] * MOTOR_COUNT
        feedforward_current_ma = [0.0] * MOTOR_COUNT
        await session.send_mit(positions, velocities, kp, kd, feedforward_current_ma)
        cycle += 1

        if cycle % max(args.frequency, 1) == 0 or elapsed >= args.duration:
            state = await hand.state.snapshot()
            observed = " ".join(
                f"J{joint}={state.positions_deg[joint]:.2f} degree"
                for joint in args.joints
            )
            print(f"cycle={cycle} {observed}")
        if elapsed >= args.duration:
            return cycle

        next_tick = started_at + cycle * period
        await asyncio.sleep(max(0.0, next_tick - time.perf_counter()))


async def run(args: argparse.Namespace) -> None:
    manager = sdk.Manager()
    hand = None
    session = None
    last_positions = [0.0] * MOTOR_COUNT
    try:
        hand = await manager.connect_auto(port=args.port, slave_id=args.slave_id)
        if hand.joint_layout is None or hand.joint_layout.joint_count != MOTOR_COUNT:
            raise RuntimeError("This example requires a 21-joint Revo3 hand")

        snapshot = await hand.state.snapshot()
        config = await hand.config.snapshot()
        initial_positions = list(snapshot.positions_deg)
        last_positions = initial_positions.copy()
        target_positions = initial_positions.copy()
        for joint in args.joints:
            minimum = config.joint_min_position_deg[joint]
            maximum = config.joint_max_position_deg[joint]
            if not (math.isfinite(minimum) and math.isfinite(maximum) and minimum < maximum):
                raise RuntimeError(f"Invalid configured position limits for joint {joint}")
            if not minimum <= initial_positions[joint] <= maximum:
                raise RuntimeError(
                    f"Initial feedback for joint {joint} is outside the configured position range"
                )
            target_positions[joint] = minimum + args.range_fraction * (maximum - minimum)
            distance = target_positions[joint] - initial_positions[joint]
            minimum_speed = config.joint_min_speed_rpm[joint]
            maximum_speed = config.joint_max_speed_rpm[joint]
            allowed_speed = (
                maximum_speed
                if distance >= 0.0 or minimum_speed >= 0.0
                else abs(minimum_speed)
            )
            peak_speed = (
                QUINTIC_PEAK_RATE_FACTOR
                * abs(distance)
                / args.duration
                / DEG_PER_SECOND_PER_RPM
            )
            if not (math.isfinite(allowed_speed) and allowed_speed > 0.0):
                raise RuntimeError(f"Invalid configured speed limit for joint {joint}")
            if peak_speed > allowed_speed:
                minimum_duration = (
                    QUINTIC_PEAK_RATE_FACTOR
                    * abs(distance)
                    / allowed_speed
                    / DEG_PER_SECOND_PER_RPM
                )
                raise RuntimeError(
                    f"Joint {joint} requires duration >= {minimum_duration:.3f}s "
                    f"for the configured {allowed_speed:.2f} rpm speed limit"
                )
            print(
                f"J{joint}: initial={initial_positions[joint]:.2f} degree, "
                f"target={target_positions[joint]:.2f} degree, "
                f"peak_velocity={peak_speed:.2f}/{allowed_speed:.2f} rpm"
            )

        session = hand.motion.open_servo(command_timeout_ms=args.command_timeout_ms)
        started_at = time.perf_counter()
        command_count = 0
        for _ in range(args.repeat):
            command_count += await run_segment(
                hand, session, initial_positions, target_positions, args
            )
            last_positions = target_positions.copy()
            command_count += await run_segment(
                hand, session, target_positions, initial_positions, args
            )
            last_positions = initial_positions.copy()

        elapsed = time.perf_counter() - started_at
        print(
            f"MIT rate: {command_count / elapsed:.1f} Hz actual, "
            f"{args.frequency} Hz requested"
        )
    finally:
        if session is not None:
            try:
                await send_zero_gains(session, last_positions)
            except Exception as error:
                print(f"Failed to clear MIT gains: {error}")
            finally:
                session.close()
        if hand is not None:
            await hand.close()
        await manager.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a repeating 2.0 MIT trajectory")
    parser.add_argument("--port")
    parser.add_argument("--slave-id", type=lambda value: int(value, 0))
    parser.add_argument("--joint", type=int, help="Control one joint instead of the example group")
    parser.add_argument(
        "--range-fraction",
        type=float,
        default=0.5,
        help="Target fraction within the configured position range (0.05 to 0.95)",
    )
    parser.add_argument("--duration", type=float, default=0.8, help="Seconds per segment")
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--frequency", type=int, default=100)
    parser.add_argument("--command-timeout-ms", type=int, default=100)
    parser.add_argument("--kp", type=float, default=3.0)
    parser.add_argument("--kd", type=float, default=0.3)
    parser.add_argument("--run", action="store_true")
    args = parser.parse_args()
    args.joints = (args.joint,) if args.joint is not None else FULL_HAND_JOINTS
    if not args.run:
        parser.error("Pass --run after checking the work area and independent stop path")
    if not (
        (args.slave_id is None or 0 <= args.slave_id <= 247)
        and all(0 <= joint < MOTOR_COUNT for joint in args.joints)
        and args.repeat > 0
        and 0 < args.frequency <= 10_000
        and args.command_timeout_ms >= math.ceil(1000.0 / args.frequency)
        and math.isfinite(args.range_fraction)
        and MIN_RANGE_FRACTION <= args.range_fraction <= MAX_RANGE_FRACTION
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
    except sdk.SdkError as error:
        print(
            f"SDK error: code={error.code}, "
            f"effect={error.operation_effect}, message={error.message}"
        )
        if error.operation_effect == sdk.OperationEffect.Indeterminate:
            print("Command result is unknown; read state before deciding whether to retry")
        raise SystemExit(1) from error
    except (RuntimeError, ValueError) as error:
        print(f"Error: {error}")
        raise SystemExit(1) from error
