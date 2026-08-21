#!/usr/bin/env python3
"""Revo3 hand trajectory example."""

import asyncio
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from common_init import cleanup_session, parse_args_and_init


async def main():
    parser = argparse.ArgumentParser(add_help=True, description=__doc__)
    parser.add_argument(
        "--move",
        action="store_true",
        help="Acknowledge that this example sends motion commands",
    )
    if "--move" not in sys.argv[1:]:
        parser.print_help()
        print("\nNo connection opened and no motion command sent. Pass --move to run.")
        return 0

    ctx, _, _ = await parse_args_and_init(sys.argv, parser)
    if ctx is None:
        return 1

    try:
        hand = ctx.hand

        print("=== Revo3 Python Hand Trajectory Demo ===")
        print("Single joint: J3 -> 30 deg over 1.5 s")
        motion = await hand.motion.move_joint(3, 30.0, duration=1.5, dt=0.01)
        await motion.wait(timeout=3.0)

        print("Single joint: J3 -> 0 deg at 25 rpm")
        motion = await hand.motion.move_joint(3, 0.0, speed=25.0, dt=0.01)
        await motion.wait(timeout=5.0)

        targets = [0.0] * 21
        for joint in (2, 6, 10, 14, 18):
            targets[joint] = 45.0
        print("Full hand: PIP joints -> 45 deg with custom gains")
        motion = await hand.motion.move_to(targets, duration=2.0, kp=5.0, kd=0.5, dt=0.01)
        await motion.wait(timeout=4.0)

        print("Full hand: all joints -> 0 deg at 25 rpm")
        motion = await hand.motion.move_to([0.0] * 21, speed=25.0, dt=0.01)
        await motion.wait(timeout=8.0)
        return 0
    finally:
        await cleanup_session(ctx)


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
