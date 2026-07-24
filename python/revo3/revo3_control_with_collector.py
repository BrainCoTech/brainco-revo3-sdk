"""Demonstrate Revo3 control while DataCollector publishes monitor samples.

This is intentionally not a ROS2 node, but it mirrors the recommended ROS2
shape:
- a monitoring path reads the latest DataCollector buffer sample and publishes it
- a control path sends commands through the normal SDK APIs
- collector frequency is reduced while high-rate control is active
"""

import argparse
import asyncio
import os
import sys
from contextlib import suppress

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from revo3.control_collector_policy import CollectorRates, observed_joint_summary
from revo3.revo3_utils import REVO3_MOTOR_COUNT, libstark, logger, open_revo3


async def publish_latest_state(motor_buffer, period_s: float, stop_event: asyncio.Event) -> None:
    """Publish-like loop: read the latest collector sample without blocking control."""
    sequence = 0
    while not stop_event.is_set():
        latest = motor_buffer.peek_latest()
        if latest is not None:
            logger.info("state_pub seq=%d observed=%s", sequence, observed_joint_summary(latest))
            sequence += 1
        await asyncio.sleep(period_s)


async def wait_for_collector_sample(motor_buffer, timeout_s: float):
    deadline = asyncio.get_running_loop().time() + timeout_s
    while asyncio.get_running_loop().time() < deadline:
        latest = motor_buffer.peek_latest()
        if latest is not None:
            return latest
        await asyncio.sleep(0.02)
    return None


async def run_control_window(client, collector, slave_id: int, args: argparse.Namespace) -> None:
    """Command-like path: lower collector load, control one joint, then restore monitoring."""
    logger.info(
        "control_start joint=%d target=%.2f idle_collector=%dHz control_collector=%dHz",
        args.joint,
        args.target,
        args.idle_collector_hz,
        args.control_collector_hz,
    )
    collector.update_motor_frequency(args.control_collector_hz)
    try:
        await client.revo3_start_servo_drag(
            slave_id,
            args.joint,
            0.0,
            args.kp,
            args.kd,
            args.vel_cap_rpm,
            args.interval_ms,
            args.idle_timeout_ms,
            0,
            35.0,
        )
        await asyncio.sleep(0.2)

        logger.info("control_update joint=%d target=%.2f", args.joint, args.target)
        client.revo3_update_servo_drag(slave_id, args.joint, args.target)
        await asyncio.sleep(args.hold_s)

        logger.info("control_update joint=%d target=0.00", args.joint)
        client.revo3_update_servo_drag(slave_id, args.joint, 0.0)
        await asyncio.sleep(args.hold_s)
    finally:
        with suppress(Exception):
            await client.revo3_stop_servo_drag(slave_id, args.joint, 0.0)
        collector.update_motor_frequency(args.idle_collector_hz)
        logger.info("control_done joint=%d collector_restored=%dHz", args.joint, args.idle_collector_hz)


async def run(args: argparse.Namespace) -> None:
    rates = CollectorRates(args.idle_collector_hz, args.control_collector_hz)
    client = None
    collector = None
    publisher_task = None
    stop_event = asyncio.Event()

    try:
        client, slave_id = await open_revo3(
            port_name=args.port,
            baudrate=args.baudrate,
            slave_id=args.slave_id,
        )

        motor_buffer = libstark.Revo3MotorStatusBuffer(max_size=args.buffer_size)
        collector = libstark.DataCollector.new_revo3_basic(
            ctx=client,
            motor_buffer=motor_buffer,
            slave_id=slave_id,
            motor_frequency=rates.idle_hz,
            enable_stats=args.stats,
        )
        collector.start()
        latest = await wait_for_collector_sample(motor_buffer, args.collector_timeout_s)
        if latest is None:
            logger.warning("DataCollector started but no sample arrived before control")
        else:
            logger.info("collector_ready observed=%s", observed_joint_summary(latest))

        publisher_task = asyncio.create_task(
            publish_latest_state(motor_buffer, 1.0 / args.publish_hz, stop_event)
        )
        await run_control_window(client, collector, slave_id, args)
        await asyncio.sleep(args.post_monitor_s)
    finally:
        stop_event.set()
        if publisher_task is not None:
            publisher_task.cancel()
            with suppress(asyncio.CancelledError):
                await publisher_task
        if collector is not None:
            collector.stop()
            collector.wait()
        if client is not None:
            with suppress(Exception):
                if hasattr(libstark, "close_device_handler"):
                    await libstark.close_device_handler(client)
                else:
                    await libstark.modbus_close(client)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a Revo3 control demo while DataCollector publishes monitor samples"
    )
    parser.add_argument("--port", help="Serial or CANFD adapter port")
    parser.add_argument("--baudrate", type=int, default=5_000_000)
    parser.add_argument("--slave-id", type=lambda value: int(value, 0))
    parser.add_argument("--joint", type=int, default=13)
    parser.add_argument("--target", type=float, default=35.0, help="Servo target position in deg")
    parser.add_argument("--kp", type=float, default=2.0)
    parser.add_argument("--kd", type=float, default=0.25)
    parser.add_argument("--vel-cap-rpm", type=float, default=50.0)
    parser.add_argument("--interval-ms", type=int, default=15)
    parser.add_argument("--idle-timeout-ms", type=int, default=300)
    parser.add_argument("--idle-collector-hz", type=int, default=60)
    parser.add_argument("--control-collector-hz", type=int, default=10)
    parser.add_argument("--publish-hz", type=float, default=5.0)
    parser.add_argument("--hold-s", type=float, default=1.5)
    parser.add_argument("--post-monitor-s", type=float, default=1.0)
    parser.add_argument("--collector-timeout-s", type=float, default=1.0)
    parser.add_argument("--buffer-size", type=int, default=1000)
    parser.add_argument("--stats", action="store_true", help="Enable DataCollector stats logs")
    args = parser.parse_args()

    if not (
        0 <= args.joint < REVO3_MOTOR_COUNT
        and args.publish_hz > 0.0
        and args.hold_s >= 0.0
        and args.post_monitor_s >= 0.0
        and args.collector_timeout_s >= 0.0
        and args.buffer_size > 0
        and args.interval_ms > 0
        and args.idle_timeout_ms > 0
        and 0.0 <= args.kp <= 10.0
        and 0.0 <= args.kd <= 10.0
    ):
        parser.error("invalid control with collector configuration")

    try:
        CollectorRates(args.idle_collector_hz, args.control_collector_hz)
    except ValueError as error:
        parser.error(str(error))
    return args


if __name__ == "__main__":
    try:
        asyncio.run(run(parse_args()))
    except KeyboardInterrupt:
        logger.info("Control with collector demo interrupted by user")
