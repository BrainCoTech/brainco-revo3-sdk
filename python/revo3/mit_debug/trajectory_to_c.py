"""Convert trajectory JSON (from revo3_teaching.py) to a C header file.

The generated header contains a static array that firmware can directly
include and use in its control loop, bypassing SDK and communication stack.

Usage:
    python python/revo3/mit_debug/trajectory_to_c.py trajectory.json
    python python/revo3/mit_debug/trajectory_to_c.py trajectory.json -o firmware_trajectory.h
    python python/revo3/mit_debug/trajectory_to_c.py trajectory.json --freq 200
"""

import json
import argparse
import numpy as np
from pathlib import Path


def load_trajectory(filepath):
    with open(filepath) as f:
        data = json.load(f)
    frames = [(f["t"], f["pos"]) for f in data["frames"]]
    motor_count = data.get("motor_count", len(frames[0][1]))
    return frames, motor_count


def resample(frames, target_freq):
    """Resample trajectory to uniform time steps at target_freq Hz."""
    if not frames:
        return frames

    duration = frames[-1][0]
    motor_count = len(frames[0][1])
    dt = 1.0 / target_freq
    n_samples = int(duration * target_freq) + 1

    # Build time arrays
    src_times = np.array([f[0] for f in frames])
    src_positions = np.array([f[1] for f in frames])  # (N, motors)

    target_times = np.linspace(0, duration, n_samples)
    resampled = []

    for t in target_times:
        # Linear interpolation
        pos = np.interp(t, src_times, src_positions.T[0])  # placeholder
        interp_pos = [float(np.interp(t, src_times, src_positions[:, m]))
                      for m in range(motor_count)]
        resampled.append((float(t), interp_pos))

    return resampled


def generate_header(frames, motor_count, freq, source_file):
    """Generate C header file content."""
    n = len(frames)
    dt_ms = round(1000.0 / freq) if freq else 0

    lines = []
    lines.append("/**")
    lines.append(f" * Auto-generated trajectory data from: {source_file}")
    lines.append(f" * Frames: {n}, Motors: {motor_count}, Duration: {frames[-1][0]:.2f}s")
    if freq:
        lines.append(f" * Resampled to {freq} Hz (dt = {dt_ms} ms)")
    lines.append(" *")
    lines.append(" * Usage in firmware:")
    lines.append(" *   #include \"trajectory_data.h\"")
    lines.append(" *   for (int i = 0; i < TRAJ_FRAME_COUNT; i++) {")
    lines.append(f" *       set_motor_positions(TRAJ_DATA[i], {motor_count});")
    lines.append(f" *       delay_ms({dt_ms if dt_ms else 'TRAJ_DT_MS'});")
    lines.append(" *   }")
    lines.append(" */")
    lines.append("")
    lines.append("#pragma once")
    lines.append("")
    lines.append(f"#define TRAJ_MOTOR_COUNT  {motor_count}")
    lines.append(f"#define TRAJ_FRAME_COUNT  {n}")
    lines.append(f"#define TRAJ_DURATION_MS  {int(frames[-1][0] * 1000)}")

    if freq:
        lines.append(f"#define TRAJ_FREQ_HZ      {freq}")
        lines.append(f"#define TRAJ_DT_MS        {dt_ms}")

    lines.append("")
    lines.append(f"static const float TRAJ_TIMESTAMPS[{n}] = {{")

    # Timestamps
    for i in range(0, n, 10):
        chunk = frames[i:i+10]
        vals = ", ".join(f"{f[0]:.4f}f" for f in chunk)
        lines.append(f"    {vals},")
    lines.append("};")

    lines.append("")
    lines.append(f"static const float TRAJ_DATA[{n}][{motor_count}] = {{")

    # Position data
    for i, (t, pos) in enumerate(frames):
        vals = ", ".join(f"{p:.2f}f" for p in pos[:motor_count])
        lines.append(f"    {{ {vals} }},  // frame {i}, t={t:.4f}s")

    lines.append("};")
    lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Convert trajectory JSON to C header for firmware playback"
    )
    parser.add_argument("input", help="Input trajectory JSON file")
    parser.add_argument("-o", "--output", help="Output .h file (default: trajectory_data.h)")
    parser.add_argument("--freq", type=int, default=0,
                        help="Resample to uniform frequency (Hz). 0 = keep original timestamps")
    parser.add_argument("--motors", type=int, default=0,
                        help="Override motor count (0 = auto-detect from data)")
    args = parser.parse_args()

    frames, motor_count = load_trajectory(args.input)
    if args.motors > 0:
        motor_count = args.motors

    print(f"Loaded: {len(frames)} frames, {motor_count} motors, {frames[-1][0]:.2f}s duration")

    if args.freq > 0:
        frames = resample(frames, args.freq)
        print(f"Resampled to {args.freq} Hz: {len(frames)} frames")

    output = args.output or "trajectory_data.h"
    header = generate_header(frames, motor_count, args.freq, Path(args.input).name)

    with open(output, "w") as f:
        f.write(header)

    print(f"Generated: {output} ({len(frames)} frames × {motor_count} motors)")
    print(f"\nFirmware usage:")
    print(f"  #include \"{output}\"")
    print(f"  // Loop TRAJ_DATA[i] at TRAJ_DT_MS interval")


if __name__ == "__main__":
    main()
