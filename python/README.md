# BrainCo Revo3 SDK 2.0 Python Examples

All customer examples use the 2.0 `Manager -> Hand` object API.

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

## GUI

The PySide GUI uses the same 2.0 Manager/Hand API and does not depend on the
Legacy `DeviceContext` layer.

```bash
python -m pip install './python[gui]'
python python/gui/main.py
```

Install `./python[gui,vision-touch]` instead when using the optional
vision tactile panels. The platform-specific vision tactile runtime must be
installed separately as described in `python/vts/README.md`.
