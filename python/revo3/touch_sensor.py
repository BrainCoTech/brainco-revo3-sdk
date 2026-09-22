"""Inspect Touch configuration and read normalized 2.0 snapshots."""

import argparse
import asyncio

from bc_revo3_sdk import main_mod as sdk


def build_standard_layout(layout_type: str, high_density_matrix_point_counts: list[int] | None = None) -> sdk.TouchLayout | None:
    norm = layout_type.lower().replace("+", "_").replace("-", "_")
    if norm in ("auto", "none"):
        return None

    fingertip_force_torque_signals = [
        sdk.TouchSignal.TouchPoint,
        sdk.TouchSignal.Force3D,
        sdk.TouchSignal.Torque2D,
        sdk.TouchSignal.ResultantForce,
    ]

    if norm in ("vision_pressure_array", "vision_tips_pressure_array_pads_pressure_array_palm"):
        modules = []
        for i, count in enumerate([57, 52, 52, 52, 52]):
            modules.append(
                sdk.TouchModuleLayout(
                    "pressure_array_thumb_pad_57" if i == 0 else "pressure_array_finger_pad_52",
                    (i + 1) * 2,
                    sdk.TouchRegion.FingerPad,
                    i,
                    [sdk.TouchSignal.TouchPoint],
                    count,
                )
            )
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

    if norm in ("vision_high_density_matrix", "vision_tips_high_density_matrix_pads_high_density_matrix_palm"):
        if high_density_matrix_point_counts is None or len(high_density_matrix_point_counts) != 11:
            raise ValueError(
                "vision_high_density_matrix requires 11 physical module point counts; "
                "pass --high-density-matrix-point-counts when they cannot be read automatically"
            )
        modules = []
        for i, physical_id in enumerate([2, 4, 6, 8, 10]):
            count = high_density_matrix_point_counts[physical_id]
            modules.append(
                sdk.TouchModuleLayout(
                    f"high_density_matrix_finger_pad_{count}",
                    physical_id,
                    sdk.TouchRegion.FingerPad,
                    i,
                    [sdk.TouchSignal.TouchPoint],
                    count,
                )
            )
        palm_count = high_density_matrix_point_counts[0]
        modules.append(
            sdk.TouchModuleLayout(
                f"high_density_matrix_palm_{palm_count}",
                0,
                sdk.TouchRegion.Palm,
                0,
                [sdk.TouchSignal.TouchPoint],
                palm_count,
            )
        )
        return sdk.TouchLayout(modules)

    if norm in ("force_torque_pressure_array", "fingertip_force_torque_tips_pressure_array_pads"):
        modules = []
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

    if norm in ("force_torque_high_density_matrix", "fingertip_force_torque_tips_high_density_matrix_pads"):
        counts = high_density_matrix_point_counts or [200, 80, 120, 80, 120, 80, 120, 80, 120, 80, 120]
        modules = []
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
        physical_indices = [2, 4, 6, 8, 10]
        for i, phys_idx in enumerate(physical_indices):
            count = counts[phys_idx] if phys_idx < len(counts) else 80
            modules.append(
                sdk.TouchModuleLayout(
                    f"high_density_matrix_finger_pad_{count}",
                    (i + 1) * 2,
                    sdk.TouchRegion.FingerPad,
                    i,
                    [sdk.TouchSignal.TouchPoint],
                    count,
                )
            )
        palm_count = counts[0] if counts else 200
        modules.append(
            sdk.TouchModuleLayout(
                f"high_density_matrix_palm_{palm_count}",
                0,
                sdk.TouchRegion.Palm,
                0,
                [sdk.TouchSignal.TouchPoint],
                palm_count,
            )
        )
        return sdk.TouchLayout(modules)

    if norm == "fingertip_force_torque":
        modules = [
            sdk.TouchModuleLayout(
                "fingertip_force_torque_48",
                i,
                sdk.TouchRegion.Fingertip,
                i,
                fingertip_force_torque_signals,
                48,
            )
            for i in range(5)
        ]
        return sdk.TouchLayout(modules)

    if norm == "pressure_array":
        pressure_array_counts = [36, 31, 57, 21, 52, 21, 52, 21, 52, 21, 52]
        modules = [
            sdk.TouchModuleLayout(
                f"pressure_array_module_{count}",
                i,
                sdk.TouchRegion.Fingertip if i in (1, 3, 5, 7, 9) else (sdk.TouchRegion.Palm if i == 0 else sdk.TouchRegion.FingerPad),
                i,
                [sdk.TouchSignal.TouchPoint],
                count,
            )
            for i, count in enumerate(pressure_array_counts)
        ]
        return sdk.TouchLayout(modules)

    raise ValueError(
        f"Unknown layout type: {layout_type}. Supported: "
        "auto, vision_pressure_array, vision_high_density_matrix, "
        "force_torque_pressure_array, force_torque_high_density_matrix, "
        "fingertip_force_torque, pressure_array"
    )


