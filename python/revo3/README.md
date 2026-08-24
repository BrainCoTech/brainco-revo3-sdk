# Revo3 Python 2.0 Examples

These examples use the public 2.0 object model:

`Manager -> Hand -> Motion/State/Touch/Health/Config/Calibration/Maintenance`

They do not carry a `DeviceContext` or `slave_id` through device operations,
and object methods do not use the Legacy `revo3_` prefix.

## Recommended Examples

| File | Purpose |
| --- | --- |
| `quickstart.py` | Connect, inspect layouts, read State and Health, and optionally move |
| `discover_devices.py` | Read-only device discovery and connection troubleshooting |
| `multi_hand.py` | Multiple Hand lifecycle and shared transport behavior |
| `subscriptions.py` | Finite State, optional Touch, and Health subscriptions |
| `concurrent_control.py` | Concurrent servo control and State reads |
| `touch_sensor.py` | Typed Touch layouts and snapshots |
| `device_operations.py` | Config, runtime statistics, calibration, and reboot |
| `teaching_mode.py` | Teach and Replay operations |
| `shared_ports.py` | Trusted serial port listing and VID/PID allowlist |
| `manager_cli.py` | JSONL recording, replay, and diagnostic bundles |
| `streaming_control.py` | Position streaming and Servo command timeout behavior |
| `mit_plan.py` | Quintic full-hand MIT impedance streaming and feedback observation |
| `units.py` | Offline scalar and batch unit conversions |

These are the customer-facing entry points maintained as the primary 2.0
examples. They do not use an adapter, operation-level `slave_id`, a collector,
or a State buffer.

`mit_plan.py` shares its default motion contract with the C++ `mit_plan.cpp`
example. Python additionally exposes `--joint`, `--range-fraction`,
`--duration`, `--repeat`, `--frequency`, `--command-timeout-ms`, `--kp`, and
`--kd` for explicit tuning. `--range-fraction` is limited to `0.05~0.95`.
Before opening a ServoSession, the example validates the initial feedback and
generated quintic peak velocity against the configured position and speed
envelopes. The command timeout must be at least one requested send period.

## Specialized Workflows

| File | Purpose |
| --- | --- |
| `trajectory_control.py` | Run an explicitly enabled joint and full-hand trajectory sequence |
| `firmware_update.py` | Update a selected main, image, or motor firmware target |
| `finger_motion.py` | Run an explicitly enabled finger and thumb motion workflow |
| `touch_hybrid.py` | Verify a confirmed `hp_*` + `mt_*` hybrid touch layout |

`firmware_update.py` requires `--run`, defaults to the `main` target, and also
supports `--target image` and `--target motor`. An `Indeterminate` result does
not prove that the device rejected the update; inspect the structured error and
verify device state before retrying.

Shared connection and cleanup helpers live in `python/common_init.py`.

Minimal Python usage:

```python
import asyncio
from bc_revo3_sdk import main_mod as sdk


async def main():
    manager = sdk.Manager()
    hand = None
    try:
        hand = await manager.connect_auto()
        device_info = hand.device_info
        firmware_info = hand.firmware_info
        state = await hand.state.snapshot()
        health = await hand.health.snapshot()
        print(device_info.serial_number, firmware_info.controller_firmware_version)
        print(state.positions_deg, health.safety_state)
    finally:
        if hand is not None:
            await hand.close()
        await manager.close()


asyncio.run(main())
```

## Run

From the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install ./python
python python/revo3/quickstart.py --help
python python/revo3/quickstart.py
```

On Windows PowerShell, create the environment with `py -3.10 -m venv .venv`
and activate it with `.venv\Scripts\Activate.ps1`.

Connection alone never sends a motion command. Examples that move, calibrate,
reboot, or update firmware require explicit command-line flags. Read State after
an `SdkError` whose `operation_effect` is `Indeterminate` before deciding
whether a command should be retried.

`quickstart.py` is the only ten-minute quick-start entry point. Use
`discover_devices.py` only when connection discovery needs troubleshooting.

`touch_hybrid.py` requires a hardware layout confirmed from the target hand's
BOM or validation record. Its `set_layout()` call changes only SDK parsing for
the current connection session. `--test-tare` changes calibration state, and
`--test-modes` changes the `mt_*` read mode; both are disabled by default.

## Troubleshooting & Serial Port Cleanup

If connection fails with `Failed to open ... at 5000000 bps: Invalid argument` or `No Revo3 device detected`, check if another process holds an open file descriptor on the serial port:

```bash
# 1. Find process holding the serial port
lsof /dev/tty.usbserial*

# 2. Terminate the process
kill -9 <PID>
```

Always call `hand.close()` and `manager.close()` in `try...finally` blocks or use async context managers.
