"""Send one full-hand command without a Servo session (SDK >= 2.1.1)."""

import argparse
import asyncio

from bc_revo3_sdk import main_mod as sdk


async def run(args):
    manager = sdk.Manager()
    hand = None
    try:
        hand = await manager.connect_auto(port=args.port)
        layout = hand.joint_layout
        if layout is None or layout.joint_count != 21:
            raise RuntimeError("This example requires a 21-joint hand")
        state = await hand.state.snapshot()
        positions = list(state.positions_deg)
        print(f"Current positions (deg): {positions}")
        if not args.run:
            print("Read-only: add --run to send one command")
            return
        health = await hand.health.snapshot()
        if (
            health.safety_state in (sdk.SafetyState.RecoveryRequired, sdk.SafetyState.Faulted)
            or health.system_state != 0
            or health.error_code != 0
            or health.faulted_motor_count != 0
        ):
            raise RuntimeError("Refusing control because health reports a fault")
        zeros = [0.0] * 21
        if args.mode == "position":
            await hand.motion.set_position(positions)
        elif args.mode == "current":
            await hand.motion.set_current(zeros)
        else:
            await hand.motion.set_mit(
                positions, zeros, [1.0] * 21, [0.1] * 21, zeros,
            )
        print(f"Sent one {args.mode} command; no heartbeat or automatic resend")
        print("Firmware determines target retention; closing the link does not stop control")
    finally:
        if hand is not None:
            await hand.close()
        await manager.close()


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", help="Serial or CAN adapter port")
    parser.add_argument("--mode", choices=("position", "current", "mit"), default="position")
    parser.add_argument("--run", action="store_true",
                        help="Send a command that may change motor control or hand support")
    return parser.parse_args()


if __name__ == "__main__":
    try:
        asyncio.run(run(parse_args()))
    except (sdk.SdkError, RuntimeError) as error:
        print(f"Error: {error}; inspect state before retrying")
        raise SystemExit(1) from error
