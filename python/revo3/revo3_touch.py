#!/usr/bin/env python3
"""Revo3 touch sensor example."""

import argparse
import asyncio

from revo3_utils import libstark, logger, open_modbus_revo3


def touch_data_mode(value: int):
    if hasattr(libstark, "TouchDataMode"):
        return libstark.TouchDataMode(value)
    return value


def touch_module_value_type(value: int):
    if hasattr(libstark, "TouchModuleValueType"):
        return libstark.TouchModuleValueType(value)
    return value


def matrix_touch_output_mode(value: int):
    if hasattr(libstark, "MatrixTouchOutputMode"):
        return libstark.MatrixTouchOutputMode(value)
    return value


def matrix_touch_tare_command(value: int):
    if hasattr(libstark, "MatrixTouchTareCommand"):
        return libstark.MatrixTouchTareCommand(value)
    return value


def pressure_touch_force_tare_command(value: int):
    if hasattr(libstark, "PressureTouchForceTareCommand"):
        return libstark.PressureTouchForceTareCommand(value)
    return value


def touch_vendor(value: int):
    if hasattr(libstark, "TouchVendor"):
        return libstark.TouchVendor(value)
    return value


if hasattr(libstark, "TouchVendor"):
    TouchVendor = libstark.TouchVendor
else:
    class TouchVendor:
        Unknown = 0
        Pressure = 1
        Matrix = 2


