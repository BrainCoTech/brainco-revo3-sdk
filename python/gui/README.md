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
python python/gui/main.py --mock revo3-hp-ft-touch
```

`--mock` is for GUI debugging without hardware. Supported mock types include `revo3`, `revo3-touch`, `revo3-mx-touch`, `revo3-hp-ft-touch`, `revo3-pro`, `revo3-pro-touch`, `revo3-basic`, and `revo3-basic-touch`.

The regular Revo3 touch UI is shown only when `hand.touch.layout` is available. If the SDK cannot identify the underlying register mapping, it fails closed; the GUI does not provide a manual override.

For `hp_fingertip_ft`, the GUI shows force, torque, resultant force, status, and tare controls without a heatmap because the layout declares `point_count=0` and frames return `points=None`. The heatmap is shown only for `hp_*` layouts that declare point-array data.

## Touch Sampling and Rendering

The GUI separates touch sampling from rendering. It keeps only the latest pending touch payload, dispatches visible charts at an approximately 16 ms interval (up to about 60 FPS), and refreshes numeric labels at a 100 ms interval. Hidden panels and hidden inner charts do not render incoming frames.

The touch sampling request depends on the detected layout and operating system:

| Touch layout | Platform | Sampling request |
|---|---|---|
| `hp_*` force/torque layouts | Windows or Linux | Adaptive steps: `5`, `20`, `30`, `60`, `90`, and `120 Hz`; starts at `30 Hz` |
| `hp_*` force/torque layouts | macOS | Maximum `5 Hz` |
| Other touch layouts | All supported platforms | Maximum `60 Hz` |

For adaptive sampling, the GUI evaluates completed reads every 5 seconds and waits at least 10 seconds between frequency changes. It raises the request when the measured rate reaches at least 90% of the current target without a new read error. It lowers the request when a read fails or the measured rate falls below 70% of the target.

`120 Hz` is a request ceiling, not a guaranteed device update rate. The displayed touch FPS counts completed subscription payloads. If a payload does not provide a firmware sequence number or acquisition timestamp, the GUI cannot use identical consecutive values to prove that the sensor produced distinct fresh samples. Transport, adapter, driver, firmware, payload size, and host load determine the achieved rate.

The SDK requests low-latency serial behavior on Windows and Linux. When the USB serial adapter driver exposes a latency-timer setting, configure it to `1 ms` before evaluating high-rate sampling. Use the touch FPS indicator to record the achieved rate and check the application log for adaptive frequency changes or read errors.

On Windows Modbus connections, the GUI identifies FTDI adapters from USB vendor ID `0x0403` or the serial-port manufacturer and product metadata. If an adaptive target of at least `60 Hz` remains below 70% of its target for the evaluation window, the GUI writes a one-time warning to the status bar and application log. The warning recommends checking **Device Manager > Ports > Port Settings > Advanced > Latency Timer**. It does not change the driver setting and does not identify the latency timer as the confirmed cause; transport and device limits can produce the same symptom.

Independent vision-tactile sensor channels, dedicated runtimes, force models,
and visualization tools are not part of the public Revo3 SDK examples.
