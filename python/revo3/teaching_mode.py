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
        period = 1.0 / args.frequency

        if args.load:
            trajectory = json.loads(Path(args.load).read_text(encoding="utf-8"))["positions"]
        else:
            if not args.record:
                raise RuntimeError("Use --record or --load; teaching changes motor control")
            print(f"Recording {args.duration:.1f} seconds; move the hand manually")
            trajectory = await hand.motion.teach_hand(args.duration, dt=period)
            if args.save:
                Path(args.save).write_text(
                    json.dumps(
                        {"period_seconds": period, "positions": trajectory},
                        indent=2,
                    ),
                    encoding="utf-8",
                )

        print(f"Recorded frames: {len(trajectory)}")
        if args.replay:
            await hand.motion.replay_hand(
                trajectory,
                dt=period,
                kp=args.kp,
                kd=args.kd,
            )
            print("Replay completed")
    finally:
        if hand is not None:
            await hand.close()
        await manager.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port")
    parser.add_argument("--slave-id", type=lambda value: int(value, 0))
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--record", action="store_true")
    source.add_argument("--load")
    parser.add_argument("--duration", type=float, default=5.0)
    parser.add_argument("--frequency", type=float, default=100.0)
    parser.add_argument("--save")
    parser.add_argument("--replay", action="store_true")
    parser.add_argument("--kp", type=float, default=1.0)
    parser.add_argument("--kd", type=float, default=0.1)
    args = parser.parse_args()
    if args.duration <= 0 or args.frequency <= 0:
        parser.error("--duration and --frequency must be positive")
    return args


if __name__ == "__main__":
    asyncio.run(run(parse_args()))
