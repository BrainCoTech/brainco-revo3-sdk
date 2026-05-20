"""Revo3-focused device initialization helpers for Python examples."""

import argparse
import os
import sys
from dataclasses import dataclass
from typing import Any, List, Optional

_current_dir = os.path.dirname(os.path.abspath(__file__))
if _current_dir not in sys.path:
    sys.path.insert(0, _current_dir)

from common_imports import check_sdk, get_hw_type_name, logger, modbus_open, sdk, revo3_uses_motor_api


@dataclass
class DeviceContext:
    """Device context for Revo3 examples."""

    ctx: Any
    slave_id: int
    hw_type: Any
    protocol_type: Any
    port_name: str
    baudrate: int = 0
    serial_number: str = ""
    firmware_version: str = ""


async def init_modbus(port: str, baudrate: int, slave_id: int) -> Optional[DeviceContext]:
    """Initialize a Revo3 device via Modbus."""
    check_sdk()
    try:
        ctx = await modbus_open(port, baudrate)
        info = await ctx.revo3_get_device_info(slave_id)
        if not revo3_uses_motor_api(info.hardware_type):
            logger.error(f"Detected non-Revo3 hardware: {get_hw_type_name(info.hardware_type)}")
            await sdk.modbus_close(ctx)
            return None

        return DeviceContext(
            ctx=ctx,
            slave_id=slave_id,
            hw_type=info.hardware_type,
            protocol_type=sdk.StarkProtocolType.Modbus,
            port_name=port,
            baudrate=baudrate,
            serial_number=info.serial_number or "",
            firmware_version=info.firmware_version or "",
        )
    except Exception as exc:
        logger.error(f"Modbus init failed: {exc}")
        return None


async def auto_detect_and_init(select_device: bool = True, scan_all: bool = False) -> Optional[DeviceContext]:
    """Auto-detect Revo3 devices and initialize the selected device."""
    check_sdk()
    try:
        devices = await sdk.revo3_auto_detect(scan_all)
        devices = [device for device in devices if revo3_uses_motor_api(device.hardware_type)]
        if not devices:
            logger.error("No Revo3 devices found")
            return None

        logger.info(f"Found {len(devices)} Revo3 device(s):")
        for index, device in enumerate(devices):
            print(f"\n[{index + 1}] {get_hw_type_name(device.hardware_type)}")
            print(f"    Protocol: {device.protocol_type}")
            print(f"    Port: {device.port_name}")
            print(f"    Slave ID: 0x{device.slave_id:02X} ({device.slave_id})")
            if device.serial_number:
                print(f"    Serial: {device.serial_number}")

        device = devices[0]
        if len(devices) > 1 and select_device:
            try:
                choice = int(input(f"\nSelect device [1-{len(devices)}]: "))
                if 1 <= choice <= len(devices):
                    device = devices[choice - 1]
                else:
                    logger.error("Invalid selection")
                    return None
            except (ValueError, EOFError):
                logger.error("Invalid input")
                return None

        ctx = await sdk.init_from_detected(device)
        return DeviceContext(
            ctx=ctx,
            slave_id=device.slave_id,
            hw_type=device.hardware_type,
            protocol_type=device.protocol_type,
            port_name=device.port_name,
            serial_number=device.serial_number or "",
            firmware_version=device.firmware_version or "",
        )
    except Exception as exc:
        logger.error(f"Auto-detect failed: {exc}")
        return None


async def cleanup_context(ctx: DeviceContext):
    """Close an initialized Revo3 device context."""
    if ctx is None:
        return
    try:
        if ctx.protocol_type == sdk.StarkProtocolType.Modbus:
            await sdk.modbus_close(ctx.ctx)
        elif hasattr(sdk, "close_device_handler"):
            await sdk.close_device_handler(ctx.ctx)
        logger.info("Device connection closed")
    except Exception as exc:
        logger.error(f"Cleanup error: {exc}")


def print_init_usage(prog_name: str = "program"):
    """Print Revo3 initialization usage."""
    print("\nInitialization options:")
    print(f"  {prog_name} -h                              # Show help")
    print(f"  {prog_name}                                 # Auto-detect Revo3")
    print(f"  {prog_name} -m <port> <baudrate> <slave_id> # Revo3 Modbus")
    print("\nExamples:")
    print(f"  {prog_name} -m /dev/ttyUSB0 5000000 1")


def create_init_parser(prog_name: Optional[str] = None) -> argparse.ArgumentParser:
    """Create an argument parser with Revo3 initialization options."""
    parser = argparse.ArgumentParser(
        prog=prog_name,
        add_help=False,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    init_group = parser.add_mutually_exclusive_group()
    init_group.add_argument("-m", "--modbus", nargs=3, metavar=("PORT", "BAUD", "SLAVE"))
    return parser


async def parse_args_and_init(argv: List[str], extra_parser: Optional[argparse.ArgumentParser] = None) -> tuple:
    """Parse command-line initialization args and return a Revo3 DeviceContext."""
    prog_name = os.path.basename(argv[0]) if argv else "program"
    init_parser = create_init_parser(prog_name)
    init_args, remaining = init_parser.parse_known_args(argv[1:])

    extra_args = None
    if extra_parser:
        extra_args, remaining = extra_parser.parse_known_args(remaining)

    if init_args.modbus:
        port, baud, slave = init_args.modbus
        ctx = await init_modbus(port, int(baud), int(slave, 0))
    else:
        ctx = await auto_detect_and_init()

    if ctx is None:
        return None, None, None

    print(f"\n[Init] {get_hw_type_name(ctx.hw_type)}")
    print(f"  Protocol: {ctx.protocol_type}")
    print(f"  Port: {ctx.port_name}")
    print(f"  Slave ID: 0x{ctx.slave_id:02X} ({ctx.slave_id})")
    if ctx.serial_number:
        print(f"  Serial: {ctx.serial_number}")
    if ctx.firmware_version:
        print(f"  Firmware: {ctx.firmware_version}")
    print()

    return ctx, extra_args, remaining


__all__ = [
    "DeviceContext",
    "init_modbus",
    "auto_detect_and_init",
    "cleanup_context",
    "print_init_usage",
    "create_init_parser",
    "parse_args_and_init",
]
