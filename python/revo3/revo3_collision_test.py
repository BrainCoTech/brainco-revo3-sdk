"""
Revo3 Python Collision and Stall Protection Example

Demonstrates configuring and using the collision protection mechanism:
  - Configure CollisionProtectionConfig with ZeroForce strategy
  - Move finger and observe trajectory interruption on collision
"""

import asyncio
import sys
import argparse
from revo3_utils import *



async def main(port=None, protocol_str="auto", slave_id=None):
    """Main function: Initialize Revo3 and execute collision protection demo"""
    logger.info("=== Revo3 Python Collision and Stall Protection Demo ===")

    # Map protocol string to StarkProtocolType
    proto = libstark.StarkProtocolType.Auto
    if protocol_str == "modbus":
        proto = libstark.StarkProtocolType.Modbus
    elif protocol_str == "canfd":
        proto = libstark.StarkProtocolType.CanFd

    devices = await libstark.revo3_auto_detect(
        port=port,
        protocol=proto,
        slave_id=slave_id
    )

    if not devices:
        logger.error("No Revo3 devices found during auto-detect")
        sys.exit(1)

    device = devices[0]
    logger.info(f"Auto-detected: protocol={device.protocol_type}, port={device.port_name}, slave_id={device.slave_id}")

    client = await libstark.init_from_detected(device)
    slave_id = device.slave_id

    # 1. Configure collision protection
    # - Enable detection
    # - Use Hybrid mode (Software tracking error + hardware Stall flag)
    # - Set maximum tracking error to 12.0 degrees
    # - Set maximum current limit to 500mA
    # - Set debounce time to 50ms
    # - Reuse motor status cache only if it is fresher than 50ms
    # - Strategy: ZeroForce (Relaxes all joints to completely limp state on collision)
    config = libstark.CollisionProtectionConfig(
        enable=True,
        source=libstark.CollisionDetectionSource.Hybrid,
        max_position_error=12.0,
        max_current=500.0,
        debounce_time_ms=50,
        max_cached_status_age_ms=50,
        strategy=libstark.CollisionProtectionStrategy.SoftStop,
        auto_clear_time_ms=1000
    )
    client.revo3_set_collision_protection_config(slave_id, config)
    logger.info(f"Collision protection configured: enable={config.enable}, source={config.source}, strategy={config.strategy}")

    # 2. Instruct user to block the finger MCP joint
    joint_id = 13 # Index MCP Flex (main bend joint)
    logger.info(f"Please hold/block Joint {joint_id} to trigger collision protection...")
    target_pos = 60.0
    logger.info(f"Moving Joint {joint_id} to {target_pos} deg over 3.0 s...")

    client.revo3_move_joint(slave_id, joint_id, target_pos, 3.0, 0.01)

    # Monitor collision status
    start_time = asyncio.get_event_loop().time()
    collision_triggered = False

    while asyncio.get_event_loop().time() - start_time < 4.0:
        await asyncio.sleep(0.05)
        is_active = client.revo3_is_collision_active(slave_id, joint_id)
        if is_active:
            logger.warning(f">>> Collision actively detected on Joint {joint_id}! <<<")
            collision_triggered = True
            break

    if collision_triggered:
        logger.info("Collision triggered. Resetting collision state...")
        client.revo3_reset_collision_state(slave_id)
        try:
            status = await client.revo3_get_motor_status_data(slave_id)
            hold_pos = status.positions[joint_id]
            logger.info(f"Holding obstacle position {hold_pos:.2f} deg actively for 3.0s...")
            for _ in range(150): # 3.0s / 20ms = 150 ticks
                await client.revo3_set_motor_mit(slave_id, joint_id, hold_pos, 0.0, 0.0, 0.3, 0.1)
                await asyncio.sleep(0.02)
        except Exception as e:
            logger.error(f"Failed to hold actively: {e}")
            await asyncio.sleep(3.0)
    else:
        logger.info(f"Movement completed without collision. Holding target position {target_pos:.2f} deg actively for 1.0s...")
        for _ in range(50): # 1.0s / 20ms = 50 ticks
            await client.revo3_set_motor_mit(slave_id, joint_id, target_pos, 0.0, 0.0, 1.0, 0.2)
            await asyncio.sleep(0.02)

    # Cleanup
    await libstark.modbus_close(client)
    logger.info("Done. Closed.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Revo3 Python Collision Test")
    parser.add_argument("--port", type=str, default=None, help="Serial port name")
    parser.add_argument("--protocol", type=str, default="auto", choices=["modbus", "canfd", "auto"], help="Protocol type")
    parser.add_argument("--slave-id", type=int, default=None, help="Slave ID")
    args = parser.parse_args()

    asyncio.run(main(port=args.port, protocol_str=args.protocol, slave_id=args.slave_id))
