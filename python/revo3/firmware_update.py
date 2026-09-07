#!/usr/bin/env python3
"""Update a selected Revo3 firmware target."""

import argparse
import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from common_init import cleanup_session, logger, parse_args_and_init, sdk


async def main():
    parser = argparse.ArgumentParser(add_help=True, description=__doc__)
    parser.add_argument("firmware", help="Firmware .bin/.ota file path")
    parser.add_argument(
        "--target",
        choices=("main", "image", "motor"),
        default="main",
        help="Firmware target (default: main)",
    )
    parser.add_argument(
        "--wait-secs",
        type=int,
        default=5,
        help="Reboot wait time in seconds (default: 5)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=600.0,
        help="DFU timeout in seconds (default: 600.0)",
    )
    parser.add_argument(
        "--run",
        action="store_true",
        help="Acknowledge that this command writes firmware and may reboot the device",
    )
    help_requested = "-h" in sys.argv[1:] or "--help" in sys.argv[1:]
    if "--run" not in sys.argv[1:] and not help_requested:
        parser.error("refusing firmware update without explicit --run acknowledgement")
    ctx, args, remaining = await parse_args_and_init(sys.argv, parser)
    if ctx is None:
        return 1
    if remaining:
        logger.error("Unknown arguments: %s", " ".join(remaining))
        await cleanup_session(ctx)
        return 2

    firmware_path = Path(args.firmware).expanduser().resolve()
    if args.wait_secs < 0:
        logger.error("--wait-secs must be non-negative")
        await cleanup_session(ctx)
        return 2
    if args.timeout <= 0:
        logger.error("--timeout must be positive")
        await cleanup_session(ctx)
        return 2
    if not firmware_path.is_file():
        logger.error("Firmware file not found: %s", firmware_path)
        await cleanup_session(ctx)
        return 1

    try:
        target = {
            "main": sdk.FirmwareTarget.MainFirmware,
            "image": sdk.FirmwareTarget.Image,
            "motor": sdk.FirmwareTarget.MotorFirmware,
        }[args.target]
        logger.info("=== Revo3 Python Firmware Update ===")
        logger.info("Firmware: %s", firmware_path)
        logger.info("Target: %s", args.target)
        logger.info("Do not disconnect power or communication while DFU is running.")
        handle = ctx.hand.maintenance.update_firmware(
            str(firmware_path), target=target, wait_secs=args.wait_secs
        )
        state = await handle.wait(timeout=args.timeout)
        logger.info("DFU state: %s", state)
        if handle.error is not None:
            error = handle.error
            logger.error(
                "DFU error: code=%s effect=%s recovery=%s retryable=%s message=%s",
                error.code,
                error.operation_effect,
                error.recovery_requirement,
                error.retryable,
                error.message,
            )
            return 1
        if state != sdk.OperationState.Succeeded:
            logger.error(
                "DFU ended in %s; inspect device state before retrying", state
            )
            return 1
        logger.info("Firmware update succeeded")
        return 0
    finally:
        await cleanup_session(ctx)


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
