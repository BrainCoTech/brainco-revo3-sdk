"""Benchmark Revo3 2.x State/Touch subscriptions with optional Servo control."""

import argparse
import asyncio
import math
import os
import sys
import time
from dataclasses import dataclass

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from common_init import REVO3_ULTRA_JOINT_COUNT, close_revo3, connect_revo3, logger


@dataclass
class Stats:
    loops: int = 0
    state_reads: int = 0
    touch_reads: int = 0
    control_writes: int = 0
    errors: int = 0
    id_order_errors: int = 0
    deadline_misses: int = 0
    latency_sum_ms: float = 0.0


async def run(args):
    manager = None
    hand = None
    state_sub = None
    touch_sub = None
    servo = None
    stats = Stats()
    try:
        manager, hand = await connect_revo3(args.port, args.baudrate, args.slave_id)
        if not 0 <= args.motor < hand.joint_layout.joint_count:
            raise ValueError("motor index is outside the connected joint layout")

        period = 1.0 / args.rate if args.rate > 0.0 else args.period
        state_sub = hand.state.subscribe(period=period)
        needs_touch = args.scenario in ("motor-touch", "closed-loop")
        if needs_touch:
            if hand.touch.layout is None:
                raise RuntimeError("connected hand does not support Touch")
            touch_sub = hand.touch.subscribe(period=period)

        base = list((await hand.state.snapshot()).positions)
        if args.scenario == "closed-loop":
            servo = hand.motion.open_servo(
                command_timeout_ms=args.command_timeout_ms
            )

        started = time.perf_counter()
        last_report = started
        next_tick = started
        target_interval = 1.0 / args.rate if args.rate > 0.0 else None

        while time.perf_counter() - started < args.duration:
            loop_started = time.perf_counter()
            try:
                if servo is not None:
                    phase = 2.0 * math.pi * args.sine_hz * (loop_started - started)
                    target = list(base)
                    target[args.motor] += args.amplitude * math.sin(phase)
                    await servo.send_position(target)
                    stats.control_writes += 1

                state = await state_sub.next()
                stats.state_reads += 1
                if touch_sub is not None:
                    await touch_sub.next()
                    stats.touch_reads += 1

                stats.loops += 1
                stats.latency_sum_ms += (time.perf_counter() - loop_started) * 1000.0

                if target_interval is not None:
                    next_tick += target_interval
                    now = time.perf_counter()
                    if now > next_tick:
                        stats.deadline_misses += 1
                    else:
                        await asyncio.sleep(next_tick - now)

                if time.perf_counter() - last_report >= 1.0:
                    elapsed = time.perf_counter() - started
                    logger.info(
                        "elapsed=%.1fs loops=%d state=%d touch=%d writes=%d errors=%d misses=%d J%d=%.2f",
                        elapsed,
                        stats.loops,
                        stats.state_reads,
                        stats.touch_reads,
                        stats.control_writes,
                        stats.errors,
                        stats.deadline_misses,
                        args.motor,
                        state.positions_deg[args.motor],
                    )
                    last_report = time.perf_counter()
            except Exception as error:
                stats.errors += 1
                err_msg = str(error).lower()
                if "slave_id" in err_msg or "id_order" in err_msg or "mismatch" in err_msg:
                    stats.id_order_errors += 1
                if stats.errors <= 3:
                    logger.warning("benchmark operation failed: %s", error)

        elapsed = time.perf_counter() - started
        logger.info(
            "summary duration=%.2fs loop_hz=%.1f state_hz=%.1f touch_hz=%.1f "
            "control_hz=%.1f avg_latency_ms=%.2f errors=%d id_order_errors=%d deadline_misses=%d",
            elapsed,
            stats.loops / elapsed,
            stats.state_reads / elapsed,
            stats.touch_reads / elapsed,
            stats.control_writes / elapsed,
            stats.latency_sum_ms / stats.loops if stats.loops else 0.0,
            stats.errors,
            stats.id_order_errors,
            stats.deadline_misses,
        )
    finally:
        if servo is not None:
            servo.close()
        if touch_sub is not None:
            touch_sub.close()
        if state_sub is not None:
            state_sub.close()
        await close_revo3(manager, hand)


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", choices=("motor", "motor-touch", "closed-loop"), default="motor")
    parser.add_argument("--duration", type=float, default=10.0)
    parser.add_argument("--period", type=float, default=0.02)
    parser.add_argument("--rate", type=float, default=0.0, help="target rate in Hz (overrides period if > 0)")
    parser.add_argument("--motor", type=int, default=3)
    parser.add_argument("--amplitude", type=float, default=3.0)
    parser.add_argument("--sine-hz", type=float, default=0.5)
    parser.add_argument("--command-timeout-ms", type=int, default=100)
    parser.add_argument("--port")
    parser.add_argument("--baudrate", type=int, default=5_000_000)
    parser.add_argument("--slave-id", type=lambda value: int(value, 0))
    args = parser.parse_args()
    if args.duration <= 0.0 or args.period <= 0.0:
        parser.error("duration and period must be positive")
    if not 0 <= args.motor < REVO3_ULTRA_JOINT_COUNT:
        parser.error("motor must be in [0, 20]")
    return args


if __name__ == "__main__":
    asyncio.run(run(parse_args()))
