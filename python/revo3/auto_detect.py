#!/usr/bin/env python3
"""Revo3 auto-detection example."""

import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from common_imports import check_sdk, get_hw_type_name, get_protocol_display_name, revo3_uses_motor_api, sdk


def parse_protocol(value):
    if value is None or value == "auto":
        return None
    return {
        "modbus": sdk.StarkProtocolType.Modbus,
        "canfd": sdk.StarkProtocolType.CanFd,
        "ethercat": sdk.StarkProtocolType.EtherCAT,
    }[value]


async def main():
    check_sdk()
    parser = argparse.ArgumentParser(description="Revo3 auto-detection")
    parser.add_argument("--scan-all", action="store_true", help="Return every detected Revo3 device")
    parser.add_argument("--port", help="Limit detection to a serial port or CANFD adapter/interface")
    parser.add_argument("--protocol", choices=("auto", "modbus", "canfd", "ethercat"), default="auto")
    args = parser.parse_args()

    devices = await sdk.revo3_auto_detect(
        scan_all=args.scan_all,
        port=args.port,
        protocol=parse_protocol(args.protocol),
    )
    devices = [device for device in devices if revo3_uses_motor_api(device.hardware_type)]

    if not devices:
        print("No Revo3 device detected.")
        return 1

    print(f"Found {len(devices)} Revo3 device(s):")
    for index, device in enumerate(devices, start=1):
        print(f"[{index}] {get_hw_type_name(device.hardware_type)}")
        print(f"    Protocol: {get_protocol_display_name(device.protocol_type)}")
        print(f"    Port: {device.port_name}")
        print(f"    Slave ID: {device.slave_id}")
        print(f"    Baudrate: {getattr(device, 'baudrate', 0)}")
        if getattr(device, "data_baudrate", 0):
            print(f"    Data baudrate: {device.data_baudrate}")
        if device.serial_number:
            print(f"    Serial: {device.serial_number}")
        if device.firmware_version:
            print(f"    Firmware: {device.firmware_version}")

    ctx = await sdk.init_from_detected(devices[0])
    info = await ctx.revo3_get_device_info(devices[0].slave_id)
    print("\nInitialized first device:")
    print(f"    Serial: {info.serial_number}")
    print(f"    Firmware: {info.firmware_version}")
    print(f"    Hardware: {get_hw_type_name(info.hardware_type)}")
    await sdk.modbus_close(ctx)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
