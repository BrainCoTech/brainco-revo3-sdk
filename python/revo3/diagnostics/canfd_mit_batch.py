"""Exercise full-hand MIT commands through the Revo3 2.x CANFD object API."""

import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from common_init import close_revo3, logger, sdk


async def run_canfd_mit_batch():
    manager = sdk.Manager()
    hand = None
    session = None
    try:
        hand = await manager.connect_auto(protocol=sdk.ProtocolType.CanFd)
        info = hand.device_info
        if info is None:
            raise RuntimeError("Device identity is unavailable")
        logger.info("Connected: model=%s SN=%s", info.model, info.serial_number)
        await hand.motion.set_zero_force_enabled(False)

        state = await hand.state.snapshot()
        positions = list(state.positions_deg)
        velocities = [0.0] * 21
        kp = [1.0] * 21
        kd = [0.05] * 21
        feedforward_current = [0.0] * 21

        session = hand.motion.open_servo(command_timeout_ms=100)
        await session.send_mit(positions, velocities, kp, kd, feedforward_current)
        logger.info("Full-hand MIT command sent")
        session.close()
        session = None

        target = [5.0] * 21
        motion = await hand.motion.move_to(
            target, duration=2.0, kp=5.0, kd=0.5, dt=0.05
        )
        await motion.wait(timeout=4.0)
        actual = list((await hand.state.snapshot()).positions)
        errors = [abs(value - expected) for value, expected in zip(actual, target)]
        logger.info(
            "Average error: %.2f degree, max error: %.2f degree",
            sum(errors) / len(errors),
            max(errors),
        )

        motion = await hand.motion.move_to([0.0] * 21, duration=2.0, dt=0.05)
        await motion.wait(timeout=4.0)
    finally:
        if session is not None:
            session.close()
        await close_revo3(manager, hand)


if __name__ == "__main__":
    asyncio.run(run_canfd_mit_batch())
