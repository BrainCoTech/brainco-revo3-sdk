#!/usr/bin/env python3
"""Run a full-hand motion sequence for controlled engineering diagnostics."""

import argparse
import asyncio
import os
import sys

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
)

from common_imports import get_model_name, sdk
from common_init import cleanup_session, parse_args_and_init


async def main():
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument(
        "--run",
        "--move",
        action="store_true",
        dest="run",
        help="Run the motion sequence after completing safety checks",
    )
    ctx, args, _ = await parse_args_and_init(sys.argv, parser)
    if ctx is None:
        return 1

    try:
        hand = ctx.hand
        info = hand.device_info
        if info is None:
            raise RuntimeError("Device identity is unavailable")
        print("=== Revo3 Full-Hand Motion Diagnostic ===")
        print(f"Model: {get_model_name(info.model)}")
        print(f"Serial: {info.serial_number}")
        print(f"Firmware: {hand.firmware_info.controller_firmware_version}")

        status = await hand.state.snapshot()
        print(f"Positions[0..4]: {[round(v, 2) for v in status.positions_deg[:5]]}")
        print(f"Velocities[0..4]: {[round(v, 2) for v in status.velocities_rpm[:5]]}")
        print(f"Currents[0..4]: {[round(v, 2) for v in status.currents_ma[:5]]}")

        try:
            enabled = await hand.touch.enabled_mask()
            if enabled:
                value_type = await hand.touch.value_mode()
                frame = await hand.touch.snapshot()
                regional_forces = [
                    list(module.regional_forces_mn or []) for module in frame.modules
                ]
                point_counts = [len(module.points or []) for module in frame.modules]
                first_regional = regional_forces[0] if regional_forces else []
                print(
                    f"Touch enabled=0x{enabled:03X}, "
                    f"value_type={int(value_type)}, "
                    f"regional_forces[0][0..7]={first_regional[:8]}, point_counts={point_counts}"
                )
            else:
                print("Touch modules are not enabled or not available.")
        except Exception as exc:
            print(f"Touch summary skipped: {exc}")

        ultra_models = {
            hand_type
            for hand_type in (
                getattr(sdk.Revo3Model, "Ultra", None),
                getattr(sdk.Revo3Model, "UltraTouch", None),
                getattr(sdk.Revo3Model, "UltraVisionTouch", None),
            )
            if hand_type is not None
        }
        layout = hand.joint_layout
        if info.model not in ultra_models or layout is None or layout.joint_count != 21:
            raise RuntimeError("This diagnostic requires a 21-DOF Revo3 Ultra")
        if not args.run:
            print("Inspection complete; no motion was sent. Pass --move to start the sequence.")
            return 0

        print(
            "Starting motion diagnostic. Keep the workspace clear and keep an "
            "independent power-disconnect measure ready."
        )

        zeros = [0.0] * 21
        grip_targets = [0.0] * 21
        # Flex MCP (1, 5, 9, 13) and PIP (2, 6, 10, 14) joints for 4 fingers (Pinky..Index)
        for joint in (1, 2, 5, 6, 9, 10, 13, 14):
            grip_targets[joint] = 60.0
        for joint in (17, 18, 19, 20):
            grip_targets[joint] = 45.0

        # Step 1: Open all fingers to 0 deg with smooth trajectory
        print("Step 1: Open all fingers to 0 deg")
        motion = await hand.motion.move_to(zeros, duration=0.7, dt=0.025)
        await motion.wait(timeout=2.0)

        # Step 2: Grip (Move whole hand to 60 deg with smooth trajectory)
        print("Step 2: Close whole hand to 60 deg")
        motion = await hand.motion.move_to(grip_targets, duration=0.7, dt=0.025)
        await motion.wait(timeout=2.0)

        # Step 3: Open again (Return whole hand to 0 deg with smooth trajectory)
        print("Step 3: Open whole hand to 0 deg")
        motion = await hand.motion.move_to(zeros, duration=0.7, dt=0.025)
        await motion.wait(timeout=2.0)

        # Step 4: Test fingers one by one (Pinky -> Ring -> Middle -> Index -> Thumb)
        fingers = [
            ("Pinky (Little Finger)", 4, [0.0, 45.0, 45.0, 0.0]),
            ("Ring Finger", 3, [0.0, 45.0, 45.0, 0.0]),
            ("Middle Finger", 2, [0.0, 45.0, 45.0, 0.0]),
            ("Index Finger", 1, [0.0, 45.0, 45.0, 0.0]),
        ]

        for name, idx, finger_target in fingers:
            print(f"Testing: {name} (smooth trajectory)...")
            motion = await hand.motion.move_finger(idx, finger_target, 0.5, dt=0.01)
            await motion.wait(timeout=2.0)
            motion = await hand.motion.move_finger(idx, [0.0] * 4, 0.5, dt=0.01)
            await motion.wait(timeout=2.0)

        print("Testing: Thumb (smooth trajectory)...")
        motion = await hand.motion.move_thumb([0.0, 30.0, 30.0, 30.0, 30.0], 0.5, dt=0.01)
        await motion.wait(timeout=2.0)
        motion = await hand.motion.move_thumb([0.0] * 5, 0.5, dt=0.01)
        await motion.wait(timeout=2.0)

        return 0
    finally:
        await cleanup_session(ctx)


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
