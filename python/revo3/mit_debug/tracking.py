"""
MIT Impedance Control – Quintic Trajectory Tracking (New Revo3 Protocol)

Drive a single joint along a quintic-polynomial trajectory using
revo3_joint_mit_control, while recording ref/actual data to a log file.

MIT torque law:
    tau = Kp * (P_ref - P_act) + Kd * (V_ref - V_act) + T_ff

Usage:
    python revo3/mit_debug/tracking.py
    python revo3/mit_debug/tracking.py --joint 3 --target 60 --duration 2.0
    python revo3/mit_debug/tracking.py --kp 5.0 --kd 0.5
    python revo3/mit_debug/tracking.py --port /dev/ttyUSB0
"""

import sys
import os
import subprocess
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import asyncio
import argparse
import time
from revo3.revo3_utils import logger, libstark, open_modbus_revo3
from revo3.mit_debug.trajectory import QuinticTrajectory

LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "log")

# ---------------------------------------------------------------------------
# Per-joint safe range and default close position
# Derived from hardware register spec (Reg 240–260: min, Reg 270–290: max)
# ---------------------------------------------------------------------------
JOINT_RANGES = {
    # Side-swing joints: [-15, 15] deg
    0: (-15, 15), 4: (-15, 15), 8: (-15, 15), 12: (-15, 15),
    # Standard flex joints: [0, 90] deg
    1: (0, 90), 2: (0, 90), 3: (0, 90),
    5: (0, 90), 6: (0, 90), 7: (0, 90),
    9: (0, 90), 10: (0, 90), 11: (0, 90),
    13: (0, 90), 14: (0, 90), 15: (0, 90),
    17: (0, 90), 18: (0, 90),
    # Thumb special joints
    16: (0, 50),    # thumb root
    19: (0, 105),   # thumb diff-1
    20: (0, 120),   # thumb diff-2
}

JOINT_CLOSE_POS = {
    0: 12.0, 4: 12.0, 8: 12.0, 12: 12.0,   # side-swing
    1: 80.0, 2: 80.0, 3: 80.0,
    5: 80.0, 6: 80.0, 7: 80.0,
    9: 80.0, 10: 80.0, 11: 80.0,
    13: 80.0, 14: 80.0, 15: 80.0,
    17: 80.0, 18: 80.0,
    16: 40.0, 19: 90.0, 20: 100.0,
}

JOINT_OPEN_POS = 0.0

# Velocity unit conversion: trajectory outputs deg/s, firmware expects rpm
DPS_TO_RPM = 1.0 / 6.0   # 1 rpm = 6 deg/s


