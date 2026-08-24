# BC Revo3 SDK GUI

This GUI provides the current Revo3 Manager/Hand workflows for device control, telemetry, touch, diagnostics, and maintenance.

Panels:

- Connection / auto-detect
- Revo3 motor control
- Collision protection test controls in the Revo3 motor panel
- Revo3 motor configuration
- Revo3 touch sensor
- Data collection
- Teaching mode
- DFU
- System configuration

## Collision Test Panel

The Revo3 motor panel exposes collision protection controls for hardware testing. The GUI default uses `Hybrid`, `SoftStop`, `debounce_time_ms=50`, `max_cached_status_age_ms=80`, and `auto_clear_time_ms=1000`, with wider position-error and lower current thresholds than the SDK defaults for bench testing. The GUI keeps its existing Data Collection panel, but its adapter now obtains current samples through the 2.0 State pull subscription and stores only GUI-owned display history; it does not use the removed SDK collector or shared buffer. Normal drag mode reduces GUI monitoring to 10Hz so control commands have more bus time. When collision protection is enabled, drag mode keeps the normal monitor frequency so motor status remains fresh. If the dragged joint reports fresh firmware `Stall` samples while the slider is still held, the GUI locally shows a yellow stall guard and blocks that drag until slider release. SDK-confirmed `collision_active` remains the red state. Monitoring-frequency changes and collision config/poll calls run through background watchdog paths, so slow SDK or transport calls are logged but should not freeze the Qt UI.

## Install

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install './python[gui]'
```

On Windows PowerShell, create the environment with `py -3.10 -m venv .venv`
and activate it with `.venv\Scripts\Activate.ps1`.

## Run

```bash
python python/gui/main.py
python python/gui/main.py --revo3-modbus
python python/gui/main.py --mock
python python/gui/main.py --mock revo3-mx-touch
```

`--mock` is for GUI debugging without hardware. Supported mock types: `revo3`, `revo3-touch`, `revo3-mx-touch`, `revo3-pro`, `revo3-pro-touch`, `revo3-basic`, `revo3-basic-touch`.

The regular Revo3 touch UI is shown only when `hand.touch.layout` is available. If the SDK cannot identify the underlying register mapping, it fails closed; the GUI does not provide a manual override.

Independent vision-tactile sensor channels, dedicated runtimes, force models,
and visualization tools are not part of the public Revo3 SDK examples.
