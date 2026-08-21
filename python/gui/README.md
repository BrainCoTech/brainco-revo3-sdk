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
- Timing test
- DFU
- System configuration
- VisionTouch window

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
python python/gui/main.py --mock revo3-vision
python python/gui/main.py --mock revo3-mx-touch
python python/gui/main.py --vts-force-model-dir python/vts/checkpoints --vts-force-model-mode auto
```

`--mock` is for GUI debugging without hardware. Supported mock types: `revo3`, `revo3-touch`, `revo3-mx-touch`, `revo3-vision`, `revo3-pro`, `revo3-pro-touch`, `revo3-basic`, `revo3-basic-touch`.

After connecting a Revo3 Ultra VisionTouch device, the `VisionTouch` tab is shown based on the product model. If the same hand also reports `mt_*` or `mx_*` touch, the regular Revo3 touch tab remains available. `Tools` -> `VisionTouch Sensor...` is kept as a shortcut to the VisionTouch tab.

The regular Revo3 touch UI is shown only when `hand.touch.layout` is available. If the SDK cannot identify the underlying register mapping, it fails closed; the GUI does not provide a manual override.

VisionTouch force model loading is optional to keep GUI startup fast:

| Option | Description | Default |
|--------|-------------|---------|
| `--vts-force-model-dir` | Parent directory for VTS force models: `{dir}/{SN}/{SN}.onnx.enc` | Auto-detects `python/vts/checkpoints` when present |
| `--vts-force-model-mode` | `none` = fast init without Force6D, `auto` = load matching models when present, `required` = skip sensors without models | `none` |

Use `--vts-force-model-mode auto` only when Force6D values are needed. Without force models, image/depth/marker data still works and initializes faster.

The `VisionTouch` tab also provides a force model mode selector, a model directory picker, and an initialization progress bar. The model directory is the parent directory that contains per-SN model folders such as `{dir}/{SN}/{SN}.onnx.enc`. Changes made while sensors are connected are applied on the next reconnect.

Real VTS data requires `pyvitaisdk4bc`:

```bash
bash python/install_vts_whl.sh
```
