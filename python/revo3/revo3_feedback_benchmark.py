"""
Revo3 feedback and closed-loop frequency benchmark.

Scenarios:
  motor        : motor feedback only
  motor-touch  : motor feedback plus touch feedback
  closed-loop  : control write plus motor and touch feedback

Read strategies:
  single-status : read public bulk status API and consume one motor value
  multi-status  : read status and error arrays
  all-positions : read all 21 positions
  split-state   : read positions, velocities, currents, and errors separately
  full-state    : read complete motor status data in one bulk API call
  touch-only    : read touch data only
"""

import argparse
import asyncio
import math
import os
import sys
import time
from dataclasses import dataclass

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from revo3.revo3_utils import REVO3_MOTOR_COUNT, libstark, logger, open_revo3


@dataclass
class Stats:
    loops: int = 0
    motor_reads: int = 0
    touch_reads: int = 0
    control_writes: int = 0
    errors: int = 0
    latency_sum_us: float = 0.0
    latency_min_us: float = 0.0
    latency_max_us: float = 0.0
    last_motor_sample: float = 0.0
    last_touch_sample: int = 0

    def record_loop(self, latency_us: float) -> None:
        self.loops += 1
        self.latency_sum_us += latency_us
        self.latency_min_us = latency_us if self.latency_min_us == 0 else min(self.latency_min_us, latency_us)
        self.latency_max_us = max(self.latency_max_us, latency_us)

    @property
    def avg_latency_ms(self) -> float:
        return self.latency_sum_us / self.loops / 1000.0 if self.loops else 0.0


async def main() -> None:
    args = parse_args()
    if args.motor < 0 or args.motor >= REVO3_MOTOR_COUNT:
        raise ValueError(f"motor must be 0..{REVO3_MOTOR_COUNT - 1}, got {args.motor}")

    client, slave_id = await open_revo3(args.port, args.baudrate, args.slave_id)
    needs_touch = args.scenario in ("motor-touch", "closed-loop") or args.read == "touch-only"
    if args.scenario == "motor" and args.read != "touch-only":
        await client.set_hardware_type(slave_id, libstark.StarkHardwareType.Revo3Ultra)
    else:
        await client.set_hardware_type(slave_id, libstark.StarkHardwareType.Revo3UltraTouch)

    device_info = None
    try:
        device_info = await client.revo3_get_device_info(slave_id)
    except Exception as exc:
        logger.warning(f"Device info query failed, continuing benchmark: {exc}")

    touch_vendor = None
    if needs_touch:
        try:
            touch_vendor = await client.revo3_get_touch_vendor(slave_id)
        except Exception as exc:
            logger.warning(f"Touch vendor query failed: {exc}")
        if touch_vendor_value(touch_vendor) == 0:
            await close_client(client)
            raise RuntimeError("UNSUPPORTED_FEATURE: Device does not support touch sensor (TouchVendor is Unknown).")

    if args.scenario == "closed-loop" and args.control == "none":
        args.control = "single-position"

    logger.info("=== Revo3 Feedback Benchmark ===")
    if device_info is not None:
        logger.info(
            "DEVICE_INFO: "
            f"sn={getattr(device_info, 'serial_number', '')}, "
            f"fw={getattr(device_info, 'firmware_version', '')}, "
            f"hw={getattr(device_info, 'hardware_version', '')}, "
            f"type={getattr(device_info, 'hardware_type', '')}, "
            f"touch_vendor={touch_vendor}"
        )
    else:
        logger.info(f"DEVICE_INFO: unavailable, touch_vendor={touch_vendor}")
    logger.info(f"scenario={args.scenario}")
    logger.info(f"read_strategy={args.read}")
    logger.info(f"control_strategy={args.control}")
    logger.info(f"duration={args.duration:.1f}s, motor_id={args.motor}")
    logger.info("Note: single-status uses the public bulk status API and consumes only one motor value.")

    base_positions = [0.0] * REVO3_MOTOR_COUNT
    if args.control != "none":
        try:
            base_positions = list(await client.revo3_get_all_motor_positions(slave_id))
        except Exception as exc:
            await close_client(client)
            raise RuntimeError(f"Failed to read base positions before control benchmark: {exc}") from exc

    total = Stats()
    interval = Stats()
    start = time.perf_counter()
    last_print = start

    try:
        while time.perf_counter() - start < args.duration:
            loop_start = time.perf_counter()
            phase = 2.0 * math.pi * args.sine_hz * (loop_start - start)

            try:
                await run_control(client, slave_id, args, base_positions, phase)
                if args.control != "none":
                    total.control_writes += 1
                    interval.control_writes += 1
            except Exception as exc:
                total.errors += 1
                interval.errors += 1
                if total.errors <= 3:
                    logger.warning(f"control error #{total.errors}: {exc}")

            try:
                await run_reads(client, slave_id, args, total, interval)
            except Exception as exc:
                total.errors += 1
                interval.errors += 1
                if total.errors <= 3:
                    logger.warning(f"read error #{total.errors}: {exc}")

            latency_us = (time.perf_counter() - loop_start) * 1_000_000.0
            total.record_loop(latency_us)
            interval.record_loop(latency_us)

            now = time.perf_counter()
            if now - last_print >= 1.0:
                print_interval(now - start, now - last_print, interval)
                interval = Stats()
                last_print = now
    finally:
        print_summary(time.perf_counter() - start, total)
        if args.control != "none":
            try:
                await client.revo3_set_all_motor_positions(slave_id, base_positions)
            except Exception:
                pass
        await close_client(client)


