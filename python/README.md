# BrainCo Revo3 Python Examples

Python examples in this repository are scoped to Revo3.

## Install

### 1. Install Dependencies

```bash
# If using uv (recommended):
uv sync

```

### 2. Install SDK (from OSS)

```bash
bash install_whl.sh
```

For a local development build:

```bash
bash install_whl.sh
```

## Import

```python
from bc_revo3_sdk import main_mod as sdk
```

## Revo3 Examples

See [revo3/README.md](revo3/README.md) for the full Revo3 Python API reference and examples.

```bash
cd python/revo3
python auto_detect.py
python hand_demo.py
python hand_trajectory.py
python hand_dfu.py /path/to/firmware.bin
python revo3_motor.py
```

## GUI

The PySide GUI lives in `python/gui` and includes Revo3 connection, motor, touch, data collection, teaching, timing, DFU and VisionTouch panels.

```bash
python python/gui/main.py
python python/gui/main.py --mock
```
