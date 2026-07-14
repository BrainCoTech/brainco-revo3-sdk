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
                value_type = await client.revo3_get_touch_module_value_type(slave_id)
                summary = await client.revo3_get_touch_summary(slave_id)
                print(
                    f"Touch enabled=0x{enabled:03X}, "
                    f"value_type={int(value_type)}, summary[0..7]={summary[:8]}"
                )
            else:
                print("Touch modules are not enabled or not available.")
        except Exception as exc:
            print(f"Touch summary skipped: {exc}")

        zeros = [0.0] * 21
        grip_targets = [0.0] * 21
        for joint in (1, 2, 5, 6, 9, 10, 13, 14):
            grip_targets[joint] = 60.0
        for joint in (17, 18, 19, 20):
            grip_targets[joint] = 45.0

        # 1. Switch all joints to Impedance mode (4)
        print("Switching all joints to Impedance control mode (4) for smooth trajectory planning...")
        await client.revo3_multi_joint_control(slave_id, 4, zeros)
        await asyncio.sleep(0.1)

        # Step 1: Open all fingers to 0 deg with smooth trajectory
        print("Step 1: Open all fingers to 0 deg (Initial Stretch via revo3_move_hand_wait)...")
        await client.revo3_move_hand_wait(slave_id, zeros, 0.7, 0.025)

        # Step 2: Grip (Move whole hand to 60 deg with smooth trajectory)
        print("Step 2: Close whole hand to 60 deg (Grip via revo3_move_hand_wait)...")
        await client.revo3_move_hand_wait(slave_id, grip_targets, 0.7, 0.025)

        # Step 3: Open again (Return whole hand to 0 deg with smooth trajectory)
        print("Step 3: Open whole hand to 0 deg (Release via revo3_move_hand_wait)...")
        await client.revo3_move_hand_wait(slave_id, zeros, 0.7, 0.025)

        # Step 4: Test fingers one by one (Pinky -> Ring -> Middle -> Index -> Thumb)
        fingers = [
            ("Pinky (Little Finger)", 4, [0.0, 45.0, 45.0, 0.0]),
            ("Ring Finger", 3, [0.0, 45.0, 45.0, 0.0]),
            ("Middle Finger", 2, [0.0, 45.0, 45.0, 0.0]),
            ("Index Finger", 1, [0.0, 45.0, 45.0, 0.0]),
        ]

        for name, idx, finger_target in fingers:
            print(f"Testing: {name} (smooth trajectory)...")
            await client.revo3_move_finger_wait(slave_id, idx, finger_target, 0.5, 0.01)
            await client.revo3_move_finger_wait(slave_id, idx, [0.0] * 4, 0.5, 0.01)

        print("Testing: Thumb (smooth trajectory)...")
        await client.revo3_move_thumb_wait(slave_id, [0.0, 30.0, 30.0, 30.0, 30.0], 0.5, 0.01)
        await client.revo3_move_thumb_wait(slave_id, [0.0] * 5, 0.5, 0.01)

        # Restore all joints back to standard Position control mode (0)
        print("Restoring all joints back to Position control mode...")
        await client.revo3_multi_joint_control(slave_id, 0, zeros)
        await asyncio.sleep(0.1)

        return 0
    finally:
        await cleanup_context(ctx)


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
