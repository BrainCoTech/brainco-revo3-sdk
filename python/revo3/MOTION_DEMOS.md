# Revo3 Motion Demonstrations

[English](MOTION_DEMOS.md) | [简体中文](MOTION_DEMOS.zh-CN.md)

Four Python examples use the SDK 2.x `Manager -> Hand` API for a 21-joint Revo3 hand. They default to offline preview without importing the SDK or connecting to a device. Pass `--run` to execute on hardware.

The built-in poses are unloaded candidate values. They have received limited right-hand testing but have not passed full-joint acceptance. Calibrate left and right hands separately; position limits alone do not prove that fingers cannot interfere.

| Entry point | Demonstration |
| --- | --- |
| `opposition_demo.py` | Thumb opposition and sequential approach toward the index, middle, ring, and little fingers |
| `finger_function_demo.py` | Individual finger flexion, claw and grasp shapes, finger spread, and lateral motion |
| `gesture_dance_demo.py` | Open palm, spread fingers, fist, V sign, and a sequential finger wave |
| `servo_classic_demo.py` | Classic sinusoidal servo motion with joint, amplitude, frequency, and filter controls |

Run commands from the repository root. Before hardware execution, activate a Python environment containing a compatible SDK.

```bash
# Offline preview; the SDK is not required
python python/revo3/opposition_demo.py
python python/revo3/finger_function_demo.py
python python/revo3/gesture_dance_demo.py
python python/revo3/servo_classic_demo.py

# Export a candidate right-hand opposition profile; refuse to overwrite an existing file
python python/revo3/opposition_demo.py --side right --export-profile /tmp/opposition-right.json

# After reviewing the profile, replace the port and device address
python python/revo3/opposition_demo.py --profile /tmp/opposition-right.json --side right --port /dev/ttyUSB0 --slave-id 127 --run

# Run the gesture dance twice at 0.5x speed
python python/revo3/gesture_dance_demo.py --tempo 0.5 --repeat 2 --side right --port /dev/ttyUSB0 --slave-id 127 --run

# Run four classic servo cycles on the index flexion joints at 0-30 degrees and 0.25 Hz
python python/revo3/servo_classic_demo.py --joints 13 14 15 --maximum 30 --frequency 0.25 --cycles 4 --side right --port /dev/ttyUSB0 --slave-id 127 --run
```

Connection uses `Manager.connect_auto()` discovery. Use `--port` and `--slave-id` to constrain the target. After connecting, the examples verify the 21-joint layout and `--side`. A left hand requires `--side left`; negating right-hand poses does not constitute left-hand adaptation. The built-in left and right templates use the same candidate logical angles. `side` prevents accidental misuse but does not indicate separate calibration. Pro, Basic, and other non-21-joint layouts are rejected.

## Pose Profiles And Opposition Calibration

The first three demos support `--export-profile` and `--profile`. A profile contains:

- `schema_version`: fixed at `1`.
- `kind`: `opposition`, `finger`, or `dance`; it must match the entry point.
- `side`: `left` or `right`; it must match the command line and hardware.
- `calibrated`: defaults to `false`; it records manual calibration status and is not software or hardware certification.
- `steps`: the motion list. Each step contains `name`, 21 `positions_deg` values, transition time `duration`, and dwell time `hold`.

The four-finger logical order is little finger J0-J3, ring J4-J7, middle J8-J11, and index J12-J15. Each finger uses `[Abd, MCP, PIP, DIP]`. Thumb J16-J20 uses `[Rotation, MCP, IP, Abd, Flex]`. Profiles always use logical joints rather than low-level channel numbers.

Begin calibration with the open-hand pose and one opposition step. At a reduced tempo, adjust the thumb and target finger gradually, verify clearance, and then expand to the full sequence. Calibrate all four opposition poses independently. The templates express motion intent; they do not calculate fingertip coordinates or use tactile feedback to detect contact. Opposition completion, grasp success, grip force, and collision avoidance require hardware validation. The examples do not support automatic object grasping or music synchronization.

## Continuous Dance And Staggered Opposition

The built-in finger-function, dance, and opposition profiles use `streaming: true` to send continuous MIT position and velocity targets. The dance transitions directly through grasp and claw shapes. Its wave uses three rounds of overlapping smooth pulses with 60/60/45-degree amplitudes and pauses only at display poses such as opposition and the V sign. Finger flexion starts 0.2 seconds after the thumb in dance opposition and 0.15 seconds after it in the standalone fast opposition segment, then decelerates smoothly near the endpoint. These trajectories do not detect contact, guarantee fingertip contact, or support object grasping.

Optional profile fields are `streaming` (Boolean), per-step `finger_delay` (finger-flexion delay in seconds, less than the transition duration), and `motion: "wave"` (three continuous wave rounds starting and ending at an open pose). The wave defaults to 6.5 seconds, with `duration` scaling the waveform. Older profiles without these fields retain the segmented path.

Use `--skip-joints`, for example `--skip-joints 2 12 20`, only for joints with a confirmed stall fault. The first three demos support this option. Skipped joints receive zero Kp, Kd, feedforward current, and target velocity; they no longer hold actively and are excluded from return-error checks. New motor, electrical, and system faults still stop execution. No joints are skipped by default, and the scripts do not clear faults or release software stop.

## Execution And Shutdown Behavior

