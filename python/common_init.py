"""Revo3-focused device initialization helpers for Python examples."""

import argparse
import os
import sys
from dataclasses import dataclass
from enum import IntEnum
from typing import Any, List, Optional

_current_dir = os.path.dirname(os.path.abspath(__file__))
if _current_dir not in sys.path:
    sys.path.insert(0, _current_dir)

from common_imports import check_sdk, get_model_name, int_to_baudrate, logger, sdk, revo3_uses_motor_api

REVO3_ULTRA_JOINT_COUNT = 21
REVO3_FINGER_COUNT = 5
FINGER_NAMES = ["Thumb", "Index", "Middle", "Ring", "Pinky"]


class Revo3Finger(IntEnum):
    INDEX = 1
    MIDDLE = 2
    RING = 3
    PINKY = 4


@dataclass
class ExampleHandSession:
    """Owning Manager, connected Hand, and discovery metadata."""

    manager: Any
    hand: Any
    slave_id: int
    model: Any
    protocol_type: Any
    port_name: str
    baudrate: int = 0
    serial_number: str = ""
    firmware_version: str = ""


async def init_modbus(port: str, baudrate: int, slave_id: int) -> Optional[ExampleHandSession]:
    """Initialize a Revo3 device via Modbus."""
    check_sdk()
    manager = None
    hand = None
    try:
        manager = sdk.Manager()
        hand = await manager.connect_auto(
            port=port,
            protocol=sdk.ProtocolType.Modbus,
            slave_id=slave_id,
            modbus_baudrate=int_to_baudrate(baudrate),
        )
        info = hand.device_info
        if info is None:
            raise RuntimeError("Device identity is unavailable")
        if not revo3_uses_motor_api(info.model):
            logger.error(f"Detected non-Revo3 hardware: {get_model_name(info.model)}")
            await hand.close()
            await manager.close()
            return None

        return ExampleHandSession(
            manager=manager,
            hand=hand,
            slave_id=slave_id,
            model=info.model,
            protocol_type=sdk.ProtocolType.Modbus,
            port_name=port,
            baudrate=baudrate,
            serial_number=info.serial_number or "",
            firmware_version=hand.firmware_info.controller_firmware_version or "",
        )
    except Exception as exc:
        if hand is not None:
            await hand.close()
        if manager is not None:
            await manager.close()
        logger.error(f"Modbus init failed: {exc}")
        return None


async def auto_detect_and_init(select_device: bool = True, scan_all: bool = False) -> Optional[ExampleHandSession]:
    """Auto-detect Revo3 devices and initialize the selected device."""
    check_sdk()
    try:
        manager = sdk.Manager()
        try:
            devices = await manager.discover(scan_all=scan_all)
        finally:
            await manager.close()
        devices = [device for device in devices if revo3_uses_motor_api(device.model)]
        if not devices:
            logger.error("No Revo3 devices found")
            return None

        logger.info(f"Found {len(devices)} Revo3 device(s):")
        for index, device in enumerate(devices):
            print(f"\n[{index + 1}] {get_model_name(device.model)}")
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

        manager = sdk.Manager()
        try:
            hand = await manager.connect(device)
        except Exception:
            await manager.close()
            raise
        return ExampleHandSession(
            manager=manager,
            hand=hand,
            slave_id=device.slave_id,
            model=device.model,
            protocol_type=device.protocol_type,
            port_name=device.port_name,
            serial_number=device.serial_number or "",
            firmware_version=device.firmware_version or "",
        )
    except Exception as exc:
        logger.error(f"Auto-detect failed: {exc}")
        return None


async def cleanup_session(session: ExampleHandSession):
    """Close an initialized Revo3 device context."""
    if session is None:
        return
    try:
        await session.hand.close()
        await session.manager.close()
        logger.info("Device connection closed")
    except Exception as exc:
        logger.error(f"Cleanup error: {exc}")


async def connect_modbus_revo3(port_name=None, baudrate=5000000, slave_id=None):
    """Connect one Revo3 hand over Modbus and return its owning objects."""
    manager = sdk.Manager()
    try:
        hand = await manager.connect_auto(
            port=port_name,
            protocol=sdk.ProtocolType.Modbus,
            slave_id=slave_id,
            modbus_baudrate=int_to_baudrate(baudrate),
        )
        return manager, hand
    except Exception:
        await manager.close()
        raise


async def connect_revo3(port_name=None, baudrate=5000000, slave_id=None):
    """Connect one Revo3 hand over an automatically selected transport."""
    manager = sdk.Manager()
    try:
        hand = await manager.connect_auto(
            port=port_name,
            slave_id=slave_id,
            modbus_baudrate=int_to_baudrate(baudrate),
        )
        return manager, hand
    except Exception:
        await manager.close()
        raise


async def close_revo3(manager, hand):
    """Close a Hand followed by its owning Manager."""
    if hand is not None:
        await hand.close()
    if manager is not None:
        await manager.close()


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
    """Parse command-line initialization args and return a Revo3 Hand context."""
    prog_name = os.path.basename(argv[0]) if argv else "program"
    if "-h" in argv[1:] or "--help" in argv[1:]:
        if extra_parser is not None:
            extra_parser.print_help()
        print_init_usage(prog_name)
        raise SystemExit(0)
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

    print(f"\n[Init] {get_model_name(ctx.model)}")
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
    "ExampleHandSession",
    "init_modbus",
    "auto_detect_and_init",
    "cleanup_session",
    "connect_modbus_revo3",
    "connect_revo3",
    "close_revo3",
    "sdk",
    "logger",
    "int_to_baudrate",
    "REVO3_ULTRA_JOINT_COUNT",
    "REVO3_FINGER_COUNT",
    "FINGER_NAMES",
    "Revo3Finger",
    "print_init_usage",
    "create_init_parser",
    "parse_args_and_init",
]
