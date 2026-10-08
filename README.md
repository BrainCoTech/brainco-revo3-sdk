# BrainCo Revo3 SDK Examples

[English](README.md) | [简体中文](README.zh-CN.md)

This repository provides example applications and integration code demonstrating how to control BrainCo Revo3 dexterous hands using the SDK.

## Layout

- `c/` - C++ examples using the C ABI, plus a standalone Linux EtherCAT example
- `python/revo3/` - Python Revo3 demos
- `python/gui/` - PySide GUI with Revo3 panels and mock mode

For installation, integration guidance, and the Python and C/C++ API reference,
see the [Revo 3 SDK documentation](https://app.brainco.cn/universal/bc-revo3-sdk/docs/site/).
For hardware registers and transport details, see the
[Revo 3 communication protocol](https://www.brainco-hz.com/docs/revolimb-hand/revo3/protocol.html).

## Motion Demonstrations

The Python and C++ motion demonstrations preview offline by default and do not
connect to hardware unless `--run` is supplied:

```bash
python python/revo3/gesture_dance_demo.py
./c/build/demo/gesture_dance_demo
```

See the [motion demonstration guide](python/revo3/MOTION_DEMOS.md)
([简体中文](python/revo3/MOTION_DEMOS.zh-CN.md)) for the choreography, candidate
pose calibration, hardware checks, interruption behavior, and Python/C++
differences.

## Getting Started

### C++

```bash
bash download-lib.sh
make -C c
./c/build/demo/quickstart
./c/build/demo/quickstart --move
./c/build/demo/discover_devices --scan-all
./c/build/demo/subscriptions --count 3
./c/build/demo/multi_hand
./c/build/demo/device_operations --help
./c/build/demo/firmware_update --help
./c/build/demo/touch_sensor
./c/build/demo/streaming_control --move
```

The pure C++ IgH EtherCAT example is built separately because it does not use
the downloaded SDK library. Before running it, verify the IgH master,
`/dev/EtherCAT0`, and the selected NIC with `c/platform/linux/revo3_ec/README.md`:

```bash
make -C c/platform/linux/revo3_ec
./c/platform/linux/revo3_ec/revo3_pdo 0
./c/platform/linux/revo3_ec/revo3_benchmark \
  --scenario motor --read full-state --duration 10
```

### Python

#### 1. Install the SDK

Create and activate an isolated Python environment first:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

On Windows PowerShell, use `py -3.10 -m venv .venv` and
`.venv\Scripts\Activate.ps1`.

Install the release-matched wheel from Ali OSS:

```bash
bash python/install_whl.sh 2.1.1
```

#### 2. Run examples

```bash
cd python
python -m pip install .

# Run Revo3 2.x Manager examples (requires a real Revo3 device)
python revo3/quickstart.py
python revo3/discover_devices.py --help
python revo3/subscriptions.py --help
python revo3/touch_sensor.py
python revo3/device_operations.py --help
python revo3/firmware_update.py --help
python revo3/mit_plan.py --help

# Run GUI in real-device mode (requires a connected Revo3 device)
python -m pip install '.[gui]'
python gui/main.py
```

The Python `mit_plan.py` and C++ `mit_plan.cpp` examples share the same
default quintic MIT impedance plan: 100 Hz, the 50% point of each target
joint's configured position range, 800 ms per outbound/return segment,
`Kp=3.0`, `Kd=0.3`, and zero feedforward current. The reusable C++ sampler is
in `c/common/revo3_mit_plan.hpp`. Initial-position tolerance defaults to 0.1
degrees; accepted out-of-range feedback is clamped to the nearest configured
limit before motion.

## Single-command control (SDK 2.1.1)

`discrete_control` sends one full-hand position, current, or MIT command without
`open_servo()`, a heartbeat, or automatic resend. It requires a powered 21-DOF
Revo3 hand and an SDK-supported transport on Linux, macOS, or Windows. This
release was verified with UV5 firmware 0.1.2 over Modbus; CANFD hardware
validation remains pending.

The default reads the current pose without writing. Add `--run` to send the
current pose in position mode, zero current in current mode, or the current
pose with kp=1, kd=0.1 and zero velocity/feedforward current in MIT mode.
Even these targets can change hand support or motor behavior; clear the workspace.
Arrays use logical joint order, degrees, rpm, and mA; MIT's fifth array is
feedforward current in mA. Firmware determines target retention. Closing the
connection does not stop control; plan stopping with the documented safety API.
On an error, inspect state before retrying because a command may have taken effect.

```bash
python python/revo3/discrete_control.py --mode mit --help
```

The firmware update example now reports transfer progress. 100% means transfer
completion; reconnect and read the installed firmware version to verify success.