Before the first motion, every target is checked against device position limits, and trajectories that exceed speed limits are lengthened. Segmented paths start from feedback, then check Health and endpoint error 0.25 seconds after the handle succeeds; an error above 5 degrees stops execution. Continuous paths start from a bounded initial pose, connect each step from the previous target, check Health about every 0.25 seconds, and validate position and speed limits on every send. They do not wait for feedback arrival at every step; only the final return checks non-skipped joints against the 5-degree threshold.

Continuous requests are sent about every 10 ms, subject to Python, Health-query, and transport timing. This is not a realtime guarantee. Command timeout is 500 ms. Execution is rejected while software stop or zero-force mode is active. On failure, the scripts attempt software stop and do not continue. `--tempo` scales transitions and dwell times while preserving speed limits; it does not change classic servo `--frequency`.

Normal completion returns smoothly to the startup feedback pose. `--feedback-tolerance-deg` defaults to `0` and accepts an explicit value from `0` to `2` for small initial-feedback violations near a limit. It does not relax target limits: feedback within tolerance is clamped to the nearest legal return target. For example, feedback at -0.2 degrees with a 0-degree lower limit returns to 0 degrees when tolerance is 0.5 degrees. Larger violations reject motion.

- `--finish hold` (default) retains the final trajectory `kp/kd` and does not enable zero-force mode. Whether holding continues after disconnect requires firmware validation.
- `--finish relax` explicitly enables zero-force mode after returning; this device state may persist after disconnect.

`--kp` defaults to `1.0` and `--kd` to `0.1`; both accept `0` through `10`. The scripts do not release software stop, clear device errors, or exit zero-force mode automatically. Confirm that the device is ready to move before running.

On motion failure, timeout, or Ctrl+C, the scripts cancel the active trajectory or close the servo session and attempt software stop. They do not continue the dance or return automatically. The stop attempt waits up to 3 seconds and reports failure explicitly. Software stop does not replace an independent stopping mechanism. Read device state after a failure before deciding whether to resume. Exit code `0` means preview/export or execution succeeded, `1` means error, and `130` means keyboard interruption.

## Relationship To 1.x Servo

The 1.x example sent the same 0-40-degree, 0.5 Hz sinusoidal target to all 21 joints at a requested 100 Hz. It used a second-order critically damped filter with `omega=25`, then sent zero position with `kp=1/kd=0` and waited 0.5 seconds.

The 2.x example retains sinusoidal motion, the requested send rate, and filter parameters. Defaults are 0-60 degrees, 0.75 Hz, and three cycles through `ServoSession.send_mit()`. Only the twelve four-finger flexion joints move by default; other joints hold their startup positions. A uniform 0-40-degree target is unsuitable for some lateral joints and is not restored as the all-joint default. `--joints` selects logical joints, but targets and peak speeds must pass device-limit checks.

The host implements the filter as an exact per-sample update of a second-order critically damped system under a constant target, producing both position and velocity. `--omega 0` disables it. The 2.x `ServoSession` does not expose the 1.x global filter setting, so this is not a point-for-point copy. The waveform begins at its minimum with zero velocity, enters smoothly, completes full cycles, and returns smoothly to the initial pose. Position is in degrees, velocity in rpm, and feedforward current is 0 mA.

`--rate` defaults to 100 Hz and accepts 1-200 Hz. Python and the transport do not guarantee realtime frequency. Missed samples are skipped rather than queued. Command timeout defaults to 200 ms; a send failure exits and attempts software stop.

## Default Motion Parameters

Python and C++ use the same default pose table. General transitions take 0.8 seconds with a 0.08-second dwell. Grasp MCP, PIP, and DIP amplitudes are 60, 60, and 45 degrees. Individual and collective lateral motions each repeat twice, take 0.35 seconds per swing, and add no dwell. Middle and ring lateral ranges are +/-12 degrees, little finger is -12 to +7 degrees, and index is -7 to +12 degrees.

The dance contains three overlapping smooth wave rounds lasting 6.5 seconds. Classic servo defaults to 0-60 degrees at 0.75 Hz for three cycles.

Standalone opposition first aligns the thumb for 0.6 seconds, completes the first 90% of flexion in 1.2 seconds and the final 10% in 0.35 seconds, holds for 0.5 seconds, and opens in 0.8 seconds. Device speed limits may extend these times. Index opposition uses thumb J16-J20 target `[73, 45, 40, 10, 15]` degrees and finger flexion `[75, 65, 50]` degrees. Middle, ring, and little opposition use thumb `[70, 40, 35, 10, 15]` degrees and target-finger flexion `[70, 60, 45]` degrees. These are uncalibrated candidate poses; `calibrated` defaults to `false`.

Defaults do not skip joints or release software stop, zero-force mode, or other device protection.

## Validation Scope

Offline regression covers SDK-free preview, profile I/O, position-limit rejection, speed calculation, sinusoid derivatives, filter convergence, model and side checks, timeout and cancellation handling, servo-failure cleanup, and connection release. It also covers overlapping wave derivatives, staggered opposition and endpoint velocity, zero gains on skipped joints, session close after send failure, and rejection under active motor faults, software stop, and zero-force mode.

Default poses have received limited unloaded execution on a right-hand device but have not passed acceptance with all 21 joints active. Left-hand mechanical adaptation, fingertip contact, object grasping, and persistent holding after disconnect remain unverified. Confirm clear finger travel and calibrate candidate poses gradually at reduced speed before running the examples.
