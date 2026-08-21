"""
Revo3 Trajectory & Gain Interruption Verification (Python Example)

This script demonstrates how to verify the native implicit trajectory interruption
and smooth quintic blending in Python.

Each motion command returns a 2.x `OperationHandle`. Starting a newer motion
preempts the active handle; callers wait only when they need a terminal result.

Usage:
    conda activate py310
    python python/revo3/diagnostics/interruption_test.py
"""

import asyncio
import os
import sys
import argparse

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from common_init import *


async def main(port_name=None):
    # 1. Establish Modbus connection (uses 5Mbps by default for Revo3)
    manager, hand = await connect_modbus_revo3(port_name=port_name)

    logger.info("=== Revo3 Gain & Interruption Verification (Python Example) ===")

    joint_id = 1  # Pinky MCP [0, 90°]
    kp = 3.0       # Safe tracking gains
    kd = 0.0

    # 2. Reset joint to 0 degrees near the start
    status = await hand.state.snapshot()
    initial_pos = status.positions_deg[joint_id]
    logger.info(f"J{joint_id} Initial Position: {initial_pos:.2f}°")

    if abs(initial_pos) > 2.0:
        logger.info(f"Preparing environment: resetting J{joint_id} to 0° over 1.0s...")
        # We call the wait-variant to block until the initial setup motion completes
        motion = await hand.motion.move_joint(joint_id, 0.0, duration=1.0, dt=0.01)
        await motion.wait(timeout=2.0)
        await asyncio.sleep(0.5)

    # 3. Action 1: Bending to 70.0° over 1.5s (Non-blocking)
    target1 = 70.0
    logger.info(f"[START] Action 1 (Non-blocking): J{joint_id} -> target={target1:.2f}°, Kp={kp}, Kd={kd}, T=1.5s")
    motion1 = await hand.motion.move_joint(joint_id, target1, duration=1.5, dt=0.01, kp=kp, kd=kd)

    # 4. First Interruption: Let Action 1 run for exactly 600ms
    logger.info("Action 1 running: interrupting in 600ms...")
    await asyncio.sleep(0.60)

    # 5. Action 2: Reversal stretching to -5.0° over 2.0s (Non-blocking Interrupt!)
    target2 = -5.0
    logger.info(f"[INTERRUPT 1] Action 2 (Non-blocking): J{joint_id} -> target={target2:.2f}°, Kp={kp}, Kd={kd}, T=2.0s")
    motion2 = await hand.motion.move_joint(joint_id, target2, duration=2.0, dt=0.01, kp=kp, kd=kd)

    # 6. Second Interruption: Let Action 2 run for exactly 1000ms
    logger.info("Action 2 running: interrupting in 1000ms...")
    await asyncio.sleep(1.0)

    # 7. Action 3: Bending to 50.0° over 1.5s (Non-blocking Interrupt!)
    target3 = 50.0
    logger.info(f"[INTERRUPT 2] Action 3 (Non-blocking): J{joint_id} -> target={target3:.2f}°, Kp={kp}, Kd={kd}, T=1.5s")
    motion3 = await hand.motion.move_joint(joint_id, target3, duration=1.5, dt=0.01, kp=kp, kd=kd)

    # 8. Third Interruption: Let Action 3 run for exactly 800ms
    logger.info("Action 3 running: interrupting in 800ms...")
    await asyncio.sleep(0.8)

    # 9. Action 4: Slow home return to 0.0° over 2.0s (Blocking Wait!)
    target4 = 0.0
    logger.info(f"[INTERRUPT 3] Action 4 (Blocking Wait): J{joint_id} -> target={target4:.2f}°, Kp={kp}, Kd={kd}, T=2.0s")
    motion4 = await hand.motion.move_joint(joint_id, target4, duration=2.0, dt=0.01, kp=kp, kd=kd)
    await motion4.wait(timeout=3.0)
    logger.info("[FINISHED] Action 4 complete.")

    # 10. Verification: Read final position
    await asyncio.sleep(0.2)
    status = await hand.state.snapshot()
    final_pos = status.positions_deg[joint_id]
    logger.info(f"Verification final position of J{joint_id}: {final_pos:.2f}°")

    # Clean up
    logger.info("Preempted states: %s, %s, %s", motion1.state, motion2.state, motion3.state)
    await close_revo3(manager, hand)
    logger.info("Done. Closed connection.")
    logger.info("=== Verification Complete ===")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Revo3 Trajectory Interruption Example")
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
