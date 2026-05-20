# MIT Impedance Control Debug Tools

Debug and tune MIT impedance control parameters for Revo3 joints.

## Files

| File | Description |
|------|-------------|
| `tracking.py` | Run quintic trajectory tracking with MIT control, log ref/actual data |
| `plot_log.py` | Plot logged data (position, velocity, current) |
| `trajectory.py` | Quintic polynomial interpolator (zero boundary vel/accel) |

## Quick Start

```bash
cd python

# Run tracking on joint 3 (auto-selects safe target position)
python revo3/mit_debug/tracking.py

# Specify joint, target angle, and MIT gains
python revo3/mit_debug/tracking.py --joint 3 --target 60 --kp 5.0 --kd 0.5

# Multiple oscillation cycles with custom duration
python revo3/mit_debug/tracking.py --joint 3 --repeat 5 --duration 3.0

# Plot a specific log file
python revo3/mit_debug/plot_log.py log/mit_track_j3.txt

# Plot the latest log (auto-detect)
python revo3/mit_debug/plot_log.py
```

## CLI Arguments (`tracking.py`)

| Argument | Default | Description |
|----------|---------|-------------|
| `--port` | auto | Serial port |
| `--joint` | 3 | Joint ID (0–20) |
| `--target` | auto | Target angle (°), auto-selected from safe range if omitted |
| `--open-pos` | 0 | Open/return angle (°) |
| `--duration` | 2.0 | Trajectory duration (s) |
| `--kp` | 5.0 | Position stiffness gain |
| `--kd` | 0.5 | Velocity damping gain |
| `--freq` | 200 | Target control frequency (Hz) |
| `--repeat` | 3 | Number of oscillation cycles |
| `--no-plot` | — | Skip auto-launch plotter |

## MIT Control Law

```
τ = Kp × (P_ref − P_act) + Kd × (V_ref − V_act) + τ_ff
```

- **Position** is in degrees (°)
- **Velocity** is in rpm (converted from trajectory °/s internally)
- **Current/torque** is in mA

## Log Format

Logs are saved to `log/mit_track_j{id}.txt`:

```
# joint_id=3 start=0.00 target=80.00 T=2.0 kp=5.0 kd=0.5 freq=200 repeat=3 actual_hz=10.5
# t  ref_pos  ref_vel  act_pos  act_vel  act_cur
0.0000  0.0000  0.0000  0.1200  0.0000  0.0000
0.1050  2.3456  0.5678  1.8900  0.4500  12.3000
...
```
