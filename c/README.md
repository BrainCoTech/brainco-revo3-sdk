# Revo3 C++ Examples

These examples use the C ABI from `dist/include/stark-sdk.h` in C++ programs.
They are Revo3-only and cover Modbus, CANFD auto-detect, motor control, touch data, and buffered monitoring.

## Build

From the repository root:

```bash
sh download-lib.sh
make -C c
```

## Run

Auto-detect:

```bash
./c/demo/auto_detect
./c/demo/hand_demo
./c/demo/hand_trajectory
./c/demo/hand_dfu firmware.bin
./c/demo/revo3_motor
./c/demo/revo3_touch
./c/demo/revo3_monitor
```

Manual Modbus:

```bash
./c/demo/hand_demo --modbus /dev/ttyUSB0 5000000 1
./c/demo/hand_trajectory --modbus /dev/ttyUSB0 5000000 1
./c/demo/hand_dfu --modbus /dev/ttyUSB0 5000000 1 firmware.bin
./c/demo/revo3_motor --modbus /dev/ttyUSB0 5000000 1
./c/demo/revo3_touch --modbus /dev/ttyUSB0 5000000 1
./c/demo/revo3_monitor --modbus /dev/ttyUSB0 5000000 1
```

The examples intentionally avoid legacy transports and APIs.
