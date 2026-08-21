#!/usr/bin/env python3
"""Revo3 hand firmware upgrade example."""

import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from common_init import cleanup_session, logger, parse_args_and_init, sdk


async def main():
    parser = argparse.ArgumentParser(add_help=True, description="Revo3 hand DFU")
    parser.add_argument("firmware", help="Firmware .bin/.ota file path")
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
    ctx, args, _ = await parse_args_and_init(sys.argv, parser)
    if ctx is None:
        return 1

    firmware_path = os.path.abspath(args.firmware)
    if not os.path.exists(firmware_path):
        logger.error("Firmware file not found: %s", firmware_path)
        await cleanup_session(ctx)
        return 1

    try:
        logger.info("=== Revo3 Python Hand DFU ===")
        logger.info("Firmware: %s", firmware_path)
        logger.info("Do not disconnect power or communication while DFU is running.")
        handle = ctx.hand.maintenance.update_firmware(
            firmware_path, wait_secs=args.wait_secs
        )
        state = await handle.wait(timeout=args.timeout)
        logger.info("DFU state: %s", state)
        if handle.error is not None:
            raise handle.error
        if state != sdk.OperationState.Succeeded:
            raise RuntimeError(f"DFU ended in {state}")
        logger.info("Firmware upgrade succeeded!")
        return 0
    finally:
        await cleanup_session(ctx)


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
