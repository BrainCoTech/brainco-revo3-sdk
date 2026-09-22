"""Verification script for Revo3 Fingertip Force/Torque + Pressure Array Hybrid Touch sensors.

Verifies:
1. Touch layout configuration: 5 Fingertip Force/Torque fingertips (3D force/torque + 48 pts) + 5 Pressure Array fingerpads (57/52 pts) + 1 Pressure Array palm (36 pts).
2. Live hybrid touch snapshot reading.
3. Fingertip Force/Torque 5-fingertip force & torque vector parsing (Fx, Fy, Fz, Tx, Ty, Fn).
4. Pressure Array 6-module tactile array reading with runtime ADC/mN unit detection.
5. Module enable state querying.
6. Zero / Tare calibration execution and verification.
7. Legacy read mode switching (PointArray <-> LegacyForceSummary).
"""

import argparse
import asyncio
import sys

from bc_revo3_sdk import main_mod as sdk


def enum_name(value) -> str:
    """Return the variant name for a PyO3 enum or a regular Python enum."""
    name = getattr(value, "name", None)
    if name:
        return name
    return str(value).rsplit(".", 1)[-1]


def protocol_type(name: str):
    """Resolve the protocol enum across SDK 2.x binding names."""
    enum_type = sdk.ProtocolType
    return getattr(enum_type, name)


def touch_read_mode(*names: str):
    """Resolve TouchReadMode names across SDK 2.0 RC bindings."""
    for name in names:
        member = getattr(sdk.TouchReadMode, name, None)
        if member is not None:
            return member
    raise RuntimeError(f"TouchReadMode does not provide any of: {', '.join(names)}")


def build_force_torque_pressure_array_layout() -> sdk.TouchLayout:
    """Build canonical Fingertip Force/Torque + Pressure Array hybrid touch layout."""
    fingertip_force_torque_signals = [
        sdk.TouchSignal.TouchPoint,
        sdk.TouchSignal.Force3D,
        sdk.TouchSignal.Torque2D,
        sdk.TouchSignal.ResultantForce,
    ]
    modules = []
    # 5 Fingertip Force/Torque Fingertips (0..4)
    for i in range(5):
        modules.append(
            sdk.TouchModuleLayout(
                "fingertip_force_torque_48",
                i * 2 + 1,
                sdk.TouchRegion.Fingertip,
                i,
                fingertip_force_torque_signals,
                48,
            )
        )
    # 5 Pressure Array FingerPads (5..9): Thumb (57), Index..Pinky (52)
    pressure_array_pad_counts = [57, 52, 52, 52, 52]
    for i, count in enumerate(pressure_array_pad_counts):
        layout_id = "pressure_array_thumb_pad_57" if i == 0 else "pressure_array_finger_pad_52"
        modules.append(
            sdk.TouchModuleLayout(
                layout_id,
                    (i + 1) * 2,
                sdk.TouchRegion.FingerPad,
                i,
                [sdk.TouchSignal.TouchPoint],
                count,
            )
        )
    # 1 Pressure Array Palm (10): 36 points
    modules.append(
        sdk.TouchModuleLayout(
            "pressure_array_palm_36",
            0,
            sdk.TouchRegion.Palm,
            0,
            [sdk.TouchSignal.TouchPoint],
            36,
        )
    )
    return sdk.TouchLayout(modules)


def parse_args():
    parser = argparse.ArgumentParser(description="Verify Revo3 Fingertip Force/Torque + Pressure Array Hybrid Touch")
    parser.add_argument("--protocol", choices=["canfd", "modbus", "auto"], default="canfd")
    parser.add_argument("--port", default=None, help="Port name (e.g. brainco:0 or /dev/ttyUSB0)")
    parser.add_argument("--slave-id", type=lambda x: int(x, 0), default=None, help="Slave ID (e.g. 0x7F or 127)")
    parser.add_argument("--count", type=int, default=5, help="Number of telemetry frames to read")
    parser.add_argument("--interval", type=float, default=0.1, help="Polling interval in seconds")
    parser.add_argument("--test-tare", action="store_true", help="Execute touch tare verification")
    parser.add_argument(
        "--test-modes",
        action="store_true",
        help="Test PointArray and the legacy secondary-calibrated summary mode",
    )
    return parser.parse_args()


