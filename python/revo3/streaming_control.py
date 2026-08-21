"""Open a Motion streaming-control session and hold the current joint positions."""

import argparse
import asyncio
import time

from bc_revo3_sdk import main_mod as sdk


async def run(args: argparse.Namespace) -> None:
    if not args.run:
        raise RuntimeError("Pass --run after checking the work area and independent stop path")

    manager = sdk.Manager()
    hand = None
    session = None
    try:
        hand = await manager.connect_auto(port=args.port, slave_id=args.slave_id)
        layout = hand.joint_layout
        if layout is None or layout.joint_count != 21:
            raise RuntimeError("The current streaming-control preview requires a 21-joint layout")

        state = await hand.state.snapshot()
        hold_positions = list(state.positions_deg)
        session = hand.motion.open_servo(command_timeout_ms=100)

        period = 1.0 / args.rate
        deadline = time.monotonic() + args.duration
        while time.monotonic() < deadline:
            await session.send_position(hold_positions)
            await asyncio.sleep(period)

        print(f"Servo session state before close: {session.state}")
    finally:
        if session is not None:
            session.close()
        if hand is not None:
            await hand.close()
        await manager.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port")
    parser.add_argument("--slave-id", type=lambda value: int(value, 0))
    parser.add_argument("--duration", type=float, default=1.0)
    parser.add_argument("--rate", type=float, default=50.0)
    parser.add_argument("--run", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    asyncio.run(run(parse_args()))
