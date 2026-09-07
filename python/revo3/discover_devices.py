#!/usr/bin/env python3
"""Discover Revo3 devices for connection troubleshooting."""

import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from common_imports import (
    baudrate_to_int,
    check_sdk,
    configure_example_logging,
    get_model_name,
    get_protocol_display_name,
    parse_modbus_baudrate,
    revo3_uses_motor_api,
    sdk,
)


def parse_protocol(value):
    if value is None or value == "auto":
        return sdk.ProtocolType.Auto
    return {
        "modbus": sdk.ProtocolType.Modbus,
        "canfd": sdk.ProtocolType.CanFd,
    }[value]


def parse_canfd_data_baudrate(value):
    if value is None:
        return None
    v = str(value).lower().strip().rstrip("m").rstrip("mbps").rstrip("bps")
    try:
        val = int(v)
    except ValueError:
        raise ValueError(f"Invalid CANFD data baudrate: {value}")
    if val == 1 or val == 1000000:
        return sdk.CanFdBaudrate.Baud1Mbps
    elif val == 2 or val == 2000000:
        return sdk.CanFdBaudrate.Baud2Mbps
    elif val == 4 or val == 4000000:
        return sdk.CanFdBaudrate.Baud4Mbps
    elif val == 5 or val == 5000000:
        return sdk.CanFdBaudrate.Baud5Mbps
    else:
        raise ValueError(f"Invalid CANFD data baudrate: {value}. Options: 1M, 2M, 4M, 5M")


def format_baudrate(value: int) -> str:
    if value >= 1_000_000 and value % 1_000_000 == 0:
        return f"{value // 1_000_000}M"
    return str(value)


def format_endpoint_baudrates(device) -> str:
    nominal_baudrate = device.nominal_baudrate_bps
    if device.protocol_type == sdk.ProtocolType.CanFd:
        return (
            f"nominal={format_baudrate(nominal_baudrate)} "
            f"data={format_baudrate(device.data_baudrate_bps)}"
        )
    return f"baud={format_baudrate(nominal_baudrate)}"


async def main():
    check_sdk()
    parser = argparse.ArgumentParser(description="Discover Revo3 devices")
    parser.add_argument("--scan-all", action="store_true", help="Return every detected Revo3 device")
    parser.add_argument("--verbose", action="store_true", help="Enable SDK info logs while scanning")
    parser.add_argument("--port", help="Limit detection to a serial port or CANFD adapter/interface")
    parser.add_argument("--slave-id", type=lambda value: int(value, 0), help="Probe only one slave ID, e.g. 0x7E")
    parser.add_argument(
        "--modbus-baudrate",
        help="Probe only one Modbus baudrate in bps, e.g. 5000000",
    )
    parser.add_argument(
        "--canfd-data-baudrate",
        help="Probe only one CANFD data baudrate, e.g. 5000000 or 5M (Options: 1M, 2M, 4M, 5M)",
    )
    parser.add_argument("--protocol", choices=("auto", "modbus", "canfd"), default="auto")
    args = parser.parse_args()

    configure_example_logging(sdk.LogLevel.Info if args.verbose else sdk.LogLevel.Warn)

    manager = sdk.Manager()
    devices = await manager.discover(
        scan_all=args.scan_all,
        port=args.port,
        protocol=parse_protocol(args.protocol),
        slave_id=args.slave_id,
        modbus_baudrate=parse_modbus_baudrate(args.modbus_baudrate),
        canfd_data_baudrate=parse_canfd_data_baudrate(args.canfd_data_baudrate),
    )

    devices = [device for device in devices if revo3_uses_motor_api(device.model)]

    if not devices:
        print("No Revo3 device detected.")
        await manager.close()
        return 1

    print(f"Found {len(devices)} Revo3 device(s):")
    for index, device in enumerate(devices, start=1):
        side_val = (
            getattr(device.hand_side, "name", str(device.hand_side))
            if device.hand_side
            else "Unknown"
        )
        print(
            f"[{index}] {get_protocol_display_name(device.protocol_type)} "
            f"{device.port_name} slave={device.slave_id} "
            f"{format_endpoint_baudrates(device)} "
            f'hw="{get_model_name(device.model)}" side={side_val} '
            f"serial={device.serial_number or 'unknown'} "
            f"fw={device.firmware_version or 'unknown'}"
        )

    hand = await manager.connect(devices[0])
    info = hand.device_info
    firmware = hand.firmware_info
    print("\nInitialized first device and read device info:")
    if info is None:
        print("Device identity: unavailable")
    else:
        side_str = getattr(info.hand_side, "name", str(info.hand_side))
        print(f"Device:   {info.serial_number or 'unknown'} ({side_str})")
        print(
            f"Model: {get_model_name(info.model)} | "
            f"Hardware revision: {info.hardware_revision or 'unknown'}"
        )
    print(f"Firmware: {firmware.controller_firmware_version or 'unknown'}")
    touch_layout = hand.touch.layout
    if touch_layout is None:
        print("Touch: unavailable")
    else:
        regions = ", ".join(
            f"{getattr(region.region, 'name', region.region)}:{len(region.module_ids)}"
            for region in touch_layout.regions
        )
        print(f"Touch: {len(touch_layout.modules)} modules ({regions})")
    await hand.close()
    await manager.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
