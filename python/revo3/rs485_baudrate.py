"""Change RS485 baud rate and verify it through a new connection."""

import argparse
import asyncio
from time import monotonic

from bc_revo3_sdk import main_mod as sdk

BAUDRATES = {
    1000000: sdk.Rs485Baudrate.Baud1Mbps,
    2000000: sdk.Rs485Baudrate.Baud2Mbps,
    3000000: sdk.Rs485Baudrate.Baud3Mbps,
    5000000: sdk.Rs485Baudrate.Baud5Mbps,
}


async def run(args):
    target = BAUDRATES[args.target_baudrate]
    manager = sdk.Manager()
    try:
        hand = await manager.connect_auto(
            port=args.port,
            protocol=sdk.ProtocolType.Modbus,
            slave_id=args.slave_id,
            modbus_baudrate=BAUDRATES[args.current_baudrate],
        )
        started = monotonic()
        try:
            await hand.config.set_rs485_baudrate(target)
            print("Write acknowledged; reconnecting to verify the target baud rate.")
        except sdk.SdkError as error:
            print(f"Write result unconfirmed after {monotonic() - started:.3f}s: {error}")
            if error.code != sdk.SdkErrorCode.Timeout:
                raise
        print("Execution continued after the baud-rate request.")
    finally:
        await manager.close()

    # Never reuse the old transport after a baud-rate change or timeout.
    manager = sdk.Manager()
    try:
        hand = await manager.connect_auto(
            port=args.port,
            protocol=sdk.ProtocolType.Modbus,
            slave_id=args.slave_id,
            modbus_baudrate=target,
        )
        configuration = await hand.config.snapshot()
        if configuration.rs485_baudrate != args.target_baudrate:
            raise RuntimeError("Device baud-rate readback differs from the requested value")
        print(f"Target baud rate verified: {args.target_baudrate}")
    finally:
        await manager.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", required=True, help="Serial port, for example COM3")
    parser.add_argument("--slave-id", type=int, default=1)
    parser.add_argument("--current-baudrate", type=int, choices=BAUDRATES, required=True)
    parser.add_argument("--target-baudrate", type=int, choices=BAUDRATES, required=True)
    asyncio.run(run(parser.parse_args()))
