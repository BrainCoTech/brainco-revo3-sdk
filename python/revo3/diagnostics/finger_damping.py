"""
Revo3 (Revo3) Finger Damping Demo - 21 DoF Dexterous Hand

Demonstrates Revo3-specific motor control APIs:
  - Finger-level MIT control (middle finger, id=2, pure damping test)

Usage:
    python python/revo3/diagnostics/finger_damping.py
    python python/revo3/diagnostics/finger_damping.py --port /dev/ttyUSB0
"""

import asyncio
import sys
import os
import argparse

# Insert paths to allow importing common example support modules.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from common_init import *

async def demo_finger_mit(hand):
    # 1. Move finger to a closed/curled state (45 degrees) first
    logger.info("  Step 1: Moving middle finger to closed position (45 degrees)...")
    motion = await hand.motion.move_finger(
        Revo3Finger.MIDDLE, [0.0, 45.0, 45.0, 45.0], 0.5, dt=0.01
    )
    await motion.wait(timeout=2.0)
    await asyncio.sleep(0.5)

    # 2. Switch to MIT damping control
    logger.info(
        "  Step 2: Switching to Middle finger MIT damping: "
        "Kp=0.0, Kd=0.1, pos=0.0, vel=100.0, current_ff=0.0 mA"
    )
    state = await hand.state.snapshot()
    positions = list(state.positions_deg)
    velocities = [0.0] * 21
    kps = [0.0] * 21
    kds = [0.0] * 21
    feedforward_currents = [0.0] * 21
    start = (4 - int(Revo3Finger.MIDDLE)) * 4
    for joint in range(start, start + 4):
        velocities[joint] = 100.0
        kds[joint] = 0.1
    session = hand.motion.open_servo(command_timeout_ms=100)
    try:
        logger.info("  >>> Try dragging or pulling the middle finger now! <<<")
        for _ in range(250):
            await session.send_mit(
                positions, velocities, kps, kds, feedforward_currents
            )
            await asyncio.sleep(0.02)
    finally:
        session.close()

async def main(port_name=None):
    """Main function: Initialize Revo3 and execute control examples"""
    # Connect to Revo3 device
    manager, hand = await connect_modbus_revo3(port_name=port_name)

    # Execute middle finger MIT damping test
    await demo_finger_mit(hand)

    # Cleanup
    await close_revo3(manager, hand)
    logger.info("Done. Closed.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Revo3 Finger Damping Demo")
    parser.add_argument("--port", "-p", type=str, default=None, help="Serial port name")
    args = parser.parse_args()

    try:
        asyncio.run(main(port_name=args.port))
    except KeyboardInterrupt:
        logger.info("User interrupted")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        sys.exit(1)
