"""Inspect, diagnose, record, and replay Revo3 Manager snapshots."""

import argparse
import asyncio
import io
import json
import time
import zipfile
from pathlib import Path
from typing import Optional

try:
    from bc_revo3_sdk import main_mod as sdk
except ImportError:
    sdk = None


def enum_name(value) -> str:
    name = getattr(value, "name", None)
    if name:
        return str(name)
    return str(value).rsplit(".", 1)[-1]


def timestamp_record(timestamp) -> dict:
    return {"clock": str(timestamp.clock), "sec": timestamp.sec, "nsec": timestamp.nsec}


def snapshot_record(hand, state, health) -> dict:
    device_info = hand.device_info
    return {
        "schema": "brainco.revo3.recording.v1",
        "host_time_ns": time.time_ns(),
        "serial_number": device_info.serial_number if device_info else None,
        "positions_degree": list(state.positions_deg),
        "velocities_rpm": list(state.velocities_rpm),
        "currents_ma": list(state.currents_ma),
        "motor_fault_codes": list(health.motor_fault_codes),
        "received_at": timestamp_record(state.timestamp),
        "system_state": health.system_state,
        "system_error_code": health.error_code,
        "safety_state": enum_name(health.safety_state),
    }


def touch_layout_record(hand) -> Optional[dict]:
    layout = hand.touch.layout
    if layout is None:
        return None
    return {
        "regions": [
            {
                "region": enum_name(region.region),
                "module_ids": list(region.module_ids),
            }
            for region in layout.regions
        ],
        "modules": [
            {
                "module_id": module.module_id,
                "region": enum_name(module.region),
                "region_index": module.region_index,
                "signals": [enum_name(signal) for signal in module.signals],
                "point_count": module.point_count,
                "layout_id": module.layout_id,
            }
            for module in layout.modules
        ],
    }


def support_manifest(hand, include_serial: bool) -> dict:
    device_info = hand.device_info
    config = hand.config.runtime_options
    statistics = hand.statistics
    layout = hand.joint_layout
    return {
        "schema": "brainco.revo3.support_bundle.v1",
        "created_at_ns": time.time_ns(),
        "device": {
            "serial_number": (
                device_info.serial_number if include_serial and device_info else None
            ),
            "model": str(device_info.model) if device_info else None,
            "hand_side": str(device_info.hand_side) if device_info else None,
            "hardware_revision": device_info.hardware_revision if device_info else None,
            "controller_firmware_version": (
                hand.firmware_info.controller_firmware_version
            ),
            "joint_layout": layout.layout_id if layout else None,
        },
        "touch_layout": touch_layout_record(hand),
        "runtime_options": {
            "state_subscription_period_ms": config.state_subscription_period_ms,
            "servo_command_timeout_ms": config.servo_command_timeout_ms,
        },
        "runtime_statistics": {
            "state_reads": statistics.state_reads,
            "touch_reads": statistics.touch_reads,
            "commands_sent": statistics.commands_sent,
            "failed_operations": statistics.failed_operations,
            "servo_command_timeouts": statistics.servo_command_timeouts,
        },
        "privacy": {"serial_number_included": include_serial},
    }


async def capture_records(hand, duration: float, rate: float) -> list[dict]:
    records = []
    sub = hand.state.subscribe(period=1.0 / rate)
    try:
        deadline = time.monotonic() + duration
        while time.monotonic() < deadline:
            state = await sub.next()
            health = await hand.health.snapshot()
            records.append(snapshot_record(hand, state, health))
    finally:
        sub.close()
    return records


def write_support_bundle(path: Path, manifest: dict, records: list[dict]) -> None:
    state_jsonl = io.StringIO()
    for record in records:
        state_jsonl.write(json.dumps(record) + "\n")
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        bundle.writestr("manifest.json", json.dumps(manifest, indent=2))
        bundle.writestr("state.jsonl", state_jsonl.getvalue())


async def connected_command(args: argparse.Namespace) -> None:
    if sdk is None:
        raise RuntimeError("bc-revo3-sdk is required for connected commands")
    manager = sdk.Manager()
    hand = None
    try:
        hand = await manager.connect_auto(port=args.port, slave_id=args.slave_id)
        if args.command == "inspect":
            state = await hand.state.snapshot()
            health = await hand.health.snapshot()
            result = snapshot_record(hand, state, health)
            result["firmware"] = hand.firmware_info.controller_firmware_version
            layout = hand.joint_layout
            result["joint_layout"] = layout.layout_id if layout else None
            result["touch_layout"] = touch_layout_record(hand)
            print(json.dumps(result, indent=2))
            return

        records = await capture_records(hand, args.duration, args.rate)
        output = Path(args.output)
        if args.command == "record":
            with output.open("w", encoding="utf-8") as stream:
                for record in records:
                    stream.write(json.dumps(record) + "\n")
            return

        for record in records:
            if not args.include_serial:
                record["serial_number"] = None
        write_support_bundle(
            output, support_manifest(hand, args.include_serial), records
        )
    finally:
        if hand is not None:
            await hand.close()
        await manager.close()


def replay(path: str) -> None:
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        record = json.loads(line)
        print(
            f"{record['host_time_ns']} {record.get('serial_number') or 'unknown'} "
            f"received_at={record['received_at']} safety={record['safety_state']} "
            f"positions={record['positions_degree']}"
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port")
    parser.add_argument("--slave-id", type=lambda value: int(value, 0))
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("inspect")
    record_parser = subparsers.add_parser("record")
    record_parser.add_argument("output")
    record_parser.add_argument("--duration", type=float, default=10.0)
    record_parser.add_argument("--rate", type=float, default=20.0)
    bundle_parser = subparsers.add_parser("bundle")
    bundle_parser.add_argument("output")
    bundle_parser.add_argument("--duration", type=float, default=5.0)
    bundle_parser.add_argument("--rate", type=float, default=10.0)
    bundle_parser.add_argument("--include-serial", action="store_true")
    replay_parser = subparsers.add_parser("replay")
    replay_parser.add_argument("input")
    return parser.parse_args()


if __name__ == "__main__":
    parsed = parse_args()
    if parsed.command == "replay":
        replay(parsed.input)
    else:
        asyncio.run(connected_command(parsed))
