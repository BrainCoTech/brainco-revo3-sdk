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
except ImportError:
    sdk = None
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

    baud_cls = getattr(sdk, "Rs485Baudrate", None)
    baudrate_map = {
        1000000: baud_cls.Baud1Mbps,
        2000000: baud_cls.Baud2Mbps,
        3000000: baud_cls.Baud3Mbps,
        5000000: baud_cls.Baud5Mbps,
    }
    if value in baudrate_map:
        return baudrate_map[value]

    try:
        return baud_cls(value)
    except Exception:
        pass

    raise ValueError(
        f"Invalid RS485 baudrate: {value} bps. Supported values: [1000000, 2000000, 3000000, 5000000]"
    )


def parse_modbus_baudrate(value):
    """Parse an optional CLI Modbus baudrate into the SDK Baudrate enum."""
    if value is None:
        return None
    return int_to_baudrate(int(value, 0))


def baudrate_to_int(baudrate) -> int:
    """Convert an SDK baudrate enum or an existing bps integer to bps."""
    if isinstance(baudrate, int) and not isinstance(baudrate, bool):
        return baudrate if baudrate > 0 else 0
    if sdk is None:
        return 0
    baud_cls = getattr(sdk, "Rs485Baudrate", None)
    if baudrate == baud_cls.Baud1Mbps:
        return 1000000
    elif baudrate == baud_cls.Baud2Mbps:
        return 2000000
    elif baudrate == baud_cls.Baud3Mbps:
        return 3000000
    elif baudrate == baud_cls.Baud5Mbps:
        return 5000000
    return 0


def get_protocol_display_name(protocol_type) -> str:
    """Return a human-readable protocol name."""
    if sdk is None:
        return "Unknown"
    if protocol_type == sdk.ProtocolType.Modbus:
        return "Modbus (RS485)"
    elif protocol_type == sdk.ProtocolType.CanFd:
        return "CANFD"
    return str(protocol_type)


def revo3_uses_motor_api(model) -> bool:
    """Return whether the model is supported by the current Revo3 runtime."""
    if sdk is None:
        return False
    return model in (
        sdk.Revo3Model.Ultra,
        sdk.Revo3Model.UltraTouch,
        sdk.Revo3Model.UltraVisionTouch,
        sdk.Revo3Model.Pro,
        sdk.Revo3Model.ProTouch,
        sdk.Revo3Model.Basic,
        sdk.Revo3Model.BasicTouch,
    )


def has_vision_tactile(model) -> bool:
    """Return whether a Revo3 product model has VisionTouch capability."""
    if sdk is None:
        return False
    return model == sdk.Revo3Model.UltraVisionTouch


def get_model_name(model) -> str:
    """Return a Revo3 hardware display name."""
    if sdk is None:
        return "Unknown"
    descriptions = {
        "Ultra": "Revo3 Ultra (21 DoF)",
        "UltraTouch": "Revo3 Ultra Touch (21 DoF)",
        "UltraVisionTouch": "Revo3 Ultra Vision Touch (21 DoF)",
        "Pro": "Revo3 Pro (16 DoF)",
        "ProTouch": "Revo3 Pro Touch (16 DoF)",
        "Basic": "Revo3 Basic (13 DoF)",
        "BasicTouch": "Revo3 Basic Touch (13 DoF)",
    }
    name = str(model) if hasattr(model, "int_value") else ""
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
    value = model if isinstance(model, int) else -1
    return value_names.get(value, str(model))


def run_async(coro_or_fn, raise_exception: bool = False):
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

    try:
        running_loop = asyncio.get_running_loop()
    except RuntimeError:
        running_loop = None

    async def _wrapper():
        if callable(coro_or_fn):
            return await coro_or_fn()
        else:
            return await coro_or_fn

    if running_loop is not None and running_loop.is_running():
        return running_loop.create_task(_wrapper())

    # 1. Create a new event loop and set it to current thread context.
    # This is critical for PyO3/Tokio runtime to bind and find the Python event loop on the current thread.
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    try:
        return loop.run_until_complete(_wrapper())
    except Exception as e:
        if raise_exception:
            raise e
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
