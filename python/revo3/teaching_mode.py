"""Record and replay a Revo3 trajectory through the 2.0 Motion API."""

import argparse
import asyncio
import json
from pathlib import Path

from bc_revo3_sdk import main_mod as sdk


async def run(args: argparse.Namespace) -> None:
    manager = sdk.Manager()
    hand = None
    try:
        hand = await manager.connect_auto(port=args.port, slave_id=args.slave_id)
        if args.action == "load":
            payload = json.loads(args.file.read_text(encoding="utf-8"))
            trajectory = payload["positions"]
            period = float(payload.get("period_seconds", 0.01))
            print(f"Loaded frames: {len(trajectory)}; replaying now")
            await hand.motion.replay_hand(
                trajectory,
                dt=period,
                kp=args.kp,
                kd=args.kd,
            )
            print("Replay completed")
        else:
            period = 1.0 / args.frequency
            print(f"Recording {args.duration:.1f} seconds; move the hand manually")
            trajectory = await hand.motion.teach_hand(args.duration, dt=period)
            args.file.write_text(
                json.dumps(
                    {"period_seconds": period, "positions": trajectory},
                    indent=2,
                ),
                encoding="utf-8",
            )
            print(f"Saved frames: {len(trajectory)} to {args.file}")
    finally:
        if hand is not None:
            await hand.close()
        await manager.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Read a hand trajectory, then load and replay it.")
    parser.add_argument("--port")
    parser.add_argument("--slave-id", type=lambda value: int(value, 0))
    action = parser.add_subparsers(dest="action", required=True)

    read = action.add_parser("read", help="Record a trajectory and save it to a JSON file")
    read.add_argument("file", type=Path)
    read.add_argument("--duration", type=float, default=5.0)
    read.add_argument("--frequency", type=float, default=100.0)

    load = action.add_parser("load", help="Load a JSON trajectory and replay it")
    load.add_argument("file", type=Path)
    load.add_argument("--kp", type=float, default=1.0)
    load.add_argument("--kd", type=float, default=0.1)

    args = parser.parse_args()
    if args.action == "read" and (args.duration <= 0 or args.frequency <= 0):
        parser.error("--duration and --frequency must be positive")
    return args


if __name__ == "__main__":
    asyncio.run(run(parse_args()))
