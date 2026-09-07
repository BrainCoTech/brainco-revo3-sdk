#!/usr/bin/env python3
"""Run an explicitly enabled finger and thumb motion sequence."""

import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from common_init import close_revo3, connect_modbus_revo3, logger


def format_angles(angles):
    return "[" + ", ".join(f"{value:.2f} deg" for value in angles) + "]"


async def main(port_name=None):
    logger.info("Connecting to a Revo3 hand over Modbus...")
    manager, hand = await connect_modbus_revo3(port_name=port_name)
    logger.info("Connected to Revo3")

    try:
        status = await hand.state.snapshot()
        logger.info(
            "Initial thumb positions [Rotation, MCP, IP, Abd, Flex]: %s",
            format_angles(status.positions_deg[16:21]),
        )

        duration = 2.0
        dt = 0.01
        thumb_targets = [30.0, 0.0, 0.0, 0.0, 0.0]
        logger.info("Moving thumb to %s over %.1f seconds", thumb_targets, duration)
        motion = await hand.motion.move_thumb(thumb_targets, duration, dt=dt)
        await motion.wait(timeout=duration + 2.0)

        await asyncio.sleep(0.1)
        status = await hand.state.snapshot()
        logger.info("Current thumb positions: %s", format_angles(status.positions_deg[16:21]))

        logger.info("Returning thumb to zero")
        motion = await hand.motion.move_thumb([0.0] * 5, duration, dt=dt)
        await motion.wait(timeout=duration + 2.0)

        finger_id = 1
        finger_targets = [0.0, 45.0, 45.0, 0.0]
        logger.info("Moving finger %d to %s", finger_id, finger_targets)
        motion = await hand.motion.move_finger(
            finger_id,
            finger_targets,
            duration,
            dt=dt,
        )
        await motion.wait(timeout=duration + 2.0)

        await asyncio.sleep(0.1)
        status = await hand.state.snapshot()
        logger.info(
            "Current finger positions [Abd, MCP, PIP, DIP]: %s",
            format_angles(status.positions_deg[12:16]),
        )

        logger.info("Returning finger %d to zero", finger_id)
        motion = await hand.motion.move_finger(
            finger_id,
            [0.0] * 4,
            duration,
            dt=dt,
        )
        await motion.wait(timeout=duration + 2.0)
    finally:
        await close_revo3(manager, hand)
        logger.info("Modbus connection closed")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", "-p")
    parser.add_argument(
        "--move",
        action="store_true",
        help="Acknowledge that this example sends motion commands",
    )
    args = parser.parse_args()
    if not args.move:
        parser.print_help()
        print("\nNo connection opened and no motion command sent. Pass --move to run.")
        raise SystemExit(0)
    asyncio.run(main(args.port))
