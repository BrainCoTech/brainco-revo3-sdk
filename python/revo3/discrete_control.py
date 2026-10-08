"""Send one full-hand or scoped command without a Servo session (SDK >= 2.1.2)."""

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
        if args.scope == "joint":
            positions = [positions[args.joint_index]]
        elif args.scope == "finger":
            start = (4 - args.finger_index) * 4
            positions = positions[start:start + 4]
        elif args.scope == "thumb":
            positions = positions[16:21]
        count = len(positions)
        zeros = [0.0] * count
        if args.scope == "hand":
            if args.mode == "position":
                await hand.motion.set_position(positions)
            elif args.mode == "current":
                await hand.motion.set_current(zeros)
            else:
                await hand.motion.set_mit(positions, zeros, [1.0] * count, [0.1] * count, zeros)
        elif args.scope == "joint":
            if args.mode == "position":
                await hand.motion.set_joint_position(args.joint_index, positions[0])
            elif args.mode == "current":
                await hand.motion.set_joint_current(args.joint_index, 0.0)
            else:
                await hand.motion.set_joint_mit(args.joint_index, positions[0], 0.0, 1.0, 0.1, 0.0)
        elif args.scope == "finger":
            if args.mode == "position":
                await hand.motion.set_finger_position(args.finger_index, positions)
            elif args.mode == "current":
                await hand.motion.set_finger_current(args.finger_index, zeros)
            else:
                await hand.motion.set_finger_mit(args.finger_index, positions, zeros, [1.0] * count, [0.1] * count, zeros)
        elif args.scope == "thumb":
            if args.mode == "position":
                await hand.motion.set_thumb_position(positions)
            elif args.mode == "current":
                await hand.motion.set_thumb_current(zeros)
            else:
                await hand.motion.set_thumb_mit(positions, zeros, [1.0] * count, [0.1] * count, zeros)
        print(f"Sent one {args.scope} {args.mode} command; no heartbeat or automatic resend")
        print("Firmware determines target retention; closing the link does not stop control")
    finally:
        if hand is not None:
            await hand.close()
        await manager.close()


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", help="Serial or CAN adapter port")
    parser.add_argument("--mode", choices=("position", "current", "mit"), default="position")
    parser.add_argument("--scope", choices=("hand", "joint", "finger", "thumb"), default="hand")
    parser.add_argument("--joint-index", type=int, choices=range(21), default=0)
    parser.add_argument("--finger-index", type=int, choices=range(1, 5), default=1,
                        help="1=Index, 2=Middle, 3=Ring, 4=Pinky; use thumb scope for thumb")
    parser.add_argument("--run", action="store_true",
                        help="Send a command that may change motor control or hand support")
    return parser.parse_args()


if __name__ == "__main__":
    try:
        asyncio.run(run(parse_args()))
    except (sdk.SdkError, RuntimeError) as error:
        print(f"Error: {error}; inspect state before retrying")
        raise SystemExit(1) from error
