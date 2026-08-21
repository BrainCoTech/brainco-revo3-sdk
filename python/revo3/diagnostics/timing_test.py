"""Measure one-joint motion timing from a direct 2.x State subscription."""

import argparse
import asyncio
import os
import platform
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from common_init import REVO3_ULTRA_JOINT_COUNT, close_revo3, connect_revo3, logger

DEFAULT_MOTOR_ID = 3
DEFAULT_NUM_CYCLES = 5
DEFAULT_TIMEOUT = 2.0
DEFAULT_CLOSE_ANGLE = 90.0
THRESHOLD_RATIO = 0.90


async def measure_movement(sub, motor_id, target_angle, timeout):
    start_time = time.perf_counter()
    read_count = 0
    current = float("nan")
    while time.perf_counter() - start_time < timeout:
        state = await sub.next()
        read_count += 1
        current = state.positions_deg[motor_id]
        reached = (
            abs(current - target_angle) <= 5.0
            if abs(target_angle) < 1.0
            else abs(current) >= abs(target_angle) * THRESHOLD_RATIO
        )
        if reached:
            return time.perf_counter() - start_time, current, True, read_count
    return time.perf_counter() - start_time, current, False, read_count


async def command_and_measure(hand, sub, motor_id, target, timeout):
    motion = await hand.motion.move_joint(motor_id, target, duration=timeout, dt=0.01)
    result = await measure_movement(sub, motor_id, target, timeout)
    if not result[2]:
        motion.cancel()
    return result


async def run_timing_test(hand, motor_id, cycles, close_angle, timeout, state_hz):
    sub = hand.state.subscribe(period=1.0 / state_hz)
    close_times = []
    open_times = []
    total_reads = 0
    test_start = time.perf_counter()
    try:
        initial = await hand.motion.move_joint(motor_id, 0.0, duration=timeout, dt=0.01)
        await initial.wait(timeout=timeout + 1.0)

        for cycle in range(cycles):
            logger.info("Cycle %d/%d: close", cycle + 1, cycles)
            elapsed, position, reached, reads = await command_and_measure(
                hand, sub, motor_id, close_angle, timeout
            )
            close_times.append(elapsed)
            total_reads += reads
            logger.info("close reached=%s elapsed=%.3fs position=%.1f reads=%d", reached, elapsed, position, reads)

            logger.info("Cycle %d/%d: open", cycle + 1, cycles)
            elapsed, position, reached, reads = await command_and_measure(
                hand, sub, motor_id, 0.0, timeout
            )
            open_times.append(elapsed)
            total_reads += reads
            logger.info("open reached=%s elapsed=%.3fs position=%.1f reads=%d", reached, elapsed, position, reads)
    finally:
        sub.close()

    duration = time.perf_counter() - test_start
    actual_hz = total_reads / duration if duration else 0.0
    logger.info("State subscription target=%.1fHz actual=%.1fHz reads=%d", state_hz, actual_hz, total_reads)
    logger.info("Close average=%.3fs Open average=%.3fs", sum(close_times) / len(close_times), sum(open_times) / len(open_times))
    logger.info("Platform=%s", platform.system())


async def main(args):
    if not 0 <= args.motor < REVO3_ULTRA_JOINT_COUNT:
        raise ValueError(f"motor must be in [0, {REVO3_ULTRA_JOINT_COUNT - 1}]")
    manager = None
    hand = None
    try:
        manager, hand = await connect_revo3(args.port)
        await run_timing_test(
            hand, args.motor, args.cycles, args.angle, args.timeout, args.state_hz
        )
    finally:
        await close_revo3(manager, hand)


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", "-p")
    parser.add_argument("--motor", "-m", type=int, default=DEFAULT_MOTOR_ID)
    parser.add_argument("--cycles", "-c", type=int, default=DEFAULT_NUM_CYCLES)
    parser.add_argument("--angle", "-a", type=float, default=DEFAULT_CLOSE_ANGLE)
    parser.add_argument("--timeout", "-t", type=float, default=DEFAULT_TIMEOUT)
    parser.add_argument("--state-hz", type=float, default=200.0)
    return parser.parse_args()


if __name__ == "__main__":
    asyncio.run(main(parse_args()))
