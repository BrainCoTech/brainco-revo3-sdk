"""Exercise the experimental Revo3 2.x collision protection API."""

import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from common_init import (
    REVO3_ULTRA_JOINT_COUNT,
    close_revo3,
    connect_revo3,
    logger,
    sdk,
)


async def hold_joint(hand, joint_index, position, duration, kp, kd):
    session = hand.motion.open_servo(command_timeout_ms=100)
    try:
        state = await hand.state.snapshot()
        positions = list(state.positions_deg)
        positions[joint_index] = position
        velocities = [0.0] * REVO3_ULTRA_JOINT_COUNT
        kps = [0.0] * REVO3_ULTRA_JOINT_COUNT
        kds = [0.0] * REVO3_ULTRA_JOINT_COUNT
        feedforward_currents = [0.0] * REVO3_ULTRA_JOINT_COUNT
        kps[joint_index] = kp
        kds[joint_index] = kd
        for _ in range(round(duration / 0.02)):
            await session.send_mit(
                positions, velocities, kps, kds, feedforward_currents
            )
            await asyncio.sleep(0.02)
    finally:
        session.close()


async def run(args):
    if not args.run:
        logger.info(
            "Collision test is disabled by default. Re-run with --run to connect and move one joint."
        )
        return

    manager = None
    hand = None
    try:
        manager, hand = await connect_revo3(args.port, slave_id=args.slave_id)
        config = sdk.ExperimentalCollisionConfig(
            enable=True,
            source=sdk.CollisionDetectionSource.Hybrid,
            position_error_threshold_deg=12.0,
            current_threshold_ma=500.0,
            debounce_time_ms=50,
            max_cached_status_age_ms=50,
            strategy=sdk.CollisionProtectionStrategy.SoftStop,
            auto_clear_time_ms=1000,
        )
        await hand.experimental_collision.configure(config)
        logger.info("Block joint %d to trigger collision protection", args.joint)
        motion = await hand.motion.move_joint(
            args.joint, args.target, duration=3.0, dt=0.01
        )

        collision_triggered = False
        deadline = asyncio.get_running_loop().time() + 4.0
        while asyncio.get_running_loop().time() < deadline:
            active = await hand.experimental_collision.active_joints()
            if active[args.joint]:
                collision_triggered = True
                logger.warning("Collision detected on joint %d", args.joint)
                break
            await asyncio.sleep(0.05)

        if collision_triggered:
            motion.cancel()
            await hand.experimental_collision.reset()
            state = await hand.state.snapshot()
            await hold_joint(hand, args.joint, state.positions_deg[args.joint], 3.0, 0.3, 0.1)
        else:
            await motion.wait(timeout=1.0)
            await hold_joint(hand, args.joint, args.target, 1.0, 1.0, 0.2)
    finally:
        await close_revo3(manager, hand)


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port")
    parser.add_argument("--slave-id", type=lambda value: int(value, 0))
    parser.add_argument("--joint", type=int, default=13)
    parser.add_argument("--target", type=float, default=60.0)
    parser.add_argument(
        "--run",
        action="store_true",
        help="Connect to the hand and run the collision motion test",
    )
    return parser.parse_args()


if __name__ == "__main__":
    asyncio.run(run(parse_args()))