async def main(
    port_name=None,
    touch_vendor_override=None,
    module_id=0,
    generic_zero=False,
    pressure_zero_all=False,
    pressure_zero_module=False,
    pressure_force_clear_all=False,
    pressure_force_clear_module=False,
    pressure_force_restore_all=False,
    pressure_force_restore_module=False,
):
    if not 0 <= module_id <= 10:
        raise ValueError(f"module_id must be 0~10, got {module_id}")

    client, slave_id = await open_modbus_revo3(port_name=port_name)

    logger.info("=== Revo3 Touch Example ===")

    try:
        await client.revo3_get_device_info(slave_id)
    except Exception as exc:
        logger.warning(f"Device info query failed: {exc}")

    # Optional: If the touch vendor cannot be auto-detected (e.g. returns 0/Unknown on older firmware),
    # you can manually force-set the touch vendor using --touch-vendor.
    if touch_vendor_override is not None and hasattr(client, "revo3_set_touch_vendor"):
        await client.revo3_set_touch_vendor(slave_id, touch_vendor(touch_vendor_override))

    touch_vendor_val = await client.revo3_get_touch_vendor(slave_id)
    logger.info(f"Touch vendor: {int(touch_vendor_val)} (0=Unknown, 1=Pressure, 2=Matrix)")

    if int(touch_vendor_val) == TouchVendor.Pressure:
        logger.info("Pressure touch detected.")

        if pressure_zero_all:
            await client.revo3_calibrate_pressure_touch_zero(slave_id)
            logger.info("Pressure touch zero calibration sent: all modules register 4011=1")

        if pressure_zero_module:
            await client.revo3_calibrate_pressure_touch_module_zero(slave_id, module_id)
            logger.info(
                f"Pressure touch zero calibration sent: module {module_id} "
                f"register {4012 + module_id}=1"
            )

        if pressure_force_clear_all:
            await client.revo3_set_pressure_touch_force_tare(
                slave_id,
                pressure_touch_force_tare_command(2),
            )
            logger.info("Pressure touch regional force tare clear sent: all modules register 4025=2")

        if pressure_force_clear_module:
            await client.revo3_set_pressure_touch_module_force_tare(
                slave_id,
                module_id,
                pressure_touch_force_tare_command(2),
            )
            logger.info(
                f"Pressure touch regional force tare clear sent: module {module_id} "
                f"register {4026 + module_id}=2"
            )

        if pressure_force_restore_all:
            logger.warning("Restoring all Pressure touch regional force factory settings.")
            await client.revo3_set_pressure_touch_force_tare(
                slave_id,
                pressure_touch_force_tare_command(3),
            )
            logger.info("Pressure touch regional force tare restore sent: all modules register 4025=3")

        if pressure_force_restore_module:
            logger.warning(
                f"Restoring Pressure touch regional force factory settings for module {module_id}."
            )
            await client.revo3_set_pressure_touch_module_force_tare(
                slave_id,
                module_id,
                pressure_touch_force_tare_command(3),
            )
            logger.info(
                f"Pressure touch regional force tare restore sent: module {module_id} "
                f"register {4026 + module_id}=3"
            )

    if int(touch_vendor_val) == TouchVendor.Matrix:
        module_sns = await client.revo3_get_all_matrix_touch_module_serial_numbers(slave_id)
        logger.info(f"Matrix module SNs: {module_sns}")

        point_counts = await client.revo3_get_all_matrix_touch_module_point_counts(slave_id)
        logger.info(f"Matrix module point counts: {point_counts}")

        await client.revo3_set_matrix_touch_output_mode(slave_id, matrix_touch_output_mode(1))
        output_mode = await client.revo3_get_matrix_touch_output_mode(slave_id)
        logger.info(f"Matrix output mode: {int(output_mode)} (0=ADC, 1=force)")

        await client.revo3_set_matrix_touch_tare(slave_id, matrix_touch_tare_command(1))
        tare_status = await client.revo3_get_matrix_touch_tare_status(slave_id)
        logger.info(f"Matrix tare status: {int(tare_status)} (0=not tared, 1=tared, 2=busy or failed)")

    await client.revo3_set_all_touch_modules_enabled(slave_id, 0x07FF)
    enabled = await client.revo3_get_all_touch_modules_enabled(slave_id)
    logger.info(f"Touch modules enabled: 0x{enabled:03X}")

    await client.revo3_set_touch_data_type(slave_id, touch_data_mode(0))
    data_type = await client.revo3_get_touch_data_type(slave_id)
    logger.info(f"Touch data type: {int(data_type)} (0=Tactile Array, 1=Force Summary)")

    await client.revo3_set_touch_module_value_type(slave_id, touch_module_value_type(2))
    value_type = await client.revo3_get_touch_module_value_type(slave_id)
    logger.info(f"Touch module value type: {int(value_type)} (0=ADC, 1=raw pressure, 2=force)")

    summary = await client.revo3_get_touch_summary(slave_id)
    logger.info(f"Touch summary[0..7]: {summary[:8]}")

    palm_data = await client.revo3_get_touch_module_data(slave_id, 0)
    logger.info(f"Palm module points: {len(palm_data)}, first values: {palm_data[:8]}")

    if generic_zero:
        await client.revo3_calibrate_touch_zero(slave_id)
        logger.info("Generic touch zero calibration command sent.")

    libstark.modbus_close(client)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Revo3 touch sensor example")
    parser.add_argument("--port", type=str, default=None, help="Serial port path")
    parser.add_argument(
        "--touch-vendor",
        type=int,
        choices=[1, 2],
        default=None,
        help="Override touch vendor when firmware cannot auto-detect: 1=Pressure, 2=Matrix",
    )
    parser.add_argument(
        "--module-id",
        type=int,
        default=0,
        help="Touch module ID for single-module Pressure/Matrix commands (0~10)",
    )
    parser.add_argument(
        "--generic-zero",
        action="store_true",
        help="Run generic vendor-routed zero calibration",
    )
    parser.add_argument(
        "--pressure-zero-all",
        action="store_true",
        help="Run Pressure touch zero calibration for all modules: 4011=1",
    )
    parser.add_argument(
        "--pressure-zero-module",
        action="store_true",
        help="Run Pressure touch zero calibration for one module: 4012+module_id=1",
    )
    parser.add_argument(
        "--pressure-force-clear-all",
        action="store_true",
        help="Run Pressure touch regional force clear for all modules: 4025=2",
    )
    parser.add_argument(
        "--pressure-force-clear-module",
        action="store_true",
        help="Run Pressure touch regional force clear for one module: 4026+module_id=2",
    )
    parser.add_argument(
        "--pressure-force-restore-all",
        action="store_true",
        help="Restore Pressure touch regional force factory settings for all modules: 4025=3",
    )
    parser.add_argument(
        "--pressure-force-restore-module",
        action="store_true",
        help="Restore Pressure touch regional force factory settings for one module: 4026+module_id=3",
    )
    args = parser.parse_args()

    asyncio.run(
        main(
            port_name=args.port,
            touch_vendor_override=args.touch_vendor,
            module_id=args.module_id,
            generic_zero=args.generic_zero,
            pressure_zero_all=args.pressure_zero_all,
            pressure_zero_module=args.pressure_zero_module,
            pressure_force_clear_all=args.pressure_force_clear_all,
            pressure_force_clear_module=args.pressure_force_clear_module,
            pressure_force_restore_all=args.pressure_force_restore_all,
            pressure_force_restore_module=args.pressure_force_restore_module,
        )
    )
