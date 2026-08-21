"""Update a selected Revo3 firmware resource through the 2.x Maintenance API."""

import argparse
import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from common_init import close_revo3, connect_modbus_revo3, logger, sdk


async def run(args):
    file_path = Path(args.file_path)
    if not file_path.is_file():
        raise FileNotFoundError(file_path)
    target = {
        "main": sdk.FirmwareTarget.MainFirmware,
        "image": sdk.FirmwareTarget.Image,
        "motor": sdk.FirmwareTarget.MotorFirmware,
    }[args.target]
    manager = None
    hand = None
    try:
        manager, hand = await connect_modbus_revo3(args.port, slave_id=args.slave_id)
        handle = hand.maintenance.update_firmware(
            str(file_path), target=target, wait_secs=args.wait_secs
        )
        state = await handle.wait(timeout=args.timeout)
        logger.info("%s update state: %s", args.target, state)
        if handle.error is not None:
            raise handle.error
        if state != sdk.OperationState.Succeeded:
            raise RuntimeError(f"resource update ended in {state}")
    finally:
        await close_revo3(manager, hand)


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file_path")
    parser.add_argument("target", choices=("main", "image", "motor"))
    parser.add_argument("--port")
    parser.add_argument("--slave-id", type=lambda value: int(value, 0))
    parser.add_argument("--wait-secs", type=int, default=5)
    parser.add_argument("--timeout", type=float, default=600.0)
    return parser.parse_args()


if __name__ == "__main__":
    asyncio.run(run(parse_args()))
