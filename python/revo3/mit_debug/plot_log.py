"""
Plot MIT impedance tracking log files.

Three subplots:
  1. Position tracking (ref_pos vs act_pos)
  2. Velocity tracking (ref_vel vs act_vel)
  3. Current (act_cur)

Usage:
    python revo3/mit_debug/plot_log.py log/mit_track_j3.txt
    python revo3/mit_debug/plot_log.py    # auto-detect latest log
"""

import sys
import os
import glob
import numpy as np
import matplotlib.pyplot as plt

LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "log")


def find_latest_log() -> str:
    """Return the most recently modified log file in LOG_DIR."""
    pattern = os.path.join(LOG_DIR, "mit_track_*.txt")
    files = sorted(glob.glob(pattern), key=os.path.getmtime)
    if not files:
        print(f"No log files found in {LOG_DIR}")
        sys.exit(1)
    return files[-1]


def parse_log(filepath: str):
    """Parse a mit_track log file.

    Returns:
        (header_info, t, ref_pos, ref_vel, act_pos, act_vel, act_cur)
    """
    header_info = ""
    t, ref_pos, ref_vel, act_pos, act_vel, act_cur = [], [], [], [], [], []
    with open(filepath, "r") as f:
        for line in f:
            if line.startswith("# joint_id"):
                header_info = line.strip("# \n")
                continue
            if line.startswith("#"):
                continue
            parts = line.split()
            if len(parts) < 6:
                continue
            t.append(float(parts[0]))
            ref_pos.append(float(parts[1]))
            ref_vel.append(float(parts[2]))
            act_pos.append(float(parts[3]))
            act_vel.append(float(parts[4]))
            act_cur.append(float(parts[5]))
    return (header_info,
            np.array(t), np.array(ref_pos), np.array(ref_vel),
            np.array(act_pos), np.array(act_vel), np.array(act_cur))


def main():
    filepath = sys.argv[1] if len(sys.argv) > 1 else find_latest_log()
    print(f"Plotting: {filepath}")

    header, t, ref_pos, ref_vel, act_pos, act_vel, act_cur = parse_log(filepath)
    if len(t) == 0:
        print("No data points found in log.")
        sys.exit(1)

    fig, axes = plt.subplots(3, 1, figsize=(12, 8), sharex=True)
    fig.suptitle(f"MIT Impedance Tracking\n{header}", fontsize=10)

    # -- Position --
    ax = axes[0]
    ax.plot(t, ref_pos, "b-", label="ref", linewidth=1.5)
    ax.plot(t, act_pos, "r-", label="actual", linewidth=1.0, alpha=0.8)
    ax.set_ylabel("Position (°)")
    ax.legend(loc="upper right")
    ax.grid(True, alpha=0.3)

    # -- Velocity --
    ax = axes[1]
    ax.plot(t, ref_vel, "b-", label="ref", linewidth=1.5)
    ax.plot(t, act_vel, "r-", label="actual", linewidth=1.0, alpha=0.8)
    ax.set_ylabel("Velocity (rpm)")
    ax.legend(loc="upper right")
    ax.grid(True, alpha=0.3)

    # -- Current --
    ax = axes[2]
    ax.plot(t, act_cur, "g-", label="current", linewidth=1.0)
    ax.set_ylabel("Current (mA)")
    ax.set_xlabel("Time (s)")
    ax.legend(loc="upper right")
    ax.grid(True, alpha=0.3)

    plt.tight_layout()

    def on_key(event):
        if event.key == "s":
            img_path = filepath.replace(".txt", ".png")
            fig.savefig(img_path, dpi=150)
            print(f"Saved: {img_path}")

    fig.canvas.mpl_connect("key_press_event", on_key)
    print("Press S to save image")
    plt.show()


if __name__ == "__main__":
    main()
