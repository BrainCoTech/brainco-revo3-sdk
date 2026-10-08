# BrainCo Revo3 SDK 2.x Python Examples

[English](README.md) | [简体中文](README.zh-CN.md)

All examples use the 2.x `Manager -> Hand` object API.

## Install

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install ./python
```

On Windows PowerShell, create the environment with `py -3.10 -m venv .venv`
and activate it with `.venv\Scripts\Activate.ps1`.

For a local SDK build:

```bash
bash python/install_whl.sh
```

## Command Line

```bash
python python/revo3/quickstart.py
python python/revo3/touch_sensor.py
python python/revo3/streaming_control.py
```

See `python/revo3/README.md` for the full list.

For opposition, finger-function, gesture-dance, and classic-servo examples,
see the [motion demonstration guide](revo3/MOTION_DEMOS.md)
([简体中文](revo3/MOTION_DEMOS.zh-CN.md)). The demos preview offline unless
`--run` is supplied.

## GUI

The PySide GUI uses the same 2.x Manager/Hand API and does not depend on the
legacy `DeviceContext` layer.

```bash
python -m pip install './python[gui]'
python python/gui/main.py
```

Independent vision-tactile data channels and their platform-specific runtimes
are outside this SDK example package.

SDK 2.1.2 adds `revo3/discrete_control.py` for one position, current, or MIT command
without a Servo session. It defaults to read-only; `--run` explicitly enables writes.
See [the CLI examples](revo3/README.md) for units and stopping semantics.
`revo3/firmware_update.py` reports transfer progress; reconnect to verify the
installed version. `revo3/device_operations.py` refreshes motor SNs and versions
and reports partial refresh failures before reading the cached results.
