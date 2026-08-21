"""Compare slider-like OperationHandle and ServoSession control with State subscription feedback."""

import argparse
import asyncio
import os
import sys
import time
from contextlib import suppress

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from common_init import close_revo3, connect_revo3, logger

SCENARIOS = (
    ("Fast Slide", [0.0, 80.0], 0.12),
    ("Slow Slide", list(range(0, 81, 5)), 0.18),
    ("Slow Reciprocate", [0.0, 80.0, 0.0], 0.8),
    ("Fast Reciprocate", [0.0, 80.0, 0.0, 80.0, 0.0], 0.15),
)


class JointRecorder:
    def __init__(self, hand, joint, period):
        self.hand = hand
        self.joint = joint
        self.period = period
        self.command_times = []
        self.command_positions = []
        self.actual_times = []
        self.actual_positions = []
        self.started_at = 0.0
        self.task = None
        self.sub = None

    def start(self):
        self.started_at = time.monotonic()
        self.sub = self.hand.state.subscribe(period=self.period)
        self.task = asyncio.create_task(self._collect())

    async def _collect(self):
        while True:
            state = await self.sub.next()
            self.actual_times.append(time.monotonic() - self.started_at)
            self.actual_positions.append(state.positions_deg[self.joint])

    def command(self, position):
        self.command_times.append(time.monotonic() - self.started_at)
        self.command_positions.append(position)

    async def stop(self):
        if self.sub is not None:
            self.sub.close()
        if self.task is not None:
            self.task.cancel()
            with suppress(asyncio.CancelledError):
                await self.task


async def run_move_scenario(hand, recorder, joint, targets, interval, kp, kd):
    last_handle = None
    for target in targets:
        recorder.command(target)
        last_handle = await hand.motion.move_joint(
            joint, target, duration=max(interval, 0.1), kp=kp, kd=kd, dt=0.01
        )
        await asyncio.sleep(interval)
    if last_handle is not None:
        await last_handle.wait(timeout=2.0)


async def run_servo_scenario(hand, recorder, joint, targets, interval, kp, kd, rate):
    state = await hand.state.snapshot()
    positions = list(state.positions_deg)
    velocities = [0.0] * len(positions)
    session = hand.motion.open_servo(command_timeout_ms=100)
    try:
        period = 1.0 / rate
        for target in targets:
            recorder.command(target)
            positions[joint] = target
            deadline = time.monotonic() + interval
            while time.monotonic() < deadline:
                await session.send_impedance(positions, velocities, kp, kd)
                await asyncio.sleep(period)
    finally:
        session.close()


def plot_results(recorder, boundaries, mode, joint, output):
    import matplotlib.pyplot as plt

    figure, axes = plt.subplots(2, 2, figsize=(14, 9))
    for axis, (name, start, end) in zip(axes.flat, boundaries):
        command = [
            (t, p) for t, p in zip(recorder.command_times, recorder.command_positions)
            if start <= t <= end
        ]
        actual = [
            (t, p) for t, p in zip(recorder.actual_times, recorder.actual_positions)
            if start <= t <= end
        ]
        if command:
            axis.step([t - start for t, _ in command], [p for _, p in command], where="post", label="command")
        if actual:
            axis.plot([t - start for t, _ in actual], [p for _, p in actual], label="actual")
        axis.set_title(name)
        axis.set_xlabel("Time (s)")
        axis.set_ylabel("Position (degree)")
        axis.grid(True, alpha=0.3)
        axis.legend()
    figure.suptitle(f"Revo3 {mode} drag scenarios, joint {joint}")
    figure.tight_layout()
    output = output or f"revo3_drag_scenarios_{mode}_joint{joint}.png"
    figure.savefig(output, dpi=150)
    logger.info("Plot saved to %s", output)


async def run(args):
    manager = None
    hand = None
    recorder = None
    boundaries = []
    try:
        manager, hand = await connect_revo3(args.port, slave_id=args.slave_id)
        recorder = JointRecorder(hand, args.joint, 1.0 / args.state_hz)
        recorder.start()
        for name, targets, interval in SCENARIOS:
            started = time.monotonic() - recorder.started_at
            if args.mode == "move":
                await run_move_scenario(hand, recorder, args.joint, targets, interval, args.kp, args.kd)
            else:
                await run_servo_scenario(hand, recorder, args.joint, targets, interval, args.kp, args.kd, args.servo_hz)
            ended = time.monotonic() - recorder.started_at
            boundaries.append((name, started, ended))
            await asyncio.sleep(0.3)
    finally:
        if recorder is not None:
            await recorder.stop()
        await close_revo3(manager, hand)

    if not args.no_plot:
        plot_results(recorder, boundaries, args.mode, args.joint, args.output)


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port")
    parser.add_argument("--slave-id", type=lambda value: int(value, 0))
    parser.add_argument("--mode", choices=("move", "servo"), default="servo")
    parser.add_argument("--joint", type=int, default=5)
    parser.add_argument("--kp", type=float, default=2.0)
    parser.add_argument("--kd", type=float, default=0.25)
    parser.add_argument("--servo-hz", type=float, default=100.0)
    parser.add_argument("--state-hz", type=float, default=50.0)
    parser.add_argument("--no-plot", action="store_true")
    parser.add_argument("--output")
    return parser.parse_args()


if __name__ == "__main__":
    asyncio.run(run(parse_args()))
