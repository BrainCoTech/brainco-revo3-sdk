"""
Revo3 Damping Overshoot & Damping test for Joint 6 in Python.

Demonstrates the physical overshoot difference between:
  1. Low Damping (Kp = 1.0, Kd = 0.1) -> Expect visible overshoot & oscillation
  2. Optimal Damping (Kp = 1.0, Kd = 0.3) -> Expect smooth arrival at target

Usage:
    python python/revo3/diagnostics/overshoot_test.py
    python python/revo3/diagnostics/overshoot_test.py --port /dev/ttyUSB0
"""

import asyncio
import os
import sys
import time
import argparse

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from common_init import *


async def main(port_name=None):
    # Auto-detect and open Revo3 Modbus connection
    manager, hand = await connect_modbus_revo3(port_name=port_name)

    # Initialize device info, this triggers the inner limits cache synchronization
    info = hand.device_info
    if info is None:
        await close_revo3(manager, hand)
        raise RuntimeError("Device identity is unavailable")
    logger.info(f"Connected Device SN: {info.serial_number}, Model: {info.model}")

    joint_id = 6
    start_pos = 0.0
    target_pos = 80.0
    duration = 0.5
    dt = 0.01

    # 1. Reset J6 to 0.0
    logger.info("\n=== Preparing: Moving Joint 6 to 0.0 degrees ===")
    motion = await hand.motion.move_joint(joint_id, start_pos, duration=1.0, dt=0.01)
    await motion.wait(timeout=2.0)
    await asyncio.sleep(1.0)

    # =========================================================================
    # Test Case 1: Low Damping (Kd = 0.1)
    # =========================================================================
    logger.info("\n=== Test 1: Low Damping (Kp = 1.0, Kd = 0.1) ===")
    logger.info("  Starting step from 0.0 -> 80.0 over 0.5s (100Hz)")

    kp_low = 1.0
    kd_low = 0.1

    async def monitor_task1():
        start_time = time.time()
        while time.time() - start_time < 0.8:
            try:
                status = await sub.next()
                elapsed_ms = int((time.time() - start_time) * 1000)
                print(f"Time: {elapsed_ms:>3} ms | Joint 6: {status.positions_deg[joint_id]:.2f}°")
            except Exception as e:
                pass
            await asyncio.sleep(0.015)

    # Spawn monitoring task and wait for trajectory to complete
    sub = hand.state.subscribe(period=0.015)
    mon_task = asyncio.create_task(monitor_task1())
    motion = await hand.motion.move_joint(
        joint_id, target_pos, duration=duration, dt=dt, kp=kp_low, kd=kd_low
    )
    await motion.wait(timeout=duration + 1.0)
    await mon_task
    sub.close()
    await asyncio.sleep(0.5)
    try:
        status = await hand.state.snapshot()
        logger.info(f"  Final Stable Position: {status.positions_deg[joint_id]:.2f}°")
    except Exception as e:
        pass
    await asyncio.sleep(1.0)

    # 2. Reset back to 0.0
    logger.info("\n=== Resetting: Moving Joint 6 back to 0.0 degrees ===")
    motion = await hand.motion.move_joint(joint_id, start_pos, duration=1.0, dt=0.01)
    await motion.wait(timeout=2.0)
    await asyncio.sleep(1.0)

    # =========================================================================
    # Test Case 2: Optimal Damping (Kd = 0.3)
    # =========================================================================
    logger.info("\n=== Test 2: Optimal Damping (Kp = 1.0, Kd = 0.3) ===")
    logger.info("  Starting step from 0.0 -> 80.0 over 0.5s (100Hz)")

    kp_high = 1.0
    kd_high = 0.3

    async def monitor_task2():
        start_time = time.time()
        while time.time() - start_time < 0.8:
            try:
                status = await sub.next()
                elapsed_ms = int((time.time() - start_time) * 1000)
                print(f"Time: {elapsed_ms:>3} ms | Joint 6: {status.positions_deg[joint_id]:.2f}°")
            except Exception as e:
                pass
            await asyncio.sleep(0.015)

    # Spawn monitoring task and wait for trajectory to complete
    sub = hand.state.subscribe(period=0.015)
    mon_task2 = asyncio.create_task(monitor_task2())
    motion = await hand.motion.move_joint(
        joint_id, target_pos, duration=duration, dt=dt, kp=kp_high, kd=kd_high
    )
    await motion.wait(timeout=duration + 1.0)
    await mon_task2
    sub.close()
    await asyncio.sleep(0.5)
    try:
        status = await hand.state.snapshot()
        logger.info(f"  Final Stable Position: {status.positions_deg[joint_id]:.2f}°")
    except Exception as e:
        pass
    await asyncio.sleep(1.0)

    # Close connection
    await close_revo3(manager, hand)
    logger.info("\n=== Damping overshoot test complete ===")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Revo3 Overshoot Test (Python)")
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
