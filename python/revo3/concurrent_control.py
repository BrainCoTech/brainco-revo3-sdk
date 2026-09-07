"""Concurrent servo streaming control and state subscription demo."""

import argparse
import asyncio

from bc_revo3_sdk import main_mod as sdk


async def state_reader_task(hand: sdk.Hand, stop_event: asyncio.Event, count_target: int) -> None:
    """Read state subscription concurrently at 50Hz."""
    sub = hand.state.subscribe(period=0.02)
    count = 0
    try:
        while not stop_event.is_set() and count < count_target:
            frame = await sub.next()
            count += 1
            print(
                f"[State #{count}] ts={frame.timestamp.sec}."
                f"{frame.timestamp.nsec:09d} J0={frame.positions_deg[0]:.2f} degree"
            )
    finally:
        sub.close()


async def control_loop_task(hand: sdk.Hand, stop_event: asyncio.Event, duration: float, rate: float) -> None:
    """Stream position targets concurrently at high frequency (100Hz)."""
    snapshot = await hand.state.snapshot()
    hold_positions = list(snapshot.positions_deg)
    session = hand.motion.open_servo(command_timeout_ms=100)
    period = 1.0 / rate
    steps = int(duration * rate)
    try:
        for i in range(steps):
            await session.send_position(hold_positions)
            await asyncio.sleep(period)
        print(f"Control loop finished {steps} steps at {rate}Hz.")
    finally:
        session.close()
        stop_event.set()


async def run(args: argparse.Namespace) -> None:
    if not args.run:
        raise RuntimeError("Pass --run after checking the work area and independent stop path")
    manager = sdk.Manager()
    hand = None
    stop_event = asyncio.Event()
    try:
        hand = await manager.connect_auto(port=args.port, slave_id=args.slave_id)
        await asyncio.gather(
            state_reader_task(hand, stop_event, count_target=int(args.duration * 50)),
            control_loop_task(hand, stop_event, duration=args.duration, rate=args.rate),
        )
    finally:
        if hand is not None:
            await hand.close()
        await manager.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port")
    parser.add_argument("--slave-id", type=lambda value: int(value, 0))
    parser.add_argument("--duration", type=float, default=1.0)
    parser.add_argument("--rate", type=float, default=100.0)
    parser.add_argument("--run", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    asyncio.run(run(parse_args()))
