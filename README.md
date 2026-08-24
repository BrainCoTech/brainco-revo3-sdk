# BrainCo Revo3 SDK Examples

This repository provides example applications and integration code demonstrating how to control BrainCo Revo3 dexterous hands using the SDK.

## Layout

- `c/` - C++ examples using the C ABI, plus a standalone Linux EtherCAT example
- `python/revo3/` - Python Revo3 demos
- `python/gui/` - PySide GUI with Revo3 panels and mock mode
- `docs/api/` - Revo3 2.0 public API reference
- `docs/device/` - Motor, touch, and collision protocol references

## Getting Started

### C++

```bash
bash download-lib.sh
make -C c
./c/build/demo/quickstart
./c/build/demo/quickstart --move
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

> **Note:** It is highly recommended to use a virtual environment (such as `conda` or `venv`) before installing the SDK and dependencies.
> ```bash
> conda create -n revo3 python=3.10
> conda activate revo3
> ```

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
bash python/install_whl.sh 2.0.0-rc.3
```

#### 2. Run examples

```bash
cd python
python -m pip install .

# Run Revo3 2.0 Manager examples (requires a real Revo3 device)
python revo3/quickstart.py
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
in `c/common/revo3_mit_plan.hpp`.
