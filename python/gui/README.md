# BC Revo3 SDK GUI

This GUI keeps the same window layout, tab organization, styling, and Revo3 panels as the legacy SDK GUI, while removing non-Revo3 workflows.

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

The Revo3 motor panel exposes collision protection controls for hardware testing. The GUI default uses `Hybrid`, `SoftStop`, `debounce_time_ms=50`, `max_cached_status_age_ms=80`, and `auto_clear_time_ms=1000`, with wider position-error and lower current thresholds than the SDK defaults for bench testing. Normal drag mode reduces the shared data collector to 10Hz so control commands have more bus time; when collision protection is enabled, drag mode keeps the collector at the normal monitor frequency so motor status stays fresh and the GUI avoids changing collector frequency on every drag press/release. If the dragged joint reports fresh firmware `Stall` samples while the slider is still held, the GUI locally shows a yellow stall guard and blocks that drag until slider release so it does not repeatedly push into the obstacle. SDK-confirmed `collision_active` remains the red state. On SDK-confirmed collision, the drag worker marks `collision_active`, tries the configured protection command with a watchdog timeout, and stops the current stream without sending a final hold. Collector start/stop/frequency changes and collision config/poll calls run through background watchdog paths, so slow SDK or transport calls are logged but should not freeze the Qt UI. SDK defaults remain defined by `CollisionProtectionConfig`.

## Install

```bash
uv sync --project examples/python
```

## Run

```bash
python examples/python/gui/main.py
python examples/python/gui/main.py --revo3-modbus
python examples/python/gui/main.py --mock
python examples/python/gui/main.py --mock revo3-vision
python examples/python/gui/main.py --mock revo3-matrix-touch
python examples/python/gui/main.py --touch-vendor matrix
python examples/python/gui/main.py --vts-force-model-dir examples/python/vts/checkpoints --vts-force-model-mode auto
```

`--mock` is for GUI debugging without hardware. Supported mock types: `revo3`, `revo3-touch`, `revo3-matrix-touch`, `revo3-vision`, `revo3-pro`, `revo3-pro-touch`, `revo3-basic`, `revo3-basic-touch`.

After connecting a Revo3 Ultra VisionTouch device, the `VisionTouch` tab is shown based on the hardware type. If the same hand also reports Pressure or Matrix touch, the regular Revo3 touch tab remains available. `Tools` -> `VisionTouch Sensor...` is kept as a shortcut to the VisionTouch tab.

Use `--touch-vendor matrix` or `--touch-vendor pressure` only to override the normal tactile register mapping when older firmware cannot report it. It does not enable or disable VisionTouch.

VisionTouch force model loading is optional to keep GUI startup fast:

| Option | Description | Default |
|--------|-------------|---------|
| `--vts-force-model-dir` | Parent directory for VTS force models: `{dir}/{SN}/{SN}.onnx.enc` | Auto-detects `examples/python/vts/checkpoints` when present |
| `--vts-force-model-mode` | `none` = fast init without Force6D, `auto` = load matching models when present, `required` = skip sensors without models | `none` |

Use `--vts-force-model-mode auto` only when Force6D values are needed. Without force models, image/depth/marker data still works and initializes faster.

The `VisionTouch` tab also provides a force model mode selector, a model directory picker, and an initialization progress bar. The model directory is the parent directory that contains per-SN model folders such as `{dir}/{SN}/{SN}.onnx.enc`. Changes made while sensors are connected are applied on the next reconnect.

Real VTS data requires `pyvitaisdk4bc`:

```bash
bash scripts/install_vts_whl.sh
```
