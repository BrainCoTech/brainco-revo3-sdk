#!/usr/bin/env python3
"""Revo3 hand trajectory example."""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from common_init import cleanup_context, parse_args_and_init


async def main():
    ctx, _, _ = await parse_args_and_init(sys.argv)
    if ctx is None:
        return 1

    try:
        client = ctx.ctx
        slave_id = ctx.slave_id

        print("=== Revo3 Python Hand Trajectory Demo ===")
        print("Single joint: J3 -> 30 deg over 1.5 s")
        await client.revo3_move_joint(slave_id, 3, 30.0, 1.5, 0.01)

        print("Single joint: J3 -> 0 deg at 25 rpm")
        await client.revo3_move_joint_with_speed(slave_id, 3, 0.0, 25.0, 0.01)

        targets = [0.0] * 21
        for joint in (2, 6, 10, 14, 18):
            targets[joint] = 45.0
        print("Full hand: PIP joints -> 45 deg with custom gains")
        await client.revo3_move_hand_with_gains(slave_id, targets, 2.0, 0.01, 5.0, 0.5)

        print("Full hand: all joints -> 0 deg at 25 rpm")
        await client.revo3_move_hand_with_speed(slave_id, [0.0] * 21, 25.0, 0.01)
        return 0
    finally:
        await cleanup_context(ctx)


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
