"""Common imports and helpers for Revo3 Python examples."""

import logging
import os
import sys

_current_dir = os.path.dirname(os.path.abspath(__file__))
if _current_dir not in sys.path:
    sys.path.insert(0, _current_dir)

from logger import getLogger

logger = getLogger(logging.INFO)

try:
    from bc_revo3_sdk import main_mod as sdk
    libstark = sdk
except ImportError:
    sdk = None
    libstark = None
    logger.error("bc_revo3_sdk not found. Install: pip install bc-revo3-sdk")


def check_sdk():
    """Return the SDK module or exit with a clear install hint."""
    if sdk is None:
        print("Error: bc_revo3_sdk not found.")
        print("Install: pip install bc-revo3-sdk")
        sys.exit(1)
    return sdk


def int_to_baudrate(value: int):
    """Convert an integer baudrate to the SDK Baudrate enum."""
    if sdk is None:
        return None
    if hasattr(sdk.Baudrate, "from_int"):
        return sdk.Baudrate.from_int(value)

    baudrate_map = {
        115200: sdk.Baudrate.Baud115200,
        57600: sdk.Baudrate.Baud57600,
        19200: sdk.Baudrate.Baud19200,
        460800: sdk.Baudrate.Baud460800,
        1000000: sdk.Baudrate.Baud1Mbps,
        2000000: sdk.Baudrate.Baud2Mbps,
        3000000: sdk.Baudrate.Baud3Mbps,
        5000000: sdk.Baudrate.Baud5Mbps,
    }
    return baudrate_map.get(value, sdk.Baudrate.Baud5Mbps)


def baudrate_to_int(baudrate) -> int:
    """Convert a Baudrate enum to the actual bps value."""
    if sdk is None:
        return 0
    if baudrate == sdk.Baudrate.Baud115200:
        return 115200
    elif baudrate == sdk.Baudrate.Baud57600:
        return 57600
    elif baudrate == sdk.Baudrate.Baud19200:
        return 19200
    elif baudrate == sdk.Baudrate.Baud460800:
        return 460800
    elif baudrate == sdk.Baudrate.Baud1Mbps:
        return 1000000
    elif baudrate == sdk.Baudrate.Baud2Mbps:
        return 2000000
    elif baudrate == sdk.Baudrate.Baud3Mbps:
        return 3000000
    elif baudrate == sdk.Baudrate.Baud5Mbps:
        return 5000000
    return 0


async def modbus_open(port_name: str, baudrate):
    """Open a Revo3 Modbus connection, accepting int or Baudrate enum."""
    check_sdk()
    baudrate_enum = int_to_baudrate(baudrate) if isinstance(baudrate, int) else baudrate
    return await sdk.modbus_open(port_name, baudrate_enum)


def get_protocol_display_name(protocol_type) -> str:
    """Return a human-readable protocol name."""
    if sdk is None:
        return "Unknown"
    if protocol_type == sdk.StarkProtocolType.Modbus:
        return "Modbus (RS485)"
    elif protocol_type == sdk.StarkProtocolType.CanFd:
        return "CANFD"
    elif protocol_type == sdk.StarkProtocolType.EtherCAT:
        return "EtherCAT"
    return str(protocol_type)


def revo3_uses_motor_api(hw_type) -> bool:
    """Check if a hardware type is a Revo3 device."""
    if sdk is None:
        return False
    return hw_type in (
        sdk.StarkHardwareType.Revo3Ultra,
        sdk.StarkHardwareType.Revo3UltraTouch,
        sdk.StarkHardwareType.Revo3UltraVisionTouch,
        sdk.StarkHardwareType.Revo3Pro,
        sdk.StarkHardwareType.Revo3ProTouch,
        sdk.StarkHardwareType.Revo3Basic,
        sdk.StarkHardwareType.Revo3BasicTouch,
    )


def uses_revo3_motor_api(hw_type) -> bool:
    """Compatibility alias used by the GUI panels."""
    return revo3_uses_motor_api(hw_type)


def has_touch(hw_type) -> bool:
    """Return whether a Revo3 hardware type has touch capability."""
    if sdk is None:
        return False
    return hw_type in (
        sdk.StarkHardwareType.Revo3UltraTouch,
        sdk.StarkHardwareType.Revo3UltraVisionTouch,
        sdk.StarkHardwareType.Revo3ProTouch,
        sdk.StarkHardwareType.Revo3BasicTouch,
    )


def get_hw_type_name(hw_type) -> str:
    """Return a Revo3 hardware display name."""
    if sdk is None:
        return "Unknown"
    descriptions = {
        "Revo3Ultra": "Revo3 Ultra (21 DoF)",
        "Revo3UltraTouch": "Revo3 Ultra Touch (21 DoF)",
        "Revo3UltraVisionTouch": "Revo3 Ultra Vision Touch (21 DoF)",
        "Revo3Pro": "Revo3 Pro (16 DoF)",
        "Revo3ProTouch": "Revo3 Pro Touch (16 DoF)",
        "Revo3Basic": "Revo3 Basic (13 DoF)",
        "Revo3BasicTouch": "Revo3 Basic Touch (13 DoF)",
    }
    name = str(hw_type) if hasattr(hw_type, "int_value") else ""
    if name in descriptions:
        return descriptions[name]

    value_names = {
        20: "Revo3 Ultra (21 DoF)",
        21: "Revo3 Ultra Touch (21 DoF)",
        22: "Revo3 Ultra Vision Touch (21 DoF)",
        23: "Revo3 Pro (16 DoF)",
        24: "Revo3 Pro Touch (16 DoF)",
        26: "Revo3 Basic (13 DoF)",
        27: "Revo3 Basic Touch (13 DoF)",
    }
    value = hw_type if isinstance(hw_type, int) else -1
    return value_names.get(value, str(hw_type))
