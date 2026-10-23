"""Read or select register 900's whole-hand mode on supporting firmware.

Requires SDK >= 2.3.0. Position=0, Damping=5, and Mit=6 affect the whole
hand, independently of the command type used by existing joint controls.
Do not call these APIs on older firmware without whole-hand mode support.
Before running a trajectory, replay, or Servo after selecting Position or
Damping, explicitly select Mit. Existing commands do not restore Mit.
"""

import argparse
import asyncio

from bc_revo3_sdk import main_mod as sdk


async def run(args):
    if not args.read and args.mode is None:
        print("Add --read to query the mode, or --mode position|damping|mit --run to change it")
        return
    if args.mode is not None and not args.run:
        raise RuntimeError("Changing the mode requires --run and may change hand support")
    manager = sdk.Manager()
    hand = None
    try:
        hand = await manager.connect_auto(port=args.port)
        if args.mode is not None:
            # Select the whole-hand firmware mode, not a joint command type.
            modes = {
                "position": sdk.HandControlMode.Position,
                "damping": sdk.HandControlMode.Damping,
                "mit": sdk.HandControlMode.Mit,
            }
            await asyncio.wait_for(hand.motion.set_control_mode(modes[args.mode]), timeout=3.0)
        mode = await asyncio.wait_for(hand.motion.get_control_mode(), timeout=3.0)
        print(f"Whole-hand mode: {mode}")
        if mode != sdk.HandControlMode.Mit:
            print(
                "Trajectory, replay, and Servo do not automatically select Mit or reject "
                "a mode mismatch. Before starting them, explicitly call "
                "await hand.motion.set_control_mode(sdk.HandControlMode.Mit)."
            )
        print("No target command was sent; closing the connection does not restore a previous mode")
    finally:
        if hand is not None:
            await hand.close()
        await manager.close()


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", help="Serial or CAN adapter port")
    parser.add_argument("--read", action="store_true", help="Read register 900 explicitly")
    parser.add_argument("--mode", choices=("position", "damping", "mit"))
    parser.add_argument("--run", action="store_true", help="Allow a mode change")
    return parser.parse_args()


if __name__ == "__main__":
    try:
        asyncio.run(run(parse_args()))
    except (sdk.SdkError, RuntimeError, asyncio.TimeoutError) as error:
        print(f"Error: {error}; a sent write may have taken effect. Inspect state before retrying")
        raise SystemExit(1) from error