async def run(args: argparse.Namespace) -> None:
    manager = sdk.Manager()
    hand = None
    baudrate = sdk.Rs485Baudrate.Baud5Mbps
    if args.baudrate == 1000000:
        baudrate = sdk.Rs485Baudrate.Baud1Mbps
    elif args.baudrate == 2000000:
        baudrate = sdk.Rs485Baudrate.Baud2Mbps
    elif args.baudrate == 3000000:
        baudrate = sdk.Rs485Baudrate.Baud3Mbps
    elif args.baudrate == 5000000:
        baudrate = sdk.Rs485Baudrate.Baud5Mbps

    try:
        model = None
        if args.model == "ultra-vision-touch":
            model = sdk.Revo3Model.UltraVisionTouch
        hand = await manager.connect_auto(
            port=args.port,
            slave_id=args.slave_id,
            modbus_baudrate=baudrate,
            model=model,
        )

        if args.layout:
            high_density_matrix_counts = args.high_density_matrix_point_counts
            norm_layout = args.layout.lower().replace("+", "_")
            if "high_density_matrix" in norm_layout and high_density_matrix_counts is None:
                try:
                    high_density_matrix_counts = await hand.touch.point_counts()
                except Exception:
                    pass
            new_layout = build_standard_layout(args.layout, high_density_matrix_counts)
            if new_layout is not None:
                await hand.touch.set_layout(new_layout)
                print(f"Applied manual touch layout override: {args.layout}")

        layout = hand.touch.layout
        if layout is None:
            try:
                await hand.touch.point_counts()
            except sdk.SdkError:
                pass
            layout = hand.touch.layout
        if layout is None:
            raise RuntimeError("This hand does not provide the Touch snapshot capability")

        print("=== Revo3 Touch Information ===")
        print(f"Modules: {len(layout.modules)}")
        for region in layout.regions:
            reg_name = getattr(region.region, "name", str(region.region))
            print(
                f"  {reg_name}: {len(region.module_ids)} modules, "
                f"module_ids={region.module_ids}"
            )
        for module in layout.modules:
            signals = ", ".join(getattr(signal, "name", str(signal)) for signal in module.signals)
            reg_name = getattr(module.region, "name", str(module.region))
            print(
                f"  module {module.module_id:02d}: {reg_name:<10}[{module.region_index}], "
                f"points={module.point_count:3d}, signals=[{signals}], layout={module.layout_id}"
            )
        print(f"Enabled mask: 0x{await hand.touch.enabled_mask():04x}")

        if args.modules and len(args.modules) == 1:
            module = await hand.touch.module_snapshot(args.modules[0])
            print(
                f"Single-module check: module={module.module_id}, "
                f"state={module.sample_state}"
            )

        array_modules = [
            module
            for module in layout.modules
            if module.layout_id.startswith(("pressure_array_", "high_density_matrix_"))
        ]
        array_units = {}
        if any(module.layout_id.startswith("high_density_matrix_") for module in array_modules):
            channel_counts = await hand.touch.point_counts()
            print(f"high_density_matrix_* ADC channel counts: {channel_counts}")
        array_modes = {}
        for module in array_modules:
            mode = await hand.touch.value_mode(module.module_id)
            mode_value = int(mode)
            array_modes[module.module_id] = mode_value
            array_units[module.module_id] = "mN" if mode_value == 2 else "ADC"
        if array_modes:
            print(
                f"Array output modes by module: {array_modes} "
                "(0=ADC, 2=force in mN)"
            )

        print(f"\n=== Start Touch Telemetry Loop ({args.count} Cycles) ===")
        names = ["ThumbTip", "IndexTip", "MiddleTip", "RingTip", "PinkyTip"]

        for cycle in range(args.count):
            frame = await hand.touch.snapshot(module_indices=args.modules)
            modules = list(frame.modules)
            fingertip_force_torque_modules = [
                module for module in modules
                if (module.layout_id and module.layout_id.startswith("fingertip_force_torque_"))
                or module.force3d is not None
            ]
            other_modules = [
                module for module in modules
                if not (
                    (module.layout_id and module.layout_id.startswith("fingertip_force_torque_"))
                    or module.force3d is not None
                )
            ]

            if fingertip_force_torque_modules:
                print(f"\n[{cycle:02d}] 5-Finger Force/Touch Telemetry ({len(fingertip_force_torque_modules)} modules):")
                for mod in fingertip_force_torque_modules:
                    region_index = mod.region_index
                    name = names[region_index] if region_index < len(names) else f"Tip{region_index}"
                    diagnostics = mod.diagnostics
                    module_status = diagnostics.module_status_raw if diagnostics is not None else None
                    sensor_fault = diagnostics.sensor_fault_code_raw if diagnostics is not None else None
                    pts = mod.points or []
                    pts_max = max(pts) if pts else 0
                    fx = mod.force3d.x if mod.force3d is not None else 0.0
                    fy = mod.force3d.y if mod.force3d is not None else 0.0
                    fz = mod.force3d.z if mod.force3d is not None else 0.0
                    fn = mod.resultant_force_mn if mod.resultant_force_mn is not None else 0.0
                    mx = mod.torque2d.x if mod.torque2d is not None else 0.0
                    my = mod.torque2d.y if mod.torque2d is not None else 0.0
                    print(
                        f"  [{name:<8}] Module {mod.module_id:02d} | "
                        f"State: {mod.sample_state!s:<12} | "
                        f"Raw: ({module_status!r}, {sensor_fault!r}) | "
                        f"Fx:{fx:+8.1f}, Fy:{fy:+8.1f}, Fz:{fz:+9.1f} mN | "
                        f"Mx:{mx:+8.4f}, My:{my:+8.4f} Nm | "
                        f"Fn:{fn:8.1f} mN | Points({len(pts)}): max={pts_max}"
                    )

            if other_modules:
                hdr = "Tactile Array Telemetry" if not fingertip_force_torque_modules else "  Pads & Palm Tactile Array"
                print(f"[{cycle:02d}] {hdr} ({len(other_modules)} modules):" if not fingertip_force_torque_modules else f"{hdr} ({len(other_modules)} modules):")
                for mod in other_modules:
                    pts = mod.points or []
                    pts_max = max(pts) if pts else 0
                    pts_min = min(pts) if pts else 0
                    pts_sum = sum(pts) if pts else 0
                    non_zero = sum(1 for p in pts if p > 0)
                    point_unit = array_units.get(mod.module_id, "raw")
                    print(
                        f"    [Mod {mod.module_id:02d} | {mod.layout_id:<16}] "
                        f"Points({len(pts):2d}): max={pts_max:5d} {point_unit}, "
                        f"min={pts_min:5d} {point_unit}, sum={pts_sum:7d} {point_unit}, "
                        f"non-zero={non_zero:2d}/{len(pts):2d}"
                    )

            if not fingertip_force_torque_modules and not other_modules:
                regional_lens = [len(mod.regional_forces_mn or []) for mod in frame.modules]
                print(f"[{cycle:02d}] StatusOnly (regional_forces_lens={regional_lens})")

            if cycle + 1 < args.count:
                await asyncio.sleep(args.interval)

    finally:
        if hand is not None:
            await hand.close()
        await manager.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port")
    parser.add_argument("--slave-id", type=lambda value: int(value, 0))
    parser.add_argument("--baudrate", type=int, default=5000000, help="Modbus baudrate (default: 5000000)")
    parser.add_argument("--count", type=int, default=30, help="Number of snapshots to read")
    parser.add_argument("--interval", type=float, default=0.1, help="Delay between snapshots in seconds")
    parser.add_argument(
        "--modules",
        type=lambda value: [int(item, 0) for item in value.split(",")],
        help="Comma-separated public touch module IDs to read; omit for all modules",
    )
    parser.add_argument(
        "--model",
        choices=("auto", "ultra-vision-touch"),
        default="auto",
        help="Model override for devices whose serial number cannot identify the product",
    )
    parser.add_argument(
        "--layout",
        type=str,
        default="auto",
        help=(
            "Touch layout override: auto, vision_pressure_array, vision_high_density_matrix, "
            "force_torque_pressure_array, force_torque_high_density_matrix, "
            "fingertip_force_torque, pressure_array"
        ),
    )
    parser.add_argument(
        "--high-density-matrix-point-counts",
        type=lambda value: [int(item, 0) for item in value.split(",")],
        help="Comma-separated point counts for physical high_density_matrix_* modules 0..10",
    )
    args = parser.parse_args()
    if args.count <= 0:
        parser.error("count must be positive")
    if args.interval < 0.0:
        parser.error("interval must be non-negative")
    if args.high_density_matrix_point_counts is not None and len(args.high_density_matrix_point_counts) != 11:
        parser.error(
            "--high-density-matrix-point-counts requires exactly 11 comma-separated values"
        )
    if args.modules is not None:
        if not args.modules:
            parser.error("--modules must contain at least one module ID")
        if len(args.modules) != len(set(args.modules)):
            parser.error("--modules must not contain duplicate module IDs")
        if any(module < 0 or module > 10 for module in args.modules):
            parser.error("--modules entries must be in range 0..10")
    return args


if __name__ == "__main__":
    asyncio.run(run(parse_args()))