async def run(port_name=None, joint_id=3, target_pos=None, open_pos=None,
              duration=2.0, kp=5.0, kd=0.5, freq=200, repeat=3,
              full_status=False, auto_plot=True):
    """Execute MIT tracking and write log.

    Args:
        full_status: If True, read full motor status (pos+vel+cur, 4 Modbus reads).
                     If False (default), read positions only (1 Modbus read, ~3x faster).
    """

    client, slave_id = await open_modbus_revo3(port_name=port_name)
    logger.info(f"Connected. slave_id={slave_id}")

    # Resolve positions
    jrange = JOINT_RANGES.get(joint_id, (0, 90))
    if target_pos is None:
        target_pos = JOINT_CLOSE_POS.get(joint_id, 80.0)
    if open_pos is None:
        open_pos = JOINT_OPEN_POS

    logger.info(f"Joint {joint_id}: range={jrange}, "
                f"open={open_pos:.1f} deg, close={target_pos:.1f} deg")

    # Read current position for the log header
    status = await client.revo3_get_motor_status_data(slave_id)
    start_pos = status.positions[joint_id]

    logger.info(f"Joint {joint_id}: cur={start_pos:.2f} deg, target={target_pos:.2f} deg, "
                f"T={duration:.2f}s, Kp={kp}, Kd={kd}, freq={freq}Hz, repeat={repeat}")

    dt = 1.0 / freq
    records = []          # (t, ref_pos, ref_vel, act_pos, act_vel, act_cur)
    global_t0 = time.perf_counter()
    total_loops = 0
    total_write_time = 0.0
    total_read_time = 0.0

    try:
        for rep in range(repeat):
            # Alternate direction each cycle
            if rep % 2 == 0:
                p0, p1 = open_pos, target_pos
            else:
                p0, p1 = target_pos, open_pos

            logger.info(f"[{rep+1}/{repeat}] {p0:.1f} -> {p1:.1f} deg")
            traj = QuinticTrajectory(p0, p1, duration)

            t0 = time.perf_counter()
            loop_n = 0

            while True:
                t_now = time.perf_counter() - t0
                t_log = time.perf_counter() - global_t0

                if t_now > duration + 0.5:
                    break

                ref_p, ref_v_dps = traj.get(t_now)
                ref_v = ref_v_dps * DPS_TO_RPM

                t_w_start = time.perf_counter()
                # Send MIT command (torque_ff = 0)
                await client.revo3_joint_mit_control(
                    slave_id, joint_id,
                    kp, kd,
                    ref_p, ref_v,
                    0.0,
                )
                t_r_start = time.perf_counter()

                # Read actual state
                if full_status:
                    status = await client.revo3_get_motor_status_data(slave_id)
                    act_pos = status.positions[joint_id]
                    act_vel = status.velocities[joint_id]
                    act_cur = status.currents[joint_id]
                else:
                    positions = await client.revo3_get_all_motor_positions(slave_id)
                    act_pos = positions[joint_id]
                    act_vel = 0.0
                    act_cur = 0.0
                t_r_end = time.perf_counter()

                total_write_time += (t_r_start - t_w_start)
                total_read_time += (t_r_end - t_r_start)

                records.append((t_log, ref_p, ref_v, act_pos, act_vel, act_cur))
                loop_n += 1

                # Absolute-time rate control
                next_tick = t0 + loop_n * dt
                sleep_s = next_tick - time.perf_counter()
                if sleep_s > 0:
                    await asyncio.sleep(sleep_s)

            total_loops += loop_n
            hz = loop_n / (time.perf_counter() - t0) if loop_n else 0
            logger.info(f"[{rep+1}/{repeat}] {loop_n} loops, {hz:.1f} Hz")

    except KeyboardInterrupt:
        logger.info("Interrupted by user.")

    # Release motor (zero gains → zero torque)
    await client.revo3_joint_mit_control(slave_id, joint_id, 0.0, 0.0, 0.0, 0.0, 0.0)

    total_t = time.perf_counter() - global_t0
    avg_hz = total_loops / total_t if total_loops else 0

    avg_write_t = total_write_time / total_loops if total_loops else 0
    write_hz = 1.0 / avg_write_t if avg_write_t > 0 else 0

    avg_read_t = total_read_time / total_loops if total_loops else 0
    read_hz = 1.0 / avg_read_t if avg_read_t > 0 else 0

    avg_io_t = avg_write_t + avg_read_t
    io_hz = 1.0 / avg_io_t if avg_io_t > 0 else 0

    logger.info(f"Done. {repeat} reps, {total_loops} loops")
    logger.info(f"  System Freq (with sleep): {avg_hz:.1f} Hz")
    logger.info(f"  IO Freq (Write+Read):     {io_hz:.1f} Hz")
    logger.info(f"  - Write-only Freq:        {write_hz:.1f} Hz ({avg_write_t*1000:.2f}ms/op)")
    logger.info(f"  - Read-only Freq:         {read_hz:.1f} Hz ({avg_read_t*1000:.2f}ms/op)")

    # ---- Save log ----
    os.makedirs(LOG_DIR, exist_ok=True)
    log_file = os.path.join(LOG_DIR, f"mit_track_j{joint_id}.txt")

    with open(log_file, "w") as f:
        f.write(f"# joint_id={joint_id} start={start_pos:.2f} target={target_pos:.2f} ")
        f.write(f"# T={duration} kp={kp} kd={kd} freq={freq} repeat={repeat} full_status={full_status}\n")
        f.write(f"# actual_hz={avg_hz:.1f} io_hz={io_hz:.1f} write_hz={write_hz:.1f} read_hz={read_hz:.1f}\n")
        f.write("# t  ref_pos  ref_vel  act_pos  act_vel  act_cur\n")
        for row in records:
            f.write(f"{row[0]:.4f}  {row[1]:.4f}  {row[2]:.4f}  "
                    f"{row[3]:.4f}  {row[4]:.4f}  {row[5]:.4f}\n")

    logger.info(f"Log saved: {log_file}")

    # Auto-launch plotter
    if auto_plot:
        plot_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "plot_log.py")
        logger.info("Launching plotter...")
        subprocess.Popen([sys.executable, plot_script, log_file])

    libstark.modbus_close(client)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="MIT impedance control with quintic trajectory tracking",
        epilog="If --target is omitted, a per-joint safe close position is used automatically.")
    parser.add_argument("--port",     type=str,   default=None, help="Serial port")
    parser.add_argument("--joint",    type=int,   default=3,    help="Joint ID (0-20)")
    parser.add_argument("--target",   type=float, default=None, help="Target angle (deg)")
    parser.add_argument("--open-pos", type=float, default=None, help="Open/return angle (deg), default 0")
    parser.add_argument("--duration", type=float, default=2.0,  help="Trajectory duration (s)")
    parser.add_argument("--kp",       type=float, default=5.0,  help="MIT Kp (position stiffness)")
    parser.add_argument("--kd",       type=float, default=0.5,  help="MIT Kd (velocity damping)")
    parser.add_argument("--freq",     type=int,   default=200,  help="Control frequency (Hz)")
    parser.add_argument("--repeat",   type=int,   default=3,    help="Number of oscillation cycles")
    parser.add_argument("--no-plot",  action="store_true",      help="Skip auto-launch plotter")
    parser.add_argument("--full-status", action="store_true",
                        help="Read full motor status (pos+vel+cur); default: position only (faster)")
    args = parser.parse_args()

    asyncio.run(run(
        port_name=args.port,
        joint_id=args.joint,
        target_pos=args.target,
        open_pos=args.open_pos,
        duration=args.duration,
        kp=args.kp,
        kd=args.kd,
        freq=args.freq,
        repeat=args.repeat,
        full_status=args.full_status,
        auto_plot=not args.no_plot,
    ))