async def run_control(client, slave_id: int, args, base_positions: list[float], phase: float) -> None:
    target = base_positions[args.motor] + args.amplitude * math.sin(phase)
    if args.control == "none":
        return
    if args.control == "single-position":
        await client.revo3_set_motor_position(slave_id, args.motor, target)
    elif args.control == "all-positions":
        positions = list(base_positions)
        positions[args.motor] = target
        await client.revo3_set_all_motor_positions(slave_id, positions)
    elif args.control == "single-mit":
        await client.revo3_joint_mit_control(slave_id, args.motor, 1.0, 0.1, target, 0.0, 0.0)
    else:
        raise ValueError(f"unknown control strategy: {args.control}")


async def run_reads(client, slave_id: int, args, total: Stats, interval: Stats) -> None:
    if args.read != "touch-only":
        await read_motor(client, slave_id, args.read, args.motor, total)
        interval.motor_reads += 1

    needs_touch = args.scenario in ("motor-touch", "closed-loop") or args.read == "touch-only"
    if needs_touch:
        touch = await client.revo3_get_all_touch_data(slave_id)
        total.last_touch_sample = int(touch.summary[0]) if hasattr(touch, "summary") else 0
        total.touch_reads += 1
        interval.touch_reads += 1


async def read_motor(client, slave_id: int, strategy: str, motor_id: int, stats: Stats) -> None:
    if strategy == "single-status":
        statuses = await client.revo3_get_all_motor_status(slave_id)
        stats.last_motor_sample = float(statuses[motor_id])
    elif strategy == "multi-status":
        statuses = await client.revo3_get_all_motor_status(slave_id)
        errors = await client.revo3_get_all_motor_errors(slave_id)
        stats.last_motor_sample = float(statuses[motor_id] + errors[motor_id])
    elif strategy == "all-positions":
        positions = await client.revo3_get_all_motor_positions(slave_id)
        stats.last_motor_sample = float(positions[motor_id])
    elif strategy == "split-state":
        positions = await client.revo3_get_all_motor_positions(slave_id)
        velocities = await client.revo3_get_all_motor_velocities(slave_id)
        currents = await client.revo3_get_all_motor_currents(slave_id)
        errors = await client.revo3_get_all_motor_errors(slave_id)
        stats.last_motor_sample = float(
            positions[motor_id] + velocities[motor_id] + currents[motor_id] + errors[motor_id]
        )
    elif strategy == "full-state":
        status = await client.revo3_get_motor_status_data(slave_id)
        stats.last_motor_sample = float(status.positions[motor_id])
    elif strategy == "touch-only":
        return
    else:
        raise ValueError(f"unknown read strategy: {strategy}")

    stats.motor_reads += 1


