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


def run_async(coro_or_fn):
    """Run an async coroutine or coroutine function in a new thread-local event loop.

    [PERFORMANCE REMARK & USAGE WARNING]
    - This helper is specifically designed for LOW-FREQUENCY UI control events
      (e.g., human-triggered button clicks, tab switches, configuration parameter changes).
    - Under low-frequency scenarios, the overhead of creating a new event loop is completely negligible.
    - DO NOT use this helper for HIGH-FREQUENCY polling/streaming loops (e.g. 50Hz+).
      Doing so will cause massive CPU/GC overhead due to loop creation/destruction.
      For high-frequency telemetry, read directly from Rust buffers (see SharedDataManager),
      or use a persistent background thread with a single, long-lived event loop.

    Supports both:
    1. A coroutine function/lambda (Recommended): `run_async(lambda: dev.some_async_func())`
       By using lambda, evaluation is deferred until the event loop is fully bound to the thread-local
       context, preventing "no running event loop" crashes in PyO3/Rust async calls.
    2. A direct coroutine object: `run_async(dev.some_async_func())`
    """
    import asyncio
    import traceback

    # 1. Create a new event loop and set it to current thread context.
    # This is critical for PyO3/Tokio runtime to bind and find the Python event loop on the current thread.
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    # 2. Wrap if callable (lazy evaluation), otherwise execute directly
    async def _wrapper():
        if callable(coro_or_fn):
            return await coro_or_fn()
        else:
            return await coro_or_fn

    try:
        return loop.run_until_complete(_wrapper())
    except Exception as e:
        logger.error(f"Error in run_async execution: {e}")
        traceback.print_exc()
        return None
    finally:
        try:
            # 3. Clean up the loop and thread-local references to prevent memory leaks and closed loop exceptions
            loop.close()
        except Exception:
            pass
        asyncio.set_event_loop(None)
