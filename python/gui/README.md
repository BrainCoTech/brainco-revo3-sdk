# BC Revo3 SDK GUI

This GUI provides Revo3 Manager/Hand workflows for device control, telemetry,
touch, diagnostics, and maintenance.

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

The Revo3 motor panel exposes collision protection controls for hardware
testing. The GUI defaults to `Hybrid`, `SoftStop`, `debounce_time_ms=50`,
`max_cached_status_age_ms=80`, and `auto_clear_time_ms=1000`. Review the
position-error and current thresholds before enabling motion; the GUI defaults
differ from the SDK defaults.

Normal drag mode reduces motor monitoring to 10 Hz so control commands have
more bus time. When collision protection is enabled, the normal monitoring
frequency remains active so motor status stays fresh. A fresh firmware `Stall`
sample while a slider is held activates a yellow local guard and blocks that
drag until the slider is released. SDK-confirmed `collision_active` status is
shown in red. Configuration and polling run in background tasks; slow SDK or
transport calls are written to the application log.

## Install

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install './python[gui]'
```

On Windows PowerShell, create the environment with `py -3.10 -m venv .venv`
and activate it with `.venv\Scripts\Activate.ps1`.

## Run

After installation, `revo3-gui` works from any directory. Run `revo3-gui --check`
to check dependency imports without opening devices, then `revo3-gui --mock`
to verify the interface. The commands below remain available from the repository root.

```bash
python python/gui/main.py
python python/gui/main.py --revo3-modbus
python python/gui/main.py --mock
python python/gui/main.py --mock ut2
python python/gui/main.py --mock uf1
```

`--mock` is for GUI debugging without hardware. Use a canonical three-character product code such as `UB1`, `UT1`, `UT2`, `UF1`, `PB1`, `PT1`, `DB1`, or `DT1`.

The regular Revo3 touch UI is shown only when `hand.touch.layout` is available. If the SDK cannot identify the underlying register mapping, it fails closed; the GUI does not provide a manual override.

For `fingertip_force_torque`, the GUI shows force, torque, resultant force, status, and tare controls without a heatmap because the layout declares `point_count=0` and frames return `points=None`. The heatmap is shown only for fingertip force/torque layouts that declare point-array data.

## Logs and Diagnostics

Choose **Help > Export Diagnostics...** to save a ZIP containing OS, Python and
dependency versions, cached connection/device labels, displayed FPS, and up to
three current-session log files (last 2 MiB each). Export runs in the background
and does not issue device commands. Wait for export to finish before closing.
The ZIP can contain device serial numbers, port names, and local paths from logs;
review it before sharing. It does not collect environment variables, firmware
images, or recorded sensor datasets.

If the GUI cannot start, run `revo3-gui --diagnostics support.zip` or
`python python/gui/main.py --diagnostics support.zip`. This offline
command works without GUI dependencies and exports environment metadata only.

GUI logs use `~/Library/Logs/BrainCo/Revo3` on macOS,
`%LOCALAPPDATA%/BrainCo/Revo3/logs` on Windows, and
`${XDG_STATE_HOME:-~/.local/state}/brainco/revo3/logs` on Linux.
Set `REVO3_LOG_DIR` to override the directory. Logs use UTC timestamps and rotate
at 2 MiB with two backups per session. Older sessions are retained; remove them
when no longer needed. Uncaught Python/worker exceptions and startup failures
are logged; native crashes and operating-system termination are not covered.

## Touch Sampling and Rendering

The GUI separates touch sampling from rendering. It keeps only the latest pending touch payload, dispatches visible charts at an approximately 16 ms interval (up to about 60 FPS), and refreshes numeric labels at a 100 ms interval. Hidden panels and hidden inner charts do not render incoming frames.

The touch sampling request depends on the detected layout and operating system:

| Touch layout | Platform | Sampling request |
|---|---|---|
| Fingertip force/torque layouts | Windows or Linux | Adaptive steps: `5`, `20`, `30`, `60`, `90`, and `120 Hz`; starts at `30 Hz` |
| Fingertip force/torque layouts | macOS | Maximum `5 Hz` |
| Other touch layouts | All supported platforms | Maximum `60 Hz` |

For adaptive sampling, the GUI evaluates completed reads every 5 seconds and waits at least 10 seconds between frequency changes. It raises the request when the measured rate reaches at least 90% of the current target without a new read error. It lowers the request when a read fails or the measured rate falls below 70% of the target.

`120 Hz` is a request ceiling, not a guaranteed device update rate. The displayed touch FPS counts completed subscription payloads. If a payload does not provide a firmware sequence number or acquisition timestamp, the GUI cannot use identical consecutive values to prove that the sensor produced distinct fresh samples. Transport, adapter, driver, firmware, payload size, and host load determine the achieved rate.

The SDK requests low-latency serial behavior on Windows and Linux. When the USB serial adapter driver exposes a latency-timer setting, configure it to `1 ms` before evaluating high-rate sampling. Use the touch FPS indicator to record the achieved rate and check the application log for adaptive frequency changes or read errors.

On Windows Modbus connections, the GUI identifies FTDI adapters from USB vendor ID `0x0403` or the serial-port manufacturer and product metadata. If an adaptive target of at least `60 Hz` remains below 70% of its target for the evaluation window, the GUI writes a one-time warning to the status bar and application log. The warning recommends checking **Device Manager > Ports > Port Settings > Advanced > Latency Timer**. It does not change the driver setting and does not identify the latency timer as the confirmed cause; transport and device limits can produce the same symptom.

Independent vision-tactile sensor channels, dedicated runtimes, force models,
and visualization tools are not part of the public Revo3 SDK examples.