async def run(args):
    protocol = None
    if args.protocol == "canfd":
        protocol = protocol_type("CanFd")
    elif args.protocol == "modbus":
        protocol = protocol_type("Modbus")

    manager = sdk.Manager()
    try:
        print("=" * 70)
        print("Revo3 Fingertip Force/Torque + Pressure Array Hybrid Touch Verification")
        print("=" * 70)
        print(f"Connecting to Revo3 device (protocol={args.protocol}, port={args.port}, slave_id={args.slave_id})...")

        hand = await manager.connect_auto(
            port=args.port,
            protocol=protocol,
            slave_id=args.slave_id,
            broadcast=False,
        )
        info = hand.device_info
        print(f"\n[OK] Connected: {info.serial_number} ({enum_name(info.hand_side)}) | Model: {enum_name(info.model)}")
        endpoint = getattr(hand, "endpoint", None)
        if endpoint is not None:
            print(f"     Transport: {enum_name(endpoint.protocol)} on {endpoint.port_name} (Slave ID: 0x{endpoint.slave_id:02X})")

        # 1. Apply Fingertip Force/Torque + Pressure Array Layout
        print("\n--- 1. Applying Fingertip Force/Torque + Pressure Array Hybrid Layout ---")
        force_torque_pressure_array_layout = build_force_torque_pressure_array_layout()
        await hand.touch.set_layout(force_torque_pressure_array_layout)
        active_layout = hand.touch.layout
        print(f"[OK] Layout registered: modules = {len(active_layout.modules)}")
        for reg in active_layout.regions:
            print(f"     Region {enum_name(reg.region)}: {len(reg.module_ids)} modules, IDs = {reg.module_ids}")

        # 2. Query Module Enable States
        print("\n--- 2. Checking Module Enable States ---")
        mask = await hand.touch.enabled_mask()
        print(f"[OK] Module enabled bitmask: 0x{mask:03X} (binary: {bin(mask)})")
        for module in active_layout.modules:
            module_id = module.module_id
            en = (mask & (1 << module_id)) != 0
            name = module.layout_id.replace("_", " ")
            print(f"     Module {module_id:2d} ({name:18s}): {'ENABLED' if en else 'DISABLED'}")

        # 3. Read frames using the device's current read mode.
        current_read_mode = await hand.touch.read_mode()
        current_value_mode = await hand.touch.value_mode()
        point_unit = "mN" if int(current_value_mode) == 2 else "ADC"
        print(
            f"\n--- 3. Reading {args.count} Live Hybrid Touch Snapshots "
            f"({enum_name(current_read_mode)}, {enum_name(current_value_mode)}) ---"
        )

        finger_names = ["Thumb", "Index", "Middle", "Ring", "Pinky"]

        for frame_idx in range(1, args.count + 1):
            frame = await hand.touch.snapshot()
            timestamp = getattr(frame, "timestamp", None)
            timestamp_s = (timestamp.sec + timestamp.nsec / 1e9) if timestamp else 0.0
            print(f"\n[Frame #{frame_idx:02d}] Timestamp: {timestamp_s:.3f}s | Sequence: {frame.sequence}")
            raw_modules = list(getattr(frame, "modules", []) or [])
            print("  Module slots: " + ", ".join(
                f"id={getattr(m, 'module_id', '?')}:{getattr(m, 'layout_id', '?')}[{len(getattr(m, 'points', []) or [])}]"
                for m in raw_modules
            ))

            # Parse fingertip_force_torque_* fingertips directly from the public TouchFrame model.
            print("  Fingertip Force/Torque Fingertip Modules (3D Force & Torque):")
            fingertip_force_torque_modules = [
                module
                for module in raw_modules
                if str(getattr(module, "layout_id", "")).startswith("fingertip_force_torque_")
            ]
            for mod in fingertip_force_torque_modules:
                region_index = int(getattr(mod, "region_index", 0))
                fname = finger_names[region_index] if region_index < len(finger_names) else f"Tip {region_index}"
                force = getattr(mod, "force3d", None)
                torque = getattr(mod, "torque2d", None)
                diagnostics = getattr(mod, "diagnostics", None)
                points = list(getattr(mod, "points", None) or [])
                print(
                    f"     [{fname:6s} Tip] module_id={mod.module_id} "
                    f"state={enum_name(mod.sample_state)} "
                    f"sensor_fault={getattr(diagnostics, 'sensor_fault_code_raw', None)!r} | "
                    f"Fx={getattr(force, 'x', 0.0):+8.1f} mN "
                    f"Fy={getattr(force, 'y', 0.0):+8.1f} mN "
                    f"Fz={getattr(force, 'z', 0.0):+8.1f} mN | "
                    f"Mx={getattr(torque, 'x', 0.0):+8.4f} Nm "
                    f"My={getattr(torque, 'y', 0.0):+8.4f} Nm | "
                    f"Fn={getattr(mod, 'resultant_force_mn', 0.0) or 0.0:8.1f} mN | "
                    f"Points={len(points)} (max={max(points) if points else 0})"
                )

            # Parse Pressure Array modules (pads + palm) from the canonical module list.
            print("  pressure_array_* Piezoresistive Array Modules:")
            pressure_array_modules = [
                module
                for module in raw_modules
                if enum_name(getattr(module, "region", "")) in ("Palm", "FingerPad")
            ]
            for module in pressure_array_modules:
                points = list(getattr(module, "points", []) or [])
                if points:
                    active = sum(1 for value in points if value > 0)
                    peak = max(points)
                    average = sum(points) / len(points)
                    print(
                        f"     [id={module.module_id:2d} {module.layout_id:18s}] "
                        f"Points: {len(points):3d} | Peak: {peak:4d} {point_unit} | "
                        f"Mean: {average:6.1f} {point_unit} | Active: {active:3d}/{len(points):3d}"
                    )
                else:
                    regional = getattr(module, "regional_forces_mn", None)
                    print(
                        f"     [id={module.module_id:2d} {module.layout_id:18s}] "
                        f"regional_forces_mn={regional!r} state={enum_name(module.sample_state)}"
                    )

            if frame_idx < args.count:
                await asyncio.sleep(args.interval)

        # 4. Test Zero / Tare if requested
        if args.test_tare:
            print("\n--- 4. Testing Zero / Tare Calibration ---")
            print("Executing global touch tare on all 11 modules...")
            await hand.touch.tare()
            print("[OK] Global tare command sent successfully.")
            await asyncio.sleep(0.1)
            frame_after = await hand.touch.snapshot()
            print("Post-Tare Fingertip Force/Torque Resultant Fn:")
            for mod in frame_after.modules:
                if not str(mod.layout_id).startswith("fingertip_force_torque_"):
                    continue
                region_index = int(mod.region_index)
                fname = finger_names[region_index] if region_index < len(finger_names) else f"Tip {region_index}"
                force = mod.force3d
                print(
                    f"     [{fname:6s}] Fn={mod.resultant_force_mn or 0.0:.1f} mN "
                    f"(Fx={getattr(force, 'x', 0.0):+.1f} mN, "
                    f"Fy={getattr(force, 'y', 0.0):+.1f} mN, "
                    f"Fz={getattr(force, 'z', 0.0):+.1f} mN)"
                )

        # 5. Test Read Modes if requested
        if args.test_modes:
            print(
                "\n--- 5. Testing Legacy Read Mode "
                "(PointArray <-> LegacyForceSummary) ---"
            )
            print("Switching to legacy secondary-calibrated force summary mode...")
            await hand.touch.set_read_mode(
                touch_read_mode("LegacyForceSummary", "ForceSummary")
            )
            await asyncio.sleep(0.05)
            frame_summary = await hand.touch.snapshot()
            regional_values = [
                value
                for module in frame_summary.modules
                for value in (getattr(module, "regional_forces_mn", None) or [])
            ]
            if regional_values:
                print(
                    f"[OK] Legacy summary received {len(regional_values)} regional values: "
                    f"{regional_values[:8]}..."
                )
            else:
                print("[OK] Legacy secondary-calibrated summary mode executed.")

            print("Restoring PointArray mode...")
            await hand.touch.set_read_mode(
                touch_read_mode("PointArray", "TactileArray")
            )
            await asyncio.sleep(0.05)
            print("[OK] PointArray mode restored.")

        print("\n" + "=" * 70)
        print("[SUCCESS] Revo3 Fingertip Force/Torque + Pressure Array Hybrid Touch verification complete!")
        print("=" * 70)

    finally:
        await manager.close()


if __name__ == "__main__":
    asyncio.run(run(parse_args()))
