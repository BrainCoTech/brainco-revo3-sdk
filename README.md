# BrainCo Revo3 SDK Examples

This repository contains Revo3-only examples for the BrainCo Revo3 SDK.

## Layout

- `c/` - C++ examples using the C ABI
- `python/revo3/` - Python Revo3 demos
- `python/gui/` - PySide GUI with Revo3 panels and mock mode

## C++

```bash
sh download-lib.sh
make -C c
./c/demo/auto_detect
./c/demo/hand_demo
./c/demo/hand_trajectory
./c/demo/hand_dfu firmware.bin
```

## Python

> **Note:** It is highly recommended to use a virtual environment (such as `conda` or `venv`) before installing the SDK and dependencies.
> ```bash
> conda create -n revo3 python=3.10
> conda activate revo3
> ```

**1. Install the SDK**

*For internal testing (download from OSS):*
```bash
bash ../scripts/install_whl.sh 1.0.6
```

*For stable release (download from PyPI):*
```bash
pip install bc-revo3-sdk==1.0.6
```

**2. Run examples**

```bash
cd python
pip install -r requirements.txt
python revo3/auto_detect.py
python revo3/hand_demo.py
python revo3/hand_trajectory.py
python revo3/hand_dfu.py /path/to/firmware.bin
python gui/main.py --mock
```
