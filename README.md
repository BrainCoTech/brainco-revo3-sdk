# BrainCo Revo3 SDK Examples

This repository provides example applications and integration code demonstrating how to control BrainCo Revo3 dexterous hands using the SDK.

## Layout

- `c/` - C++ examples using the C ABI, plus a standalone Linux EtherCAT example
- `python/revo3/` - Python Revo3 demos
- `python/gui/` - PySide GUI with Revo3 panels and mock mode

## Getting Started

### C++

```bash
sh download-lib.sh
make -C c
./c/demo/auto_detect
./c/demo/hand_demo
./c/demo/hand_trajectory
./c/demo/hand_dfu firmware.bin
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

*For internal testing (download from OSS):*
```bash
bash python/install_whl.sh 1.5.1
```

*For stable release (download from PyPI):*
```bash
pip install bc-revo3-sdk==1.5.1
```

#### 2. Run examples

```bash
cd python
# Install dependencies via uv (recommended):
uv sync

# Run CLI examples (requires a real Revo3 device)
python revo3/auto_detect.py
python revo3/hand_demo.py
python revo3/hand_trajectory.py
python revo3/hand_dfu.py /path/to/firmware.bin

# Run GUI in mock mode (recommended for a quick UI demo without hardware)
python gui/main.py --mock

# Run GUI in real-device mode (requires a connected Revo3 device)
python gui/main.py
```
