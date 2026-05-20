"""Analyze trajectory JSON from revo3_teaching.py — quantify jitter.

Reads a recorded trajectory file (from teaching mode playback),
computes jitter metrics per motor, and generates a summary report.

Usage:
    python scripts/jitter_analysis.py trajectory.json
    python scripts/jitter_analysis.py trajectory.json --plot
    python scripts/jitter_analysis.py baseline.json optimized.json  # A/B comparison
"""

import json
import argparse
import numpy as np
from pathlib import Path


def load_trajectory(filepath):
    """Load trajectory JSON and return (timestamps, positions_array)."""
    with open(filepath) as f:
        data = json.load(f)
    frames = data["frames"]
    motor_count = data.get("motor_count", len(frames[0]["pos"]))
    t = np.array([f["t"] for f in frames])
    pos = np.array([f["pos"][:motor_count] for f in frames])  # (N, motors)
    return t, pos, motor_count


def compute_jitter_metrics(t, pos):
    """Compute per-motor jitter metrics.

    Returns dict with per-motor stats:
      - velocity_rms: RMS of velocity (proxy for smoothness)
      - accel_rms: RMS of acceleration (jitter indicator)
      - accel_peak: peak acceleration (worst jitter)
      - position_noise_std: std of position after detrending
    """
    dt = np.diff(t)
    dt[dt == 0] = 1e-6  # avoid division by zero

    n_motors = pos.shape[1]
    metrics = []

    for m in range(n_motors):
        p = pos[:, m]

        # Velocity and acceleration via finite differences
        vel = np.diff(p) / dt
        accel = np.diff(vel) / dt[1:]

        # Position noise: detrend with moving average then take std
        window = min(20, len(p) // 4)
        if window > 1:
            kernel = np.ones(window) / window
            smooth = np.convolve(p, kernel, mode="same")
            noise = p - smooth
        else:
            noise = p - np.mean(p)

        metrics.append({
            "motor": m,
            "pos_range": float(np.ptp(p)),
            "pos_noise_std": float(np.std(noise)),
            "vel_rms": float(np.sqrt(np.mean(vel**2))),
            "vel_peak": float(np.max(np.abs(vel))),
            "accel_rms": float(np.sqrt(np.mean(accel**2))) if len(accel) > 0 else 0,
            "accel_peak": float(np.max(np.abs(accel))) if len(accel) > 0 else 0,
        })

    return metrics


MOTOR_LABELS = {
    0: "Pinky-Abd", 1: "Pinky-MCP", 2: "Pinky-PIP", 3: "Pinky-DIP",
    4: "Ring-Abd",  5: "Ring-MCP",  6: "Ring-PIP",  7: "Ring-DIP",
    8: "Mid-Abd",   9: "Mid-MCP",  10: "Mid-PIP",  11: "Mid-DIP",
    12: "Idx-Abd",  13: "Idx-MCP",  14: "Idx-PIP",  15: "Idx-DIP",
    16: "Thb-Rot",  17: "Thb-MCP",  18: "Thb-IP",
    19: "Thb-Abd",  20: "Thb-Flex",
    21: "Wrist-FE", 22: "Wrist-Abd",
}


def print_report(metrics, title="Jitter Analysis"):
    """Print formatted jitter report."""
    print(f"\n{'='*72}")
    print(f"  {title}")
    print(f"{'='*72}")
    print(f"{'Motor':<14} {'Range°':>8} {'Noise σ':>8} {'Vel RMS':>9} {'Acc RMS':>10} {'Acc Peak':>10}")
    print(f"{'-'*14} {'-'*8} {'-'*8} {'-'*9} {'-'*10} {'-'*10}")

    # Sort by accel_rms descending (worst jitter first)
    sorted_metrics = sorted(metrics, key=lambda x: x["accel_rms"], reverse=True)

    for m in sorted_metrics:
        label = MOTOR_LABELS.get(m["motor"], f"M{m['motor']}")
        flag = " ⚠️" if m["accel_rms"] > 1000 else ""
        print(f"{label:<14} {m['pos_range']:>7.1f}° {m['pos_noise_std']:>7.3f}° "
              f"{m['vel_rms']:>8.1f}  {m['accel_rms']:>9.1f}  {m['accel_peak']:>9.1f}{flag}")

    # Summary
    worst = sorted_metrics[0]
    worst_label = MOTOR_LABELS.get(worst["motor"], f"M{worst['motor']}")
    avg_accel = np.mean([m["accel_rms"] for m in metrics])
    print(f"\nWorst jitter: {worst_label} (accel RMS = {worst['accel_rms']:.1f})")
    print(f"Average accel RMS across all motors: {avg_accel:.1f}")

    # Flag MCP joints specifically
    mcp_motors = [1, 5, 9, 13, 17]  # MCP joints
    mcp_accels = [m["accel_rms"] for m in metrics if m["motor"] in mcp_motors]
    if mcp_accels:
        print(f"MCP joints avg accel RMS: {np.mean(mcp_accels):.1f}")


def compare_ab(metrics_a, metrics_b, title_a="Baseline", title_b="Optimized"):
    """Print A/B comparison."""
    print(f"\n{'='*72}")
    print(f"  A/B Comparison: {title_a} vs {title_b}")
    print(f"{'='*72}")
    print(f"{'Motor':<14} {'A Acc RMS':>10} {'B Acc RMS':>10} {'Δ%':>8} {'Result':>8}")
    print(f"{'-'*14} {'-'*10} {'-'*10} {'-'*8} {'-'*8}")

    improvements = 0
    for ma, mb in zip(metrics_a, metrics_b):
        label = MOTOR_LABELS.get(ma["motor"], f"M{ma['motor']}")
        a_val = ma["accel_rms"]
        b_val = mb["accel_rms"]
        if a_val > 0:
            pct = (b_val - a_val) / a_val * 100
        else:
            pct = 0
        result = "✅ better" if pct < -5 else ("⚠️ worse" if pct > 5 else "— same")
        if pct < -5:
            improvements += 1
        print(f"{label:<14} {a_val:>9.1f}  {b_val:>9.1f}  {pct:>+6.1f}%  {result}")

    print(f"\nImproved: {improvements}/{len(metrics_a)} motors")


def plot_jitter(t, pos, metrics, title="Jitter"):
    """Generate jitter visualization (requires matplotlib)."""
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib not installed, skipping plots")
        return

    # Top 4 worst motors by accel_rms
    sorted_m = sorted(metrics, key=lambda x: x["accel_rms"], reverse=True)[:4]

    fig, axes = plt.subplots(4, 2, figsize=(14, 10))
    fig.suptitle(title, fontsize=14)

    for i, m in enumerate(sorted_m):
        idx = m["motor"]
        label = MOTOR_LABELS.get(idx, f"M{idx}")
        p = pos[:, idx]

        # Position
        axes[i, 0].plot(t, p, linewidth=0.5)
        axes[i, 0].set_ylabel(f"{label} (°)")
        axes[i, 0].set_title(f"{label} Position" if i == 0 else "")

        # Velocity
        dt = np.diff(t)
        dt[dt == 0] = 1e-6
        vel = np.diff(p) / dt
        axes[i, 1].plot(t[1:], vel, linewidth=0.5, color="orange")
        axes[i, 1].set_ylabel("°/s")
        axes[i, 1].set_title(f"{label} Velocity" if i == 0 else "")

    axes[-1, 0].set_xlabel("Time (s)")
    axes[-1, 1].set_xlabel("Time (s)")
    plt.tight_layout()

    out_path = f"jitter_report.png"
    plt.savefig(out_path, dpi=150)
    print(f"\nPlot saved: {out_path}")
    plt.close()


def main():
    parser = argparse.ArgumentParser(description="Analyze trajectory jitter")
    parser.add_argument("files", nargs="+", help="Trajectory JSON file(s). 1 file = report, 2 files = A/B comparison")
    parser.add_argument("--plot", action="store_true", help="Generate jitter plots (requires matplotlib)")
    args = parser.parse_args()

    if len(args.files) == 1:
        # Single file analysis
        t, pos, n = load_trajectory(args.files[0])
        print(f"Loaded: {len(t)} frames, {n} motors, {t[-1]:.2f}s")
        metrics = compute_jitter_metrics(t, pos)
        print_report(metrics, title=f"Jitter Analysis: {Path(args.files[0]).name}")
        if args.plot:
            plot_jitter(t, pos, metrics, title=Path(args.files[0]).name)

    elif len(args.files) == 2:
        # A/B comparison
        t_a, pos_a, n_a = load_trajectory(args.files[0])
        t_b, pos_b, n_b = load_trajectory(args.files[1])
        print(f"A: {len(t_a)} frames, {n_a} motors | B: {len(t_b)} frames, {n_b} motors")
        metrics_a = compute_jitter_metrics(t_a, pos_a)
        metrics_b = compute_jitter_metrics(t_b, pos_b)
        print_report(metrics_a, title=f"A: {Path(args.files[0]).name}")
        print_report(metrics_b, title=f"B: {Path(args.files[1]).name}")
        compare_ab(metrics_a, metrics_b,
                    title_a=Path(args.files[0]).stem,
                    title_b=Path(args.files[1]).stem)
        if args.plot:
            plot_jitter(t_a, pos_a, metrics_a, title=f"A: {Path(args.files[0]).name}")
            plot_jitter(t_b, pos_b, metrics_b, title=f"B: {Path(args.files[1]).name}")


if __name__ == "__main__":
    main()
