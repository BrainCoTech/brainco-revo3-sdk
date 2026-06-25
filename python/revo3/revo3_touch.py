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


async def main(port_name=None):
    client, slave_id = await open_modbus_revo3(port_name=port_name)

    logger.info("=== Revo3 Touch Example ===")

    await client.revo3_set_all_touch_modules_enabled(slave_id, 0x07FF)
    enabled = await client.revo3_get_all_touch_modules_enabled(slave_id)
    logger.info(f"Touch modules enabled: 0x{enabled:03X}")

    await client.revo3_set_touch_data_type(slave_id, touch_data_mode(0))
    data_type = await client.revo3_get_touch_data_type(slave_id)
    logger.info(f"Touch data type: {int(data_type)} (0=Pressure Array, 1=Force Summary)")

    await client.revo3_set_touch_module_value_type(slave_id, touch_module_value_type(2))
    value_type = await client.revo3_get_touch_module_value_type(slave_id)
    logger.info(f"Touch module value type: {int(value_type)} (0=AD, 1=raw pressure, 2=force)")

    summary = await client.revo3_get_touch_summary(slave_id)
    logger.info(f"Touch summary[0..7]: {summary[:8]}")

    palm_data = await client.revo3_get_touch_module_data(slave_id, 0)
    logger.info(f"Palm module points: {len(palm_data)}, first values: {palm_data[:8]}")

    await client.revo3_calibrate_touch_zero(slave_id)
    logger.info("Touch zero calibration command sent.")

    libstark.modbus_close(client)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Revo3 touch sensor example")
    parser.add_argument("--port", type=str, default=None, help="Serial port path")
    args = parser.parse_args()

    asyncio.run(main(args.port))
