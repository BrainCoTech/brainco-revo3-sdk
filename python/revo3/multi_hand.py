"""Discover and select multiple Revo3 hands by serial number."""

import argparse
import asyncio

from bc_revo3_sdk import main_mod as sdk


async def run(args: argparse.Namespace) -> None:
    manager = sdk.Manager()
    try:
        devices = await manager.discover(scan_all=True, port=args.port)
        if not devices:
            raise RuntimeError("No Revo3 device detected")

        hands = await manager.connect_all(devices)
        if len(hands) < 2:
            raise RuntimeError("At least two Revo3 hands are required")
        def hand_by_serial_number(serial_number: str) -> sdk.Hand:
            hand = next(
                (
                    hand
                    for hand in hands
                    if hand.device_info is not None
                    and hand.device_info.serial_number == serial_number
                ),
                None,
            )
            if hand is None:
                raise RuntimeError(f"No connected Revo3 hand has SN {serial_number}")
            return hand

        left = hand_by_serial_number(args.left_sn) if args.left_sn else hands[0]
        right = hand_by_serial_number(args.right_sn) if args.right_sn else hands[1]

        left_info = left.device_info
        right_info = right.device_info
        print(f"Left: {left_info.serial_number if left_info else 'unknown'}")
        print(f"Right: {right_info.serial_number if right_info else 'unknown'}")

        left_state, right_state = await asyncio.gather(
            left.state.snapshot(),
            right.state.snapshot(),
        )
        print(f"Left positions: {left_state.positions_deg}")
        print(f"Right positions: {right_state.positions_deg}")

        # Closing one Hand does not close the shared physical port while a
        # sibling Hand still uses it.
        await left.close()
        right_state = await right.state.snapshot()
        print(
            "Right still connected after left close: "
            f"timestamp={right_state.timestamp.sec}.{right_state.timestamp.nsec:09d}"
        )
    finally:
        await manager.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--left-sn")
    parser.add_argument("--right-sn")
    parser.add_argument("--port")
    return parser.parse_args()


if __name__ == "__main__":
    asyncio.run(run(parse_args()))
