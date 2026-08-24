"""Read finite State, optional Touch, and Health pull subscriptions."""

import argparse
import asyncio

from bc_revo3_sdk import main_mod as sdk


async def run(args: argparse.Namespace) -> None:
    manager = sdk.Manager()
    hand = None
    state_sub = None
    touch_sub = None
    health_sub = None
    try:
        hand = await manager.connect_auto(port=args.port, slave_id=args.slave_id)
        state_sub = hand.state.subscribe(period=args.period)
        for _ in range(args.count):
            state = await asyncio.wait_for(state_sub.next(), timeout=args.timeout)
            print(
                f"State timestamp={state.timestamp.sec}.{state.timestamp.nsec:09d} "
                f"J0={state.positions_deg[0]:.2f} degree"
            )

        if hand.touch.layout is not None:
            touch_sub = hand.touch.subscribe(period=args.period)
            for _ in range(args.count):
                frame = await asyncio.wait_for(touch_sub.next(), timeout=args.timeout)
                module_count = len(frame.modules)
                signal_modules = sum(
                    1
                    for module in frame.modules
                    if module.force3d is not None
                    or module.torque2d is not None
                    or module.resultant_force_mn is not None
                )
                print(
                    f"Touch sequence={frame.sequence} "
                    f"modules={module_count} force_modules={signal_modules}"
                )

        health_sub = hand.health.subscribe(period=args.health_period)
        for _ in range(args.count):
            health = await asyncio.wait_for(health_sub.next(), timeout=args.timeout)
            print(
                f"Health safety={health.safety_state} "
                f"system={health.system_state} error={health.system_error_code} "
                f"faulted_motors={health.faulted_motor_count}"
            )

        statistics = hand.statistics
        print(
            "RuntimeStatistics: "
            f"state_reads={statistics.state_reads}, "
            f"touch_reads={statistics.touch_reads}, "
            f"failed_operations={statistics.failed_operations}"
        )
    finally:
        if health_sub is not None:
            health_sub.close()
        if touch_sub is not None:
            touch_sub.close()
        if state_sub is not None:
            state_sub.close()
        if hand is not None:
            await hand.close()
        await manager.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port")
    parser.add_argument("--slave-id", type=lambda value: int(value, 0))
    parser.add_argument("--period", type=float, default=0.02)
    parser.add_argument("--health-period", type=float, default=1.0)
    parser.add_argument("--count", type=int, default=3)
    parser.add_argument(
        "--timeout",
        type=float,
        default=5.0,
        help="timeout in seconds for each subscription read (default: 5.0)",
    )
    args = parser.parse_args()
    if args.period <= 0 or args.health_period <= 0:
        parser.error("subscription periods must be positive")
    if args.count <= 0:
        parser.error("count must be positive")
    if args.timeout <= 0:
        parser.error("timeout must be positive")
    return args


if __name__ == "__main__":
    asyncio.run(run(parse_args()))