def print_interval(elapsed: float, window: float, stats: Stats) -> None:
    logger.info(
        f"[{elapsed:5.1f}s] "
        f"loop={stats.loops / window:7.1f}Hz "
        f"motor={stats.motor_reads / window:7.1f}Hz "
        f"touch={stats.touch_reads / window:7.1f}Hz "
        f"control_cmd={stats.control_writes / window:7.1f}Hz "
        f"latency(avg/min/max)="
        f"{stats.avg_latency_ms:.2f}/{stats.latency_min_us / 1000.0:.2f}/{stats.latency_max_us / 1000.0:.2f}ms "
        f"errors={stats.errors} sample={stats.last_motor_sample:.2f} touch={stats.last_touch_sample}"
    )


def print_summary(duration: float, stats: Stats) -> None:
    logger.info("=== Summary ===")
    logger.info(f"duration={duration:.2f}s loops={stats.loops} errors={stats.errors}")
    logger.info(f"loop_hz={stats.loops / duration:.1f}")
    logger.info(f"motor_read_hz={stats.motor_reads / duration:.1f}")
    logger.info(f"touch_read_hz={stats.touch_reads / duration:.1f}")
    logger.info(f"control_cmd_hz={stats.control_writes / duration:.1f}")
    logger.info(
        f"latency_ms avg={stats.avg_latency_ms:.2f}, "
        f"min={stats.latency_min_us / 1000.0:.2f}, max={stats.latency_max_us / 1000.0:.2f}"
    )


def parse_args():
    parser = argparse.ArgumentParser(description="Revo3 feedback and closed-loop frequency benchmark")
    parser.add_argument("--scenario", choices=["motor", "motor-touch", "closed-loop"], default="motor")
    parser.add_argument(
        "--read",
        choices=["single-status", "multi-status", "all-positions", "split-state", "full-state", "touch-only"],
        default="full-state",
    )
    parser.add_argument(
        "--control",
        choices=["none", "single-position", "all-positions", "single-mit"],
        default="none",
    )
    parser.add_argument("--duration", type=float, default=10.0)
    parser.add_argument("--motor", type=int, default=3)
    parser.add_argument("--amplitude", type=float, default=3.0)
    parser.add_argument("--sine-hz", type=float, default=0.5)
    parser.add_argument("--port", type=str, default=None)
    parser.add_argument("--baudrate", type=int, default=5_000_000)
    parser.add_argument("--slave-id", type=int, default=None)
    args = parser.parse_args()
    if not math.isfinite(args.duration) or args.duration <= 0.0:
        parser.error(f"--duration must be a positive finite number, got {args.duration}")
    if not math.isfinite(args.amplitude) or args.amplitude < 0.0:
        parser.error(f"--amplitude must be a non-negative finite number, got {args.amplitude}")
    if not math.isfinite(args.sine_hz) or args.sine_hz < 0.0:
        parser.error(f"--sine-hz must be a non-negative finite number, got {args.sine_hz}")
    return args


async def close_client(client) -> None:
    try:
        if hasattr(libstark, "close_device_handler"):
            await libstark.close_device_handler(client)
        else:
            await libstark.modbus_close(client)
    except Exception:
        pass


def touch_vendor_value(vendor) -> int:
    if vendor is None:
        return 0
    raw = getattr(vendor, "value", vendor)
    try:
        return int(raw)
    except (TypeError, ValueError):
        text = str(vendor).lower()
        if "pressure" in text:
            return 1
        if "matrix" in text:
            return 2
        return 0


if __name__ == "__main__":
    asyncio.run(main())
