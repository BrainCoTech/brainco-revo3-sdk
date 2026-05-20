#!/usr/bin/env python3
"""Revo3 hand firmware upgrade example."""

import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from common_init import cleanup_context, parse_args_and_init


async def main():
    parser = argparse.ArgumentParser(add_help=True, description="Revo3 hand DFU")
    parser.add_argument("firmware", help="Firmware .bin/.ota file")
    ctx, args, _ = await parse_args_and_init(sys.argv, parser)
    if ctx is None:
        return 1

    firmware_path = os.path.abspath(args.firmware)
    if not os.path.exists(firmware_path):
        print(f"Firmware file not found: {firmware_path}")
        await cleanup_context(ctx)
        return 1

    try:
        print("=== Revo3 Python Hand DFU ===")
        print(f"Firmware: {firmware_path}")
        print("Do not disconnect power or communication while DFU is running.")
        await ctx.ctx.revo3_start_dfu(ctx.slave_id, firmware_path, 5)
        print("DFU completed.")
        return 0
    finally:
        await cleanup_context(ctx)


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
