"""
Revo3 Dexterous Hand Multi-Target DFU Example (MCU, Image, Motor)

This example demonstrates how to perform a firmware or resource upgrade for the Revo3 dexterous hand,
using the specific target API or the generalized target API.

It shows:
- Upgrading main board MCU firmware via `revo3_start_mcu_dfu` or `revo3_start_dfu_with_target`.
- Upgrading picture resource via `revo3_start_image_dfu` or `revo3_start_dfu_with_target`.
- Upgrading motor firmware via `revo3_start_motor_dfu` or `revo3_start_dfu_with_target`.
"""

import asyncio
import sys
import os
import argparse
import time

from revo3_utils import *

# Make sure we use the same loop for callback synchronization
main_loop = None
shutdown_event = None

def on_dfu_state(_slave_id, state):
    """Callback triggered on DFU state change."""
    try:
        dfu_state = libstark.DfuState(state)
        logger.info(f"DFU State Update: {dfu_state}")
        if dfu_state in (libstark.DfuState.Completed, libstark.DfuState.Aborted):
            if main_loop and shutdown_event:
                if not shutdown_event.is_set():
                    main_loop.call_soon_threadsafe(shutdown_event.set)
    except Exception as e:
        logger.error(f"Error in on_dfu_state callback: {e}")

def on_dfu_progress(_slave_id, progress):
    """Callback triggered periodically for DFU progress update."""
    if progress >= 1.0:
        print(f"\r[DFU] progress: 100%")
    else:
        print(f"[DFU] progress: {progress * 100.0:.1f}%\r", end="", flush=True)

async def main():
    global main_loop, shutdown_event
    main_loop = asyncio.get_running_loop()
    shutdown_event = asyncio.Event()

    parser = argparse.ArgumentParser(description="Revo3 Multi-Target DFU Example")
    parser.add_argument("file_path", type=str, help="Path to the upgrade binary file")
    parser.add_argument("target_type", type=int, choices=[0, 1, 2], 
                        help="Upgrade target type: 0=MainFw (MCU), 1=Image, 2=MotorFw")
    parser.add_argument("--port", "-p", type=str, default=None, help="Serial port name")
    args = parser.parse_args()

    # Verify target type and print it
    target_map = {
        0: (libstark.OtaTarget.MainFw, "Main Board Firmware (MCU)"),
        1: (libstark.OtaTarget.Image, "Picture Resource (Image)"),
        2: (libstark.OtaTarget.MotorFw, "Motor Driver Firmware (MotorFw)"),
    }
    target, target_name = target_map[args.target_type]

    # Verify that the file exists
    if not os.path.exists(args.file_path):
        logger.error(f"Upgrade file not found: {args.file_path}")
        sys.exit(1)

    file_size = os.path.getsize(args.file_path)
    logger.info(f"Upgrade file path: {args.file_path} ({file_size} bytes)")
    logger.info(f"Upgrade target: {target_name} ({target})")

    # Automatically detect device connection
    (client, slave_id) = await open_modbus_revo3(port_name=args.port)

    # Read and print device info before OTA
    try:
        device_info = await client.revo3_get_device_info(slave_id)
        logger.info(f"Connected Device Info:")
        logger.info(f"  SN: {device_info.serial_number}")
        logger.info(f"  Firmware: {device_info.firmware_version}")
        logger.info(f"  Hardware: {device_info.hardware_type}")
    except Exception as e:
        logger.warning(f"Could not read device info: {e}")

    logger.info("Starting DFU process...")
    start_time = time.perf_counter()

    # Here we show three different ways to invoke the DFU depending on target.
    # We can use the specific shortcuts or the generalized start_dfu_with_target.
    if args.target_type == 0:
        # Shortcut for MCU board upgrade
        await client.revo3_start_mcu_dfu(
            slave_id,
            args.file_path,
            5,
            on_dfu_state,
            on_dfu_progress
        )
    elif args.target_type == 1:
        # Shortcut for Image resource upgrade
        await client.revo3_start_image_dfu(
            slave_id,
            args.file_path,
            5,
            on_dfu_state,
            on_dfu_progress
        )
    elif args.target_type == 2:
        # Shortcut for Motor firmware upgrade
        await client.revo3_start_motor_dfu(
            slave_id,
            args.file_path,
            5,
            on_dfu_state,
            on_dfu_progress
        )
    
    # Wait for the DFU process to complete via callback notification
    await shutdown_event.wait()

    elapsed = time.perf_counter() - start_time
    logger.info(f"DFU process completed in {elapsed:.1f} seconds.")

    # Cleanup and close Modbus client
    libstark.modbus_close(client)
    logger.info("Modbus connection closed.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("User interrupted")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        sys.exit(1)
