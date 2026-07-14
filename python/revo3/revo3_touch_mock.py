#!/usr/bin/env python3
"""
Revo3 Mock Touch Test.
Demonstrates the granular 13 test cases using MockDeviceContext for offline API verification,
aligning 100% with the Rust revo3_touch.rs options and structure.
"""

import asyncio
import sys
import os

# Align python import paths to import mock_device and revo3_utils
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))) + "/gui")

try:
    from mock_device import MockDeviceContext
    from revo3_utils import libstark, logger
except ImportError as e:
    print(f"Error importing modules: {e}")
    sys.exit(1)

if 'libstark' in globals() and hasattr(libstark, "TouchVendor"):
    TouchVendor = libstark.TouchVendor
else:
    class TouchVendor:
        Unknown = 0
        Pressure = 1
        Matrix = 2

async def run_mock_test():
    logger.info("=== Starting Revo3 Mock Touch Test ===")
    
    # 1. Initialize Mock Device Context in Matrix Mode
    client = MockDeviceContext(mock_type="revo3-matrix-touch")
    slave_id = 1
    
    # =========================================================================
    # 1. Primary Test Targets & Actions Configuration
    # =========================================================================
    # Configure output mode and telemetry action (Cases 9~13):
    # 0: None
    # Single-module options: 1: Single AD, 2: Single Force, 3: SingleMatrixStream
    # Global options:        4: Global AD, 5: Global Force, 6: GlobalMatrixStream
    test_stream_action = 2                           # Default to test single module Force set

    # Smart association: Automatically forced to None if global stream action is selected, otherwise 1.
    test_module_id = None if test_stream_action in [4, 5, 6] else 1

    # =========================================================================
    # 2. Secondary Test Cases Toggle Switches
    # =========================================================================
    test_info_query = True                           # Device general info, point counts, serial numbers
    test_enable_disable = False                      # Individual and collective module enable bitmask toggle
    test_single_module_zero_set = False              # Single module calibration (zero tare)
    test_single_module_zero_query = True             # Single module tare status query
    test_single_module_zero_cancel = False           # Single module tare cancel (restoration)
    test_global_modules_zero_set = False             # Global modules calibration (zero tare)
    test_global_modules_zero_query = True            # Global modules tare status query
    test_global_modules_zero_cancel = False          # Global modules tare cancel (restoration)
    test_single_module_sn_query = True               # Query single module serial number
    test_single_module_restart = False               # Restart single touch module
    test_global_modules_restart = False              # Restart all touch modules

    touch_vendor = client.touch_vendor
    logger.info(f"Mock Device Type: {client.mock_type}, Hardware: {client.hw_type}, Touch Vendor: {touch_vendor}")

    # Check for TouchVendor::Unknown (value is 0) to safely exit on non-touch devices
    is_unknown = False
    if hasattr(touch_vendor, "value"):
        is_unknown = (touch_vendor.value == TouchVendor.Unknown)
    else:
        is_unknown = (touch_vendor == TouchVendor.Unknown or touch_vendor is None)

    if is_unknown:
        logger.warning("Warning: No touch/tactile sensor hardware detected on this device (TouchVendor is Unknown). Exiting example safely.")
        return

    # Case 1: Single Module Restart
    if test_single_module_restart:
        if test_module_id is not None:
            logger.info(f"\n=== Case 1: Single Module {test_module_id} Restart ===")
            await client.revo3_restart_matrix_touch_module(slave_id, test_module_id)
            logger.info("Single module restart command sent.")
        else:
            logger.info("Skipped Case 1: test_module_id is None.")

    # Case 2: Global Modules Restart
    if test_global_modules_restart:
        logger.info("\n=== Case 2: Global Modules Restart ===")
        await client.revo3_restart_matrix_touch_modules(slave_id)
        logger.info("Global modules restart command sent.")

    # Case 3: Device Info and Vendor Query
    if test_info_query:
        logger.info("\n=== Case 3: Device Info ===")
        vendor_int = getattr(touch_vendor, "value", int(touch_vendor))
        if vendor_int == TouchVendor.Matrix:
            point_counts = await client.revo3_get_all_matrix_touch_module_point_counts(slave_id)
            logger.info(f"Matrix Point Counts: {point_counts}")
            sns = await client.revo3_get_all_matrix_touch_module_serial_numbers(slave_id)
            logger.info(f"Matrix Module SNs: {sns}")

    # Case 4: Enable/Disable Touch Modules
    if test_enable_disable:
        logger.info("\n=== Case 4: Touch Module Enable/Disable ===")
        enabled = await client.revo3_get_all_touch_modules_enabled(slave_id)
        logger.info(f"Current enabled mask: 0x{enabled:03X}")
        logger.info("Disabling module 2 (ThumbPad)...")
        await client.revo3_set_touch_module_enabled(slave_id, 2, False)
        enabled_after = await client.revo3_get_all_touch_modules_enabled(slave_id)
        logger.info(f"Enabled mask after toggle: 0x{enabled_after:03X}")
        logger.info("Re-enabling all 11 modules (0x07FF)...")
        await client.revo3_set_all_touch_modules_enabled(slave_id, 0x07FF)

    # Case 5: Single Module Zero Set
    if test_single_module_zero_set:
        if test_module_id is not None:
            logger.info(f"\n=== Case 5: Single Module {test_module_id} Zero Set ===")
            await client.revo3_calibrate_touch_zero_single(slave_id, test_module_id)
            logger.info("Single module zero calibration command sent.")
        else:
            logger.info("Skipped Case 5: test_module_id is None.")

    # Case 6: Single Module Zero Query
    if test_single_module_zero_query:
        if test_module_id is not None:
            logger.info(f"\n=== Case 6: Single Module {test_module_id} Zero Query ===")
            status = await client.revo3_get_matrix_touch_module_tare_status(slave_id, test_module_id)
            logger.info(f"Single Module {test_module_id} Zero Status: {status} (0=not tared, 1=tared)")
        else:
            logger.info("Skipped Case 6: test_module_id is None.")

    # Case 7: Single Module Zero Cancel
    if test_single_module_zero_cancel:
        if test_module_id is not None:
            logger.info(f"\n=== Case 7: Single Module {test_module_id} Zero Cancel ===")
            await client.revo3_set_matrix_touch_module_tare(slave_id, test_module_id, 2)
            logger.info("Single module zero cancel command sent.")
        else:
            logger.info("Skipped Case 7: test_module_id is None.")

    # Case 8: Global Modules Zero Set
    if test_global_modules_zero_set:
        logger.info("\n=== Case 8: Global Modules Zero Set ===")
        await client.revo3_calibrate_touch_zero(slave_id)
        logger.info("Global zero calibration command sent.")

    # Case 9: Global Modules Zero Query
    if test_global_modules_zero_query:
        logger.info("\n=== Case 9: Global Modules Zero Query ===")
        status = await client.revo3_get_matrix_touch_tare_status(slave_id)
        logger.info(f"Global Tare Status: {status} (0=not tared, 1=tared)")

    # Case 10: Global Modules Zero Cancel
    if test_global_modules_zero_cancel:
        logger.info("\n=== Case 10: Global Modules Zero Cancel ===")
        await client.revo3_set_matrix_touch_tare(slave_id, 2)
        logger.info("Global zero cancel command sent.")

    # Case 11: Single Module AD Output
    if test_stream_action == 1:
        if test_module_id is not None:
            logger.info(f"\n=== Case 11: Single Module {test_module_id} Output Mode - Set Adc ===")
            await client.revo3_set_matrix_touch_module_output_mode(slave_id, test_module_id, 0)
            mode = await client.revo3_get_matrix_touch_module_output_mode(slave_id, test_module_id)
            logger.info(f"Single Module {test_module_id} Output Mode: {mode} (0=ADC, 1=Force)")
        else:
            logger.info("Skipped Case 11: test_module_id is None.")

    # Case 12: Single Module Force Output
    if test_stream_action == 2:
        if test_module_id is not None:
            logger.info(f"\n=== Case 12: Single Module {test_module_id} Output Mode - Set Force ===")
            await client.revo3_set_matrix_touch_module_output_mode(slave_id, test_module_id, 1)
            mode = await client.revo3_get_matrix_touch_module_output_mode(slave_id, test_module_id)
            logger.info(f"Single Module {test_module_id} Output Mode: {mode} (0=ADC, 1=Force)")
        else:
            logger.info("Skipped Case 12: test_module_id is None.")

    # Case 13: Global Modules AD Output
    if test_stream_action == 4:
        logger.info("\n=== Case 13: Global Modules Output Mode - Set Adc ===")
        await client.revo3_set_touch_module_value_type(slave_id, 0)
        val_type = await client.revo3_get_touch_module_value_type(slave_id)
        logger.info(f"Global module value type: {val_type}")

    # Case 14: Global Modules Force Output
    if test_stream_action == 5:
        logger.info("\n=== Case 14: Global Modules Output Mode - Set Force ===")
        await client.revo3_set_touch_module_value_type(slave_id, 2)
        val_type = await client.revo3_get_touch_module_value_type(slave_id)
        logger.info(f"Global module value type: {val_type}")

    # Case 15: High-frequency matrix data streaming telemetry loop
    is_matrix_stream = (test_stream_action == 3 or test_stream_action == 6)
    if is_matrix_stream:
        logger.info("\n=== Case 15: Matrix Data Stream ===")
        if test_stream_action == 3:
            if test_module_id is not None:
                logger.info(f"Start telemetry loop for 5 cycles on module {test_module_id}...")
                for cycle in range(5):
                    touch_data = await client.revo3_get_touch_module_data(slave_id, test_module_id)
                    logger.info(f"[{cycle}] Single Module {test_module_id} 60-points data (len={len(touch_data)}):")
                    # Print in 6 rows of 10 values for visual alignment
                    for chunk_idx in range(6):
                        start = chunk_idx * 10
                        end = start + 10
                        row = touch_data[start:end]
                        row_str = " ".join(f"{v:4}" for v in row)
                        logger.info(f"  [{start:2}..{end-1:2}]: {row_str}")
                    await asyncio.sleep(0.1)
            else:
                logger.info("Skipped Case 15: test_module_id is None (required for SingleMatrixStream).")
        else:
            logger.info("Start telemetry loop for 5 cycles on all modules summary...")
            for cycle in range(5):
                all_data = await client.revo3_get_all_touch_data(slave_id)
                max_summary = [max(m) if m else 0 for m in all_data.modules]
                logger.info(f"[{cycle}] Max forces for all 11 modules: {max_summary}")
                await asyncio.sleep(0.1)

    # Case 16: Single Module Serial Number Query
    if test_single_module_sn_query:
        if test_module_id is not None:
            logger.info(f"\n=== Case 16: Single Module {test_module_id} Serial Number Query ===")
            sn = await client.revo3_get_matrix_touch_module_serial_number(slave_id, test_module_id)
            logger.info(f"Module {test_module_id} Serial Number: {sn}")
        else:
            logger.info("Skipped Case 16: test_module_id is None.")

    logger.info("\nMock Test completed successfully.")

if __name__ == "__main__":
    asyncio.run(run_mock_test())
