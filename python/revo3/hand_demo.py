#!/usr/bin/env python3
"""Revo3 hand demo: info, status, touch summary, and a small safe trajectory."""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from common_imports import get_hw_type_name
from common_init import cleanup_context, parse_args_and_init


async def main():
    ctx, _, _ = await parse_args_and_init(sys.argv)
    if ctx is None:
        return 1

    try:
        client = ctx.ctx
        slave_id = ctx.slave_id

        info = await client.revo3_get_device_info(slave_id)
        print("=== Revo3 Python Hand Demo ===")
        print(f"Hardware: {get_hw_type_name(info.hardware_type)}")
        print(f"Serial: {info.serial_number}")
        print(f"Firmware: {info.firmware_version}")

        status = await client.revo3_get_motor_status_data(slave_id)
        print(f"Positions[0..4]: {[round(v, 2) for v in status.positions[:5]]}")
        print(f"Velocities[0..4]: {[round(v, 2) for v in status.velocities[:5]]}")
        print(f"Currents[0..4]: {[round(v, 2) for v in status.currents[:5]]}")

        try:
            enabled = await client.revo3_get_all_touch_modules_enabled(slave_id)
            if enabled:
                summary = await client.revo3_get_touch_summary(slave_id)
                print(f"Touch enabled=0x{enabled:03X}, summary[0..7]={summary[:8]}")
            else:
                print("Touch modules are not enabled or not available.")
        except Exception as exc:
            print(f"Touch summary skipped: {exc}")

        targets = [0.0] * 21
        for joint in (1, 5, 9, 13, 17):
            targets[joint] = 20.0
        print("Move MCP joints to 20 deg...")
        await client.revo3_move_hand(slave_id, targets, 2.0, 0.01)

        print("Return all joints to 0 deg...")
        await client.revo3_move_hand(slave_id, [0.0] * 21, 2.0, 0.01)
        return 0
    finally:
        await cleanup_context(ctx)


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
