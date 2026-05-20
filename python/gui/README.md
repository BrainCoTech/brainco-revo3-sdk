# BC Revo3 SDK GUI

This GUI keeps the same window layout, tab organization, styling, and Revo3 panels as the legacy SDK GUI, while removing non-Revo3 workflows.

Panels:

- Connection / auto-detect
- Revo3 motor control
- Revo3 motor configuration
- Revo3 touch sensor
- Data collection
- Teaching mode
- Timing test
- DFU
- System configuration
- VisionTouch window

## Install

```bash
pip install -r examples/python/gui/requirements.txt
pip install bc-revo3-sdk
```

## Run

```bash
python examples/python/gui/main.py
python examples/python/gui/main.py --revo3-modbus
python examples/python/gui/main.py --mock
python examples/python/gui/main.py --mock revo3-vision
```

`--mock` is for GUI debugging without hardware. Supported mock types: `revo3`, `revo3-touch`, `revo3-vision`, `revo3-pro`, `revo3-pro-touch`, `revo3-basic`, `revo3-basic-touch`.
